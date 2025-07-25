import asyncio
import os
import tempfile
import time
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import aiofiles
import httpx
from pathlib import Path
import multiprocessing

logger = logging.getLogger(__name__)

# Check if multicore import is available
try:
    from app.utils.multicore_import import optimize_import_with_multicore
    MULTICORE_AVAILABLE = True
    logger.info(f"Multicore import available with {multiprocessing.cpu_count()} cores")
except ImportError:
    MULTICORE_AVAILABLE = False
    logger.warning("Multicore import not available, using single-threaded import")

# WebSocket manager for broadcasting logs
from app.api.websocket import manager as ws_manager

class WebSocketLogHandler(logging.Handler):
    """Custom log handler that sends logs through WebSocket"""
    def __init__(self, import_id: str):
        super().__init__()
        self.import_id = import_id
        
    def emit(self, record):
        try:
            log_entry = {
                "type": "import_log",
                "import_id": self.import_id,
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "source": record.name,
                "message": self.format(record)
            }
            # Send to all connected WebSocket clients
            for user_id in list(ws_manager.active_connections.keys()):
                asyncio.create_task(ws_manager.broadcast_to_user(log_entry, user_id))
        except Exception:
            self.handleError(record)

@dataclass
class ImportJob:
    id: str
    playlist_id: int
    url: str
    epg_url: Optional[str] = None
    status: str = "pending"  # pending, downloading, parsing, importing, completed, failed
    progress: float = 0.0
    message: str = ""
    details: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    temp_file: Optional[str] = None
    total_size: int = 0
    downloaded_size: int = 0
    
