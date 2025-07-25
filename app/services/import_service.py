import asyncio
import hashlib
import os
import tempfile
import aiofiles
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import UploadFile

from app.models.import_source import ImportSource
from app.models.playlist import Playlist
from app.models.channel import Channel, ChannelGroup
from app.models.epg_source import EPGSource
from app.utils.m3u_parser import M3UParser
from app.utils.epg_auto_mapper import EPGAutoMapper, EPGChannel
from app.utils.xmltv_parser import XMLTVParser
from app.utils.import_manager import import_manager
from app.database import SessionLocal

logger = logging.getLogger(__name__)

class ImportService:
    """Modern import service for 2030-ready IPTV management"""
    
    def __init__(self):
        self.upload_dir = Path(tempfile.gettempdir()) / "iptv_imports"
        self.upload_dir.mkdir(exist_ok=True)
    
    async def create_source(
        self,
        db: Session,
        name: str,
        m3u_url: Optional[str] = None,
        m3u_file: Optional[UploadFile] = None,
        epg_url: Optional[str] = None,
        epg_file: Optional[UploadFile] = None,
        import_settings: Optional[Dict[str, Any]] = None,
        auto_refresh: bool = False,
        refresh_interval: int = 86400,
        created_by_id: Optional[int] = None
    ) -> ImportSource:
        """Create a new import source with deduplication"""
        
        # Process uploaded files
        m3u_file_path = None
        m3u_file_hash = None
        epg_file_path = None
        
        if m3u_file:
            m3u_file_path, m3u_file_hash = await self._save_upload_file(m3u_file, "m3u")
            
            # Check for duplicate by hash
            existing = db.query(ImportSource).filter(
                ImportSource.file_hash == m3u_file_hash
            ).first()
            
            if existing:
                raise ValueError(f"This M3U file already exists as source: {existing.name}")
        
        if epg_file:
            epg_file_path, _ = await self._save_upload_file(epg_file, "epg")
        
        # Check for duplicate URLs
        if m3u_url:
            existing = db.query(ImportSource).filter(
                ImportSource.m3u_url == m3u_url,
                ImportSource.epg_url == (epg_url or None)
            ).first()
            
            if existing:
                raise ValueError(f"A source with these URLs already exists: {existing.name}")
        
        # Create source
        source = ImportSource(
            name=name,
            source_type='file' if m3u_file else 'url',
            m3u_url=m3u_url,
            m3u_file_path=m3u_file_path,
            epg_url=epg_url,
            epg_file_path=epg_file_path,
            import_settings=import_settings or self._default_import_settings(),
            auto_refresh=auto_refresh,
            refresh_interval=refresh_interval,
            created_by_id=created_by_id,
            original_filename=m3u_file.filename if m3u_file else None,
            file_size=m3u_file.size if m3u_file else None,
            file_hash=m3u_file_hash
        )
        
        db.add(source)
        db.commit()
        db.refresh(source)
        
        logger.info(f"Created import source: {source.name} (ID: {source.id})")
        return source
    
    async def update_source(
        self,
        db: Session,
        source_id: int,
        **kwargs
    ) -> ImportSource:
        """Update an existing source"""
        source = db.query(ImportSource).filter(ImportSource.id == source_id).first()
        if not source:
            raise ValueError(f"Source {source_id} not found")
        
        # Update allowed fields
        update_fields = [
            'name', 'epg_url', 'import_settings', 'auto_refresh', 
            'refresh_interval', 'refresh_time', 'is_active'
        ]
        
        for field in update_fields:
            if field in kwargs and kwargs[field] is not None:
                setattr(source, field, kwargs[field])
        
        source.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(source)
        
        return source
    
    async def import_from_source(
        self,
        db: Session,
        source_id: int,
        user_id: Optional[int] = None,
        force_refresh: bool = False
    ) -> str:
        """Import channels from a source"""
        source = db.query(ImportSource).filter(ImportSource.id == source_id).first()
        if not source:
            raise ValueError(f"Source {source_id} not found")
        
        # Check if already importing
        import_id = f"source_{source_id}"
        existing_job = import_manager.get_job(import_id)
        if existing_job and existing_job.status in ['pending', 'downloading', 'parsing', 'importing']:
            return existing_job.id
        
        # Create or get playlist
        playlist = await self._ensure_playlist(db, source)
        
        # Create import job
        m3u_location = source.get_m3u_location()
        epg_location = source.get_epg_location() if source.import_settings.get('auto_map_epg') else None
        
        job = import_manager.create_job(
            import_id=f"source_{source_id}_{int(datetime.utcnow().timestamp())}",
            playlist_id=playlist.id,
            url=m3u_location,
            epg_url=epg_location
        )
        
        # Update source status
        source.last_import_at = datetime.utcnow()
        source.last_import_status = 'importing'
        db.commit()
        
        # Store IDs to avoid session issues
        source_id_copy = source.id
        playlist_id_copy = playlist.id
        auto_refresh_copy = source.auto_refresh
        refresh_interval_copy = source.refresh_interval
        
        # Create enhanced progress callback
        async def progress_callback(status: str, progress: float, message: str, details: dict = None):
            # Create new session for callback
            callback_db = SessionLocal()
            try:
                # Get fresh source object
                source_obj = callback_db.query(ImportSource).filter(ImportSource.id == source_id_copy).first()
                if not source_obj:
                    return
                
                # Update source with progress
                if status in ['completed', 'failed']:
                    source_obj.last_import_status = 'success' if status == 'completed' else 'failed'
                    source_obj.last_import_details = details or {'message': message}
                    
                    if status == 'completed':
                        # Update statistics
                        channel_count = callback_db.query(Channel).filter(
                            Channel.playlist_id == playlist_id_copy
                        ).count()
                        
                        active_count = callback_db.query(Channel).filter(
                            Channel.playlist_id == playlist_id_copy,
                            Channel.is_active == True
                        ).count()
                        
                        source_obj.total_channels = channel_count
                        source_obj.active_channels = active_count
                        source_obj.failed_channels = channel_count - active_count
                        
                        # Calculate next refresh
                        if auto_refresh_copy:
                            source_obj.next_refresh_at = datetime.utcnow() + timedelta(seconds=refresh_interval_copy)
                    
                    callback_db.commit()
            finally:
                callback_db.close()
            
            # Send websocket update if user_id provided
            if user_id:
                try:
                    from app.api.websocket import send_import_update
                    # Create progress dict for WebSocket
                    progress_data = {
                        'phase': status,
                        'percentage': progress,
                        'current_item': message,
                        'details': details
                    }
                    await send_import_update(str(user_id), source.id, status, progress_data)
                except ImportError:
                    # WebSocket updates not available
                    pass
        
        # Start import
        await import_manager.start_import(job.id, progress_callback)
        
        return job.id
    
    async def get_sources(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        search: Optional[str] = None
    ) -> Tuple[List[ImportSource], int]:
        """Get import sources with pagination"""
        query = db.query(ImportSource)
        
        if active_only:
            query = query.filter(ImportSource.is_active == True)
        
        if search:
            query = query.filter(
                or_(
                    ImportSource.name.ilike(f"%{search}%"),
                    ImportSource.m3u_url.ilike(f"%{search}%"),
                    ImportSource.original_filename.ilike(f"%{search}%")
                )
            )
        
        total = query.count()
        sources = query.order_by(ImportSource.created_at.desc()).offset(skip).limit(limit).all()
        
        return sources, total
    
    async def delete_source(
        self,
        db: Session,
        source_id: int,
        delete_channels: bool = False
    ) -> bool:
        """Delete an import source"""
        source = db.query(ImportSource).filter(ImportSource.id == source_id).first()
        if not source:
            return False
        
        # Get associated playlist
        playlist = db.query(Playlist).filter(
            Playlist.name == f"Source: {source.name}"
        ).first()
        
        if playlist:
            if delete_channels:
                # Delete all channels
                db.query(Channel).filter(Channel.playlist_id == playlist.id).delete()
                # Delete playlist
                db.delete(playlist)
            else:
                # Just mark channels as inactive
                db.query(Channel).filter(
                    Channel.playlist_id == playlist.id
                ).update({"is_active": False})
        
        # Delete uploaded files
        if source.m3u_file_path and os.path.exists(source.m3u_file_path):
            try:
                os.remove(source.m3u_file_path)
            except:
                pass
        
        if source.epg_file_path and os.path.exists(source.epg_file_path):
            try:
                os.remove(source.epg_file_path)
            except:
                pass
        
        # Delete source
        db.delete(source)
        db.commit()
        
        return True
    
    async def refresh_sources(
        self,
        db: Session,
        force_all: bool = False
    ) -> List[str]:
        """Refresh sources that need updating"""
        job_ids = []
        now = datetime.utcnow()
        
        # Get sources that need refresh
        query = db.query(ImportSource).filter(
            ImportSource.is_active == True
        )
        
        if not force_all:
            query = query.filter(
                or_(
                    ImportSource.auto_refresh == True,
                    ImportSource.next_refresh_at <= now
                )
            )
        
        sources = query.all()
        
        for source in sources:
            try:
                # Skip if never imported
                if not source.last_import_at and not force_all:
                    continue
                
                job_id = await self.import_from_source(db, source.id)
                job_ids.append(job_id)
                
            except Exception as e:
                logger.error(f"Failed to refresh source {source.id}: {e}")
        
        return job_ids
    
    async def validate_source(
        self,
        m3u_url: Optional[str] = None,
        m3u_file: Optional[UploadFile] = None,
        epg_url: Optional[str] = None,
        epg_file: Optional[UploadFile] = None
    ) -> Dict[str, Any]:
        """Validate source before creating"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "info": {}
        }
        
        # Validate M3U
        if m3u_url:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.head(m3u_url, follow_redirects=True)
                    if response.status_code != 200:
                        result["errors"].append(f"M3U URL returned status {response.status_code}")
                        result["valid"] = False
                    else:
                        size = response.headers.get('content-length')
                        if size:
                            result["info"]["m3u_size"] = int(size)
            except Exception as e:
                result["errors"].append(f"Cannot access M3U URL: {str(e)}")
                result["valid"] = False
        
        elif m3u_file:
            # Validate file
            if not m3u_file.filename.endswith(('.m3u', '.m3u8')):
                result["warnings"].append("File doesn't have standard M3U extension")
            
            result["info"]["m3u_filename"] = m3u_file.filename
            result["info"]["m3u_size"] = m3u_file.size
        
        # Validate EPG
        if epg_url:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.head(epg_url, follow_redirects=True)
                    if response.status_code != 200:
                        result["warnings"].append(f"EPG URL returned status {response.status_code}")
                    else:
                        result["info"]["epg_available"] = True
            except Exception as e:
                result["warnings"].append(f"Cannot access EPG URL: {str(e)}")
        
        return result
    
    async def get_source_stats(
        self,
        db: Session
    ) -> Dict[str, Any]:
        """Get overall import statistics"""
        total_sources = db.query(ImportSource).count()
        active_sources = db.query(ImportSource).filter(
            ImportSource.is_active == True
        ).count()
        
        # Get channel stats across all sources
        total_channels = db.query(Channel).count()
        active_channels = db.query(Channel).filter(
            Channel.is_active == True
        ).count()
        
        # Get recent imports
        recent_imports = db.query(ImportSource).filter(
            ImportSource.last_import_at.isnot(None)
        ).order_by(
            ImportSource.last_import_at.desc()
        ).limit(10).all()
        
        # Get failing sources
        failing_sources = db.query(ImportSource).filter(
            ImportSource.last_import_status == 'failed'
        ).count()
        
        return {
            "total_sources": total_sources,
            "active_sources": active_sources,
            "failing_sources": failing_sources,
            "total_channels": total_channels,
            "active_channels": active_channels,
            "recent_imports": [
                {
                    "source_id": s.id,
                    "source_name": s.name,
                    "imported_at": s.last_import_at.isoformat() if s.last_import_at else None,
                    "status": s.last_import_status,
                    "channel_count": s.total_channels
                }
                for s in recent_imports
            ]
        }
    
    async def _save_upload_file(
        self,
        upload_file: UploadFile,
        file_type: str
    ) -> Tuple[str, Optional[str]]:
        """Save uploaded file and calculate hash"""
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = "".join(c for c in upload_file.filename if c.isalnum() or c in "._-")
        filename = f"{file_type}_{timestamp}_{safe_filename}"
        file_path = self.upload_dir / filename
        
        # Calculate hash while saving
        hasher = hashlib.sha256()
        
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await upload_file.read(8192):
                await f.write(chunk)
                hasher.update(chunk)
        
        file_hash = hasher.hexdigest() if file_type == "m3u" else None
        
        return str(file_path), file_hash
    
    async def _ensure_playlist(
        self,
        db: Session,
        source: ImportSource
    ) -> Playlist:
        """Ensure playlist exists for source"""
        playlist_name = f"Source: {source.name}"
        
        playlist = db.query(Playlist).filter(
            Playlist.name == playlist_name
        ).first()
        
        if not playlist:
            playlist = Playlist(
                name=playlist_name,
                url=source.get_m3u_location() or "",
                is_active=True
            )
            db.add(playlist)
            db.commit()
            db.refresh(playlist)
        
        # Ensure EPG source if needed
        if source.epg_url or source.epg_file_path:
            epg_source = db.query(EPGSource).filter(
                EPGSource.playlist_id == playlist.id
            ).first()
            
            if not epg_source:
                epg_source = EPGSource(
                    name=f"{source.name} EPG",
                    url=source.get_epg_location(),
                    playlist_id=playlist.id,
                    is_active=True
                )
                db.add(epg_source)
                db.commit()
        
        return playlist
    
    def _default_import_settings(self) -> Dict[str, Any]:
        """Get default import settings"""
        return {
            "auto_map_epg": False,
            "update_existing": True,
            "preserve_user_edits": True,
            "skip_duplicates": True,
            "filter_adult": False,
            "only_hd": False,
            "test_streams": False,
            "group_filter": [],
            "country_filter": [],
            "language_filter": []
        }

# Global import service instance
import_service = ImportService()