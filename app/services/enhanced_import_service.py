"""
Enhanced Import Service with detailed progress tracking and multi-source support
"""

import asyncio
import hashlib
import os
import tempfile
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, AsyncGenerator
from dataclasses import dataclass, field
import aiofiles
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import ImportSource, Channel, ChannelGroup, Playlist, EPGProgram
from app.database import get_db
from app.utils.m3u_parser import M3UParser
from app.utils.xmltv_parser import XMLTVParser
from app.utils.epg_auto_mapper import EPGAutoMapper
from app.core.error_management import error_manager, ErrorCategory, ErrorSeverity, handle_import_error
from app.api.websocket import send_import_update
import logging

# Try to import multicore support
try:
    from app.utils.multicore_import import optimize_import_with_multicore
    MULTICORE_AVAILABLE = True
except ImportError:
    MULTICORE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ImportProgress:
    """Detailed progress tracking for imports"""
    phase: str = "initializing"  # initializing, downloading, parsing, processing, importing, completing
    total_items: int = 0
    processed_items: int = 0
    current_item: str = ""
    percentage: float = 0.0
    speed_bps: float = 0.0  # bytes per second
    eta_seconds: Optional[int] = None
    sub_progress: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "phase": self.phase,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "current_item": self.current_item,
            "percentage": round(self.percentage, 2),
            "speed_bps": round(self.speed_bps, 2),
            "eta_seconds": self.eta_seconds,
            "sub_progress": self.sub_progress,
            "warnings": self.warnings,
            "errors": self.errors
        }