class ImportManager:
    """Manages background import jobs with resumable downloads"""
    
    def __init__(self):
        self.jobs: Dict[str, ImportJob] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.callbacks: Dict[str, Callable] = {}
        
    def create_job(self, import_id: str, playlist_id: int, url: str, epg_url: Optional[str] = None) -> ImportJob:
        """Create a new import job"""
        job = ImportJob(
            id=import_id,
            playlist_id=playlist_id,
            url=url,
            epg_url=epg_url
        )
        self.jobs[import_id] = job
        return job
    
    def get_job(self, import_id: str) -> Optional[ImportJob]:
        """Get job by ID"""
        return self.jobs.get(import_id)
    
    def get_job_status(self, import_id: str) -> Optional[dict]:
        """Get job status for API"""
        job = self.jobs.get(import_id)
        if not job:
            return None
            
        return {
            "import_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "details": job.details,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat()
        }
    
    async def start_import(self, import_id: str, progress_callback: Optional[Callable] = None):
        """Start or resume an import job"""
        job = self.jobs.get(import_id)
        if not job:
            raise ValueError(f"Import job {import_id} not found")
        
        # Store callback
        if progress_callback:
            self.callbacks[import_id] = progress_callback
        
        # Don't start if already running
        if import_id in self.active_tasks and not self.active_tasks[import_id].done():
            logger.info(f"Import {import_id} already running")
            return
        
        # Create and store task
        task = asyncio.create_task(self._run_import(job))
        self.active_tasks[import_id] = task
        
        # Clean up when done
        task.add_done_callback(lambda t: self.active_tasks.pop(import_id, None))
        
        return task
    
    async def _run_import(self, job: ImportJob):
        """Run the import process"""
        # Set up WebSocket logging for this import
        ws_handler = WebSocketLogHandler(job.id)
        ws_handler.setFormatter(logging.Formatter('%(message)s'))
        
        # Add handler to relevant loggers
        import_logger = logging.getLogger('app.utils.import_manager')
        parser_logger = logging.getLogger('app.utils.m3u_parser')
        
        import_logger.addHandler(ws_handler)
        parser_logger.addHandler(ws_handler)
        
        try:
            # Update status
            await self._update_job(job, "downloading", 0, "Starting download...")
            
            # Download with resume support
            temp_file = await self._download_with_resume(job)
            job.temp_file = str(temp_file)
            
            # Parse M3U
            await self._update_job(job, "parsing", 50, "Parsing playlist...")
            logger.info(f"Starting M3U parsing for file: {job.temp_file}")
            
            from app.utils.m3u_parser import M3UParser
            parser = M3UParser()
            
            # Log file size and first few lines for debugging
            file_size = Path(job.temp_file).stat().st_size
            logger.info(f"M3U file size: {file_size/1024/1024:.1f} MB")
            
            with open(job.temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                first_lines = [f.readline().strip() for _ in range(5)]
                logger.info(f"First 5 lines of M3U file: {first_lines}")
            
            logger.info("Calling parser.parse_from_file()...")
            channels_data = parser.parse_from_file(job.temp_file)
            logger.info(f"M3U parsing completed! Found {len(channels_data)} channels")
            
            # Import channels
            await self._update_job(job, "importing", 70, f"Importing {len(channels_data)} channels...")
            logger.info(f"Starting channel import for {len(channels_data)} channels")
            await self._import_channels(job, channels_data)
            logger.info("Channel import completed successfully")
            
            # Success
            await self._update_job(job, "completed", 100, f"Successfully imported {len(channels_data)} channels")
            
        except Exception as e:
            logger.error(f"Import {job.id} failed: {e}")
            job.error = str(e)
            await self._update_job(job, "failed", job.progress, f"Import failed: {str(e)}")
            raise
        finally:
            # Remove WebSocket handler
            import_logger.removeHandler(ws_handler)
            parser_logger.removeHandler(ws_handler)
            
            # Clean up temp file
            if job.temp_file and os.path.exists(job.temp_file):
                try:
                    os.unlink(job.temp_file)
                except:
                    pass
    
    async def _download_with_resume(self, job: ImportJob) -> Path:
        """Download file with resume support for large files"""
        temp_dir = tempfile.gettempdir()
        temp_file = Path(temp_dir) / f"m3u_import_{job.id}.m3u"
        
        # Check if partial download exists
        start_byte = 0
        if temp_file.exists():
            start_byte = temp_file.stat().st_size
            logger.info(f"Resuming download from byte {start_byte}")
        
        logger.info(f"Starting download from: {job.url}")
        
        # Configure client with streaming support
        timeout = httpx.Timeout(
            connect=30.0,
            read=300.0,  # 5 minute read timeout for large files
            write=30.0,
            pool=30.0
        )
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',  # Don't use compression for M3U files to avoid issues
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        }
        
        # Add range header for resume
        if start_byte > 0:
            headers['Range'] = f'bytes={start_byte}-'
        
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            try:
                # Get total size first
                if job.total_size == 0:
                    try:
                        logger.info("Checking file size with HEAD request...")
                        head_response = await client.head(job.url)
                        job.total_size = int(head_response.headers.get('content-length', 0))
                        logger.info(f"File size: {job.total_size/1024/1024:.1f} MB")
                    except Exception as e:
                        logger.warning(f"HEAD request failed: {e}")
                
                # Update status
                await self._update_job(job, "downloading", 5, "Starting download...")
                
                # Stream download
                logger.info("Starting GET request to download file...")
                async with client.stream('GET', job.url) as response:
                    response.raise_for_status()
                    
                    # Check if server supports resume
                    if start_byte > 0 and response.status_code != 206:
                        logger.warning("Server doesn't support resume, starting from beginning")
                        start_byte = 0
                        temp_file.unlink()
                    
                    # Get content length
                    content_length = int(response.headers.get('content-length', 0))
                    if content_length > 0 and job.total_size == 0:
                        job.total_size = content_length + start_byte
                    
                    # Open file for append or write
                    mode = 'ab' if start_byte > 0 else 'wb'
                    async with aiofiles.open(temp_file, mode) as f:
                        downloaded = start_byte
                        chunk_size = 1024 * 1024  # 1MB chunks
                        last_update = time.time()
                        
                        # Log initial download start
                        logger.info(f"Starting to download chunks (chunk size: {chunk_size/1024:.0f} KB)")
                        chunk_count = 0
                        
                        async for chunk in response.aiter_bytes(chunk_size):
                            if not chunk:
                                break
                            
                            chunk_count += 1
                            await f.write(chunk)
                            downloaded += len(chunk)
                            job.downloaded_size = downloaded
                            
                            # Log first few chunks for debugging
                            if chunk_count <= 5:
                                logger.info(f"Downloaded chunk {chunk_count}: {len(chunk)} bytes (total: {downloaded/1024/1024:.1f} MB)")
                            
                            # Update progress every second
                            current_time = time.time()
                            if current_time - last_update > 1:
                                elapsed = current_time - last_update
                                progress = (downloaded / job.total_size * 40) if job.total_size > 0 else min(20 + (downloaded / 1024 / 1024), 40)
                                speed = len(chunk) / elapsed / 1024 / 1024  # MB/s
                                
                                # Log progress every 10 seconds for debugging
                                if chunk_count % 10 == 0:
                                    logger.info(f"Download progress: {downloaded/1024/1024:.1f} MB at {speed:.1f} MB/s")
                                
                                size_text = f"{job.total_size/1024/1024:.1f} MB" if job.total_size > 0 else "unknown size"
                                await self._update_job(
                                    job, "downloading", progress,
                                    f"Downloading... {downloaded/1024/1024:.1f}/{size_text} ({speed:.2f} MB/s)",
                                    {"downloaded": downloaded, "total": job.total_size, "speed": speed}
                                )
                                last_update = current_time
                
                # Log download completion
                final_size = temp_file.stat().st_size
                logger.info(f"Download completed! Final size: {final_size/1024/1024:.1f} MB ({chunk_count} chunks)")
                
                # Verify download
                if final_size == 0:
                    raise Exception("Downloaded file is empty")
                
                # Quick validation
                with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                    first_line = f.readline().strip()
                    if not first_line.startswith('#EXTM3U'):
                        logger.warning(f"File may not be M3U format. First line: {first_line[:100]}")
                    else:
                        logger.info("File validated as M3U format")
                
                await self._update_job(job, "downloading", 45, f"Download completed ({final_size/1024/1024:.1f} MB)")
                return temp_file
                
            except httpx.ConnectError:
                raise Exception("Unable to connect to server")
            except httpx.TimeoutException:
                raise Exception("Download timed out - you can retry to resume")
            except Exception as e:
                # Save progress for resume
                if temp_file.exists() and temp_file.stat().st_size > 0:
                    logger.info(f"Download interrupted at {temp_file.stat().st_size} bytes, can resume")
                raise
    
    async def _import_channels(self, job: ImportJob, channels_data: list):
        """Import channels to database"""
        from app.database import SessionLocal
        from app.models.channel import Channel, ChannelGroup
        from app.models.playlist import Playlist
        
        logger.info("Opening database session for channel import")
        db = SessionLocal()
        try:
            # Get existing channels
            logger.info(f"Querying existing channels for playlist {job.playlist_id}")
            existing_channels = {ch.channel_id: ch for ch in 
                               db.query(Channel).filter(Channel.playlist_id == job.playlist_id).all()}
            logger.info(f"Found {len(existing_channels)} existing channels")
            
            logger.info("Querying all channel IDs for uniqueness check")
            all_channel_ids = set(ch.channel_id for ch in db.query(Channel).all())
            logger.info(f"Total channels in database: {len(all_channel_ids)}")
            
            # Process channels
            logger.info("Starting channel processing loop")
            groups_cache = {}
            processed = 0
            total = len(channels_data)
            start_time = time.time()
            
            for ch_data in channels_data:
                # Get or create group
                group_name = ch_data.get('group_title', 'Uncategorized')
                if group_name not in groups_cache:
                    group = db.query(ChannelGroup).filter(ChannelGroup.name == group_name).first()
                    if not group:
                        group = ChannelGroup(name=group_name)
                        db.add(group)
                        db.flush()
                    groups_cache[group_name] = group
                
                # Create unique channel ID
                channel_id = ch_data.get('tvg_id', '').strip()
                if not channel_id:
                    channel_id = f"ch_{job.playlist_id}_{processed}"
                
                # Check if exists
                existing = existing_channels.get(channel_id)
                
                if existing:
                    # Update existing channel - ONLY update stream URL and metadata, preserve user settings
                    existing.stream_url = ch_data['stream_url']  # Always update stream URL
                    
                    # Only update other fields if they're empty (preserve user modifications)
                    if not existing.name:
                        existing.name = ch_data['name']
                    if not existing.number:
                        existing.number = ch_data.get('channel_number')
                    if not existing.logo_url:
                        existing.logo_url = ch_data.get('tvg_logo')
                    if not existing.epg_channel_id:
                        existing.epg_channel_id = ch_data.get('tvg_id')
                    
                    # Update group only if channel hasn't been manually moved
                    if existing.group_id == groups_cache.get(ch_data.get('group_title', 'Uncategorized'), existing.group).id:
                        existing.group_id = groups_cache[group_name].id
                    
                    existing.country = ch_data.get('tvg_country', '')
                    existing.language = ch_data.get('tvg_language', '')
                    del existing_channels[channel_id]
                else:
                    # Make unique if needed
                    if channel_id in all_channel_ids:
                        original_id = channel_id
                        counter = 1
                        while channel_id in all_channel_ids:
                            channel_id = f"{original_id}_p{job.playlist_id}_{counter}"
                            counter += 1
                    
                    # Create new
                    channel = Channel(
                        channel_id=channel_id,
                        name=ch_data['name'],
                        number=ch_data.get('channel_number'),
                        logo_url=ch_data.get('tvg_logo'),
                        stream_url=ch_data['stream_url'],
                        group_id=groups_cache[group_name].id,
                        epg_channel_id=ch_data.get('tvg_id'),
                        playlist_id=job.playlist_id,
                        country=ch_data.get('tvg_country', ''),
                        language=ch_data.get('tvg_language', '')
                    )
                    db.add(channel)
                    all_channel_ids.add(channel_id)
                
                processed += 1
                
                # Log progress every 100 channels for debugging
                if processed % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    logger.info(f"Processed {processed}/{total} channels ({rate:.1f} channels/sec)")
                
                # Update progress
                if processed % 50 == 0 or processed == total:
                    progress = 70 + (processed / total * 25)
                    await self._update_job(
                        job, "importing", progress,
                        f"Imported {processed}/{total} channels",
                        {"processed": processed, "total": total}
                    )
            
            logger.info("Committing channel changes to database")
            db.commit()
            processing_time = time.time() - start_time
            logger.info(f"Channel processing completed in {processing_time:.2f} seconds")
            
            # Mark removed channels as inactive instead of deleting
            # This preserves recordings and user settings
            if existing_channels:
                logger.info(f"Marking {len(existing_channels)} removed channels as inactive")
                for channel_id, channel in existing_channels.items():
                    channel.is_active = False
                    logger.info(f"Marked channel '{channel.name}' as inactive (no longer in playlist)")
                db.commit()
                logger.info("Inactive channel updates committed")
            
            # Update playlist timestamp
            logger.info(f"Updating playlist {job.playlist_id} timestamp")
            playlist = db.query(Playlist).filter(Playlist.id == job.playlist_id).first()
            if playlist:
                playlist.last_updated = datetime.utcnow()
                db.commit()
                logger.info("Playlist timestamp updated")
            
            # Auto-map EPG if URL provided
            if job.epg_url:
                logger.info(f"Starting EPG auto-mapping for URL: {job.epg_url}")
                await self._auto_map_epg(job, db)
                logger.info("EPG auto-mapping completed")
            
        finally:
            logger.info("Closing database session")
            db.close()
    
    async def _auto_map_epg(self, job: ImportJob, db):
        """Auto-map EPG channels"""
        try:
            await self._update_job(job, "importing", 95, "Auto-mapping EPG channels...")
            
            from app.utils.epg_auto_mapper import EPGAutoMapper, EPGChannel
            from app.utils.xmltv_parser import XMLTVParser
            
            # Parse EPG
            xmltv_parser = XMLTVParser()
            epg_data = await xmltv_parser.parse_from_url(job.epg_url)
            
            # Convert to EPGChannel objects
            epg_channels = []
            for ch_id, ch_data in epg_data.get('channels', {}).items():
                epg_channels.append(EPGChannel(
                    id=ch_id,
                    display_names=ch_data.get('display_names', []),
                    icon=ch_data.get('icon')
                ))
            
            # Auto-map
            mapper = EPGAutoMapper(db)
            matches = mapper.auto_map_channels(epg_channels)
            applied = mapper.apply_mappings(matches, update_existing=True)
            
            job.details['epg_mapped'] = applied
            
        except Exception as e:
            logger.error(f"EPG auto-mapping failed: {e}")
            job.details['epg_error'] = str(e)
    
    async def _update_job(self, job: ImportJob, status: str, progress: float, 
                         message: str, details: dict = None):
        """Update job status and notify callback"""
        job.status = status
        job.progress = progress
        job.message = message
        job.updated_at = datetime.utcnow()
        
        if details:
            job.details.update(details)
        
        # Send progress update through WebSocket
        progress_data = {
            "type": "import_progress",
            "import_id": job.id,
            "status": status,
            "progress": progress,
            "message": message,
            "details": details or {},
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat()
        }
        # Broadcast to all connected users
        for user_id in list(ws_manager.active_connections.keys()):
            await ws_manager.broadcast_to_user(progress_data, user_id)
        
        # Call callback if exists
        callback = self.callbacks.get(job.id)
        if callback:
            try:
                await callback(status, progress, message, details)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def cancel_import(self, import_id: str) -> bool:
        """Cancel an import job"""
        task = self.active_tasks.get(import_id)
        if task and not task.done():
            task.cancel()
            
            job = self.jobs.get(import_id)
            if job:
                job.status = "cancelled"
                job.message = "Import cancelled by user"
            
            return True
        return False
    
    def get_active_imports(self) -> List[dict]:
        """Get all active import jobs"""
        active_jobs = []
        for job_id, job in self.jobs.items():
            if job.status in ['pending', 'downloading', 'parsing', 'importing']:
                active_jobs.append(self.get_job_status(job_id))
        return active_jobs
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up old completed/failed jobs"""
        cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        
        to_remove = []
        for job_id, job in self.jobs.items():
            if job.created_at.timestamp() < cutoff and job.status in ['completed', 'failed', 'cancelled']:
                to_remove.append(job_id)
        
        for job_id in to_remove:
            self.jobs.pop(job_id, None)
            self.callbacks.pop(job_id, None)

# Global import manager instance
import_manager = ImportManager()