class EnhancedImportService:
    """Enhanced import service with detailed progress tracking"""
    
    def __init__(self, db: Session):
        self.db = db
        self.active_imports: Dict[str, ImportProgress] = {}
        self.import_locks: Dict[str, asyncio.Lock] = {}
        
    async def import_source(
        self,
        source_id: int,
        user_id: int,
        force_refresh: bool = False
    ) -> AsyncGenerator[Dict, None]:
        """Import from a source with detailed progress updates"""
        
        source = self.db.query(ImportSource).filter(ImportSource.id == source_id).first()
        if not source:
            raise ValueError("Import source not found")
        
        # Check if already importing
        import_key = f"source_{source_id}"
        if import_key in self.import_locks and self.import_locks[import_key].locked():
            raise ValueError("Import already in progress for this source")
        
        # Create lock
        self.import_locks[import_key] = asyncio.Lock()
        
        async with self.import_locks[import_key]:
            progress = ImportProgress()
            self.active_imports[import_key] = progress
            
            try:
                # Update source status
                source.last_import_attempt = datetime.utcnow()
                source.import_status = "importing"
                self.db.commit()
                
                # Yield initial progress
                yield self._create_update(source_id, "started", progress)
                
                # Download or read file
                if source.source_type == "url":
                    async for update in self._download_file(source, progress):
                        yield update
                else:
                    async for update in self._read_uploaded_file(source, progress):
                        yield update
                
                # Parse content based on type
                if source.url and source.url.lower().endswith(('.m3u', '.m3u8')):
                    async for update in self._parse_m3u(source, progress):
                        yield update
                elif source.epg_url and source.epg_url.lower().endswith(('.xml', '.gz')):
                    async for update in self._parse_epg(source, progress):
                        yield update
                else:
                    # Auto-detect format
                    async for update in self._auto_detect_and_parse(source, progress):
                        yield update
                
                # Update source statistics
                progress.phase = "completing"
                source.last_import_success = datetime.utcnow()
                source.import_status = "success"
                source.channels_imported = progress.processed_items
                source.import_errors = None
                self.db.commit()
                
                # Final update
                progress.percentage = 100.0
                yield self._create_update(source_id, "completed", progress)
                
            except Exception as e:
                # Handle error
                error = handle_import_error(e, source.url or source.name, user_id)
                
                source.import_status = "failed"
                source.import_errors = error.user_message
                self.db.commit()
                
                progress.phase = "failed"
                progress.errors.append(error.user_message)
                
                yield self._create_update(source_id, "failed", progress, error=error)
                
            finally:
                # Cleanup
                del self.active_imports[import_key]
                del self.import_locks[import_key]
    
    async def _download_file(
        self,
        source: ImportSource,
        progress: ImportProgress
    ) -> AsyncGenerator[Dict, None]:
        """Download file with progress tracking"""
        progress.phase = "downloading"
        progress.current_item = f"Downloading from {source.url}"
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                async with client.stream('GET', source.url) as response:
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    start_time = time.time()
                    last_update = start_time
                    
                    # Update progress
                    progress.total_items = total_size
                    
                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Calculate progress
                            current_time = time.time()
                            elapsed = current_time - start_time
                            
                            if elapsed > 0:
                                progress.speed_bps = downloaded / elapsed
                                
                                if total_size > 0:
                                    progress.percentage = (downloaded / total_size) * 100
                                    remaining = total_size - downloaded
                                    if progress.speed_bps > 0:
                                        progress.eta_seconds = int(remaining / progress.speed_bps)
                            
                            progress.processed_items = downloaded
                            
                            # Yield update every 0.5 seconds
                            if current_time - last_update > 0.5:
                                yield self._create_update(source.id, "downloading", progress)
                                last_update = current_time
            
            # Calculate file hash
            progress.phase = "verifying"
            progress.current_item = "Verifying file integrity"
            yield self._create_update(source.id, "processing", progress)
            
            file_hash = await self._calculate_file_hash(temp_path)
            
            # Check for duplicates
            if not source.file_hash or source.file_hash != file_hash:
                source.file_hash = file_hash
                source.file_path = temp_path
                self.db.commit()
            else:
                # File hasn't changed
                progress.warnings.append("File content hasn't changed since last import")
                
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    async def _parse_m3u(
        self,
        source: ImportSource,
        progress: ImportProgress
    ) -> AsyncGenerator[Dict, None]:
        """Parse M3U file with detailed progress"""
        progress.phase = "parsing"
        progress.current_item = "Parsing M3U playlist"
        
        parser = M3UParser()
        channels_data = await parser.parse_file(source.file_path)
        
        progress.total_items = len(channels_data)
        progress.phase = "importing"
        
        # Get or create playlist
        playlist = self.db.query(Playlist).filter(
            Playlist.name == source.name
        ).first()
        
        if not playlist:
            playlist = Playlist(
                name=source.name,
                url=source.url,
                last_updated=datetime.utcnow()
            )
            self.db.add(playlist)
            self.db.commit()
        
        # Process channels in batches
        batch_size = 50
        for i in range(0, len(channels_data), batch_size):
            batch = channels_data[i:i + batch_size]
            
            for channel_data in batch:
                try:
                    await self._import_channel(channel_data, playlist, source)
                    progress.processed_items += 1
                except Exception as e:
                    logger.error(f"Error importing channel: {e}")
                    progress.errors.append(f"Failed to import {channel_data.get('name', 'Unknown')}: {str(e)}")
                
                progress.percentage = (progress.processed_items / progress.total_items) * 100
                progress.current_item = channel_data.get('name', 'Unknown channel')
            
            # Commit batch
            self.db.commit()
            
            # Yield progress update
            yield self._create_update(source.id, "importing", progress)
    
    async def _import_channel(
        self,
        channel_data: Dict,
        playlist: Playlist,
        source: ImportSource
    ) -> None:
        """Import or update a single channel"""
        # Check if channel exists
        channel = self.db.query(Channel).filter(
            Channel.url == channel_data['url']
        ).first()
        
        if channel:
            # Update existing channel (preserve user modifications)
            if not channel.user_modified:
                channel.name = channel_data.get('name', channel.name)
                channel.logo = channel_data.get('logo', channel.logo)
            
            channel.is_active = True
            channel.last_seen = datetime.utcnow()
        else:
            # Create new channel
            channel = Channel(
                name=channel_data['name'],
                url=channel_data['url'],
                logo=channel_data.get('logo'),
                playlist_id=playlist.id,
                is_active=True,
                last_seen=datetime.utcnow()
            )
            
            # Auto-assign channel number
            max_number = self.db.query(func.max(Channel.channel_number)).scalar() or 0
            channel.channel_number = max_number + 1
            
            self.db.add(channel)
        
        # Handle channel group
        group_name = channel_data.get('group', 'Uncategorized')
        group = self.db.query(ChannelGroup).filter(
            ChannelGroup.name == group_name
        ).first()
        
        if not group:
            group = ChannelGroup(name=group_name)
            self.db.add(group)
            self.db.flush()
        
        channel.group_id = group.id
    
    async def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(8192):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def _create_update(
        self,
        source_id: int,
        status: str,
        progress: ImportProgress,
        error: Optional[Dict] = None
    ) -> Dict:
        """Create progress update message"""
        return {
            "source_id": source_id,
            "status": status,
            "progress": progress.to_dict(),
            "error": error.to_user_dict() if error else None,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_import_progress(self, source_id: int) -> Optional[Dict]:
        """Get current import progress"""
        import_key = f"source_{source_id}"
        progress = self.active_imports.get(import_key)
        
        if progress:
            return self._create_update(source_id, "in_progress", progress)
        
        return None
    
    async def cancel_import(self, source_id: int) -> bool:
        """Cancel an active import"""
        import_key = f"source_{source_id}"
        
        if import_key in self.active_imports:
            # Set cancellation flag
            # Note: Actual cancellation logic would need to be implemented
            # in the import methods by checking a cancellation flag
            return True
        
        return False
    
    async def import_multiple_sources(
        self,
        source_ids: List[int],
        user_id: int
    ) -> AsyncGenerator[Dict, None]:
        """Import multiple sources concurrently"""
        tasks = []
        
        for source_id in source_ids:
            task = asyncio.create_task(
                self._collect_import_updates(source_id, user_id)
            )
            tasks.append(task)
        
        # Yield updates as they come in
        pending = set(tasks)
        
        while pending:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in done:
                updates = await task
                for update in updates:
                    yield update
    
    async def _collect_import_updates(
        self,
        source_id: int,
        user_id: int
    ) -> List[Dict]:
        """Collect all updates from an import"""
        updates = []
        
        async for update in self.import_source(source_id, user_id):
            updates.append(update)
            
            # Also send via WebSocket if available
            try:
                await send_import_update(
                    str(user_id),
                    update['source_id'],
                    update['status'],
                    update['progress']
                )
            except:
                pass  # WebSocket might not be available
        
        return updates