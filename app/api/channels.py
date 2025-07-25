from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.channel import Channel, ChannelGroup
from app.models.playlist import Playlist
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from app.utils.m3u_parser import M3UParser
from pydantic import BaseModel
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ChannelResponse(BaseModel):
    id: int
    channel_id: str
    name: str
    number: Optional[str]
    logo_url: Optional[str]
    group_name: Optional[str]
    epg_channel_id: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

class PlaylistCreate(BaseModel):
    name: str
    url: str
    epg_url: Optional[str] = None
    auto_map_epg: bool = False  # Explicit opt-in for auto-mapping

class ChannelUpdate(BaseModel):
    name: Optional[str]
    number: Optional[str]
    epg_channel_id: Optional[str]
    is_active: Optional[bool]

class ChannelGroupResponse(BaseModel):
    id: int
    name: str
    channel_count: int

@router.get("/", response_model=List[ChannelResponse])
async def get_channels(
    skip: int = 0,
    limit: int = 100,  # Reduced default limit from 10000 to 100
    group: Optional[str] = None,
    search: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from sqlalchemy.orm import joinedload
    
    # Use joinedload to eager load the group relationship
    query = db.query(Channel).options(joinedload(Channel.group))
    
    if active_only:
        query = query.filter(Channel.is_active == True)
    
    if group:
        query = query.join(ChannelGroup).filter(ChannelGroup.name == group)
    
    if search:
        query = query.filter(Channel.name.ilike(f"%{search}%"))
    
    channels = query.offset(skip).limit(limit).all()
    
    return [
        ChannelResponse(
            id=ch.id,
            channel_id=ch.channel_id,
            name=ch.name,
            number=ch.number,
            logo_url=ch.logo_url,
            group_name=ch.group.name if ch.group else None,
            epg_channel_id=ch.epg_channel_id,
            is_active=ch.is_active
        )
        for ch in channels
    ]

# Removed duplicate /groups endpoint - using the one at line 1091 instead

@router.get("/playlists")
async def get_playlists(
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    from app.models.epg_source import EPGSource
    playlists = db.query(Playlist).order_by(Playlist.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "url": p.url,
            "last_updated": p.last_updated.isoformat() if p.last_updated else None,
            "created_at": p.created_at.isoformat(),
            "channel_count": db.query(Channel).filter(Channel.playlist_id == p.id).count(),
            "epg_sources": db.query(EPGSource).filter(EPGSource.playlist_id == p.id).all()
        }
        for p in playlists
    ]

@router.delete("/playlists/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Delete all channels from this playlist
    db.query(Channel).filter(Channel.playlist_id == playlist_id).delete()
    
    # Delete the playlist
    db.delete(playlist)
    db.commit()
    
    return {"message": "Playlist deleted successfully"}

@router.post("/playlists/{playlist_id}/cancel")
async def cancel_playlist_import(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    from app.utils.import_manager import import_manager
    
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Try to find and cancel active import
    import_id = f"playlist_{playlist_id}"
    cancelled = import_manager.cancel_import(import_id)
    
    if not cancelled:
        # If no active import, clean up any partial data
        db.query(Channel).filter(Channel.playlist_id == playlist_id).delete()
        db.commit()
    
    return {"message": "Import cancelled successfully"}

@router.post("/imports/{import_id}/cancel")
async def cancel_import_job(
    import_id: str,
    current_user = Depends(require_admin)
):
    """Cancel a specific import job"""
    from app.utils.import_manager import import_manager
    
    if import_manager.cancel_import(import_id):
        return {"message": "Import cancelled successfully"}
    else:
        raise HTTPException(status_code=404, detail="Import job not found or already completed")

@router.post("/imports/{import_id}/retry")
async def retry_import_job(
    import_id: str,
    background_tasks: BackgroundTasks,
    current_user = Depends(require_admin)
):
    """Retry a failed or cancelled import job"""
    from app.utils.import_manager import import_manager
    
    job = import_manager.get_job(import_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    
    if job.status not in ['failed', 'cancelled']:
        raise HTTPException(status_code=400, detail="Can only retry failed or cancelled imports")
    
    # Reset job status
    job.status = "pending"
    job.progress = 0
    job.message = "Retrying import..."
    job.error = None
    
    # Create progress callback
    async def progress_callback(status: str, progress: float, message: str, details: dict = None):
        from app.api.websocket import send_import_update
        await send_import_update(str(current_user.id), import_id, status, progress, message, details)
    
    # Restart import
    background_tasks.add_task(
        import_manager.start_import,
        import_id,
        progress_callback
    )
    
    return {"message": "Import retry started", "import_id": import_id}

@router.get("/imports/active")
async def get_active_imports(
    current_user = Depends(get_current_user)
):
    """Get all active import jobs"""
    from app.utils.import_manager import import_manager
    
    active_jobs = []
    for job_id, job in import_manager.jobs.items():
        if job.status not in ['completed', 'failed', 'cancelled']:
            active_jobs.append(import_manager.get_job_status(job_id))
    
    return {"active_imports": active_jobs}

@router.post("/playlists/{playlist_id}/refresh")
async def refresh_playlist(
    playlist_id: int,
    background_tasks: BackgroundTasks,
    auto_map_epg: bool = False,  # Explicit opt-in for auto-mapping
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if not playlist.url or playlist.url.startswith("file://"):
        raise HTTPException(status_code=400, detail="Cannot refresh uploaded playlists")
    
    # Get EPG URL if available
    from app.models.epg_source import EPGSource
    epg_source = db.query(EPGSource).filter(EPGSource.playlist_id == playlist_id).first()
    epg_url = epg_source.url if epg_source else None
    
    # Use import manager for refresh
    from app.utils.import_manager import import_manager
    import time
    import_id = f"playlist_refresh_{playlist_id}_{int(time.time())}"
    
    # Create import job
    job = import_manager.create_job(
        import_id=import_id,
        playlist_id=playlist_id,
        url=playlist.url,
        epg_url=epg_url if auto_map_epg else None  # Only pass EPG if auto-map requested
    )
    
    # Create progress callback
    async def progress_callback(status: str, progress: float, message: str, details: dict = None):
        from app.api.websocket import send_import_update
        await send_import_update(str(current_user.id), import_id, status, progress, message, details)
    
    # Start refresh
    background_tasks.add_task(
        import_manager.start_import,
        import_id,
        progress_callback
    )
    
    return {"message": "Playlist refresh started", "import_id": import_id}

@router.patch("/playlists/{playlist_id}")
async def update_playlist_settings(
    playlist_id: int,
    update_interval_hours: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if update_interval_hours is not None:
        playlist.update_interval = update_interval_hours * 3600  # Convert to seconds
    
    if is_active is not None:
        playlist.is_active = is_active
    
    db.commit()
    db.refresh(playlist)
    
    return {"message": "Playlist settings updated"}

@router.get("/groups", response_model=List[ChannelGroupResponse])
async def get_channel_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all channel groups with counts"""
    from sqlalchemy import func
    
    groups = db.query(
        ChannelGroup.id,
        ChannelGroup.name,
        func.count(Channel.id).label("channel_count")
    ).outerjoin(Channel).group_by(ChannelGroup.id).all()
    
    return [
        {
            "id": g.id,
            "name": g.name,
            "channel_count": g.channel_count
        }
        for g in groups
    ]

@router.post("/groups")
async def create_channel_group(
    name: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new channel group"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if group exists
    existing = db.query(ChannelGroup).filter(
        ChannelGroup.name == name
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Group already exists")
    
    group = ChannelGroup(name=name)
    db.add(group)
    db.commit()
    db.refresh(group)
    
    return {"id": group.id, "name": group.name}

@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    return ChannelResponse(
        id=channel.id,
        channel_id=channel.channel_id,
        name=channel.name,
        number=channel.number,
        logo_url=channel.logo_url,
        group_name=channel.group.name if channel.group else None,
        epg_channel_id=channel.epg_channel_id,
        is_active=channel.is_active
    )

@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    channel_update: ChannelUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if channel_update.name is not None:
        channel.name = channel_update.name
    if channel_update.number is not None:
        channel.number = channel_update.number
    if channel_update.epg_channel_id is not None:
        channel.epg_channel_id = channel_update.epg_channel_id
    if channel_update.is_active is not None:
        channel.is_active = channel_update.is_active
    
    db.commit()
    db.refresh(channel)
    
    return ChannelResponse(
        id=channel.id,
        channel_id=channel.channel_id,
        name=channel.name,
        number=channel.number,
        logo_url=channel.logo_url,
        group_name=channel.group.name if channel.group else None,
        epg_channel_id=channel.epg_channel_id,
        is_active=channel.is_active
    )

@router.post("/playlists/import")
async def import_playlist(
    playlist_data: PlaylistCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    # Create playlist entry
    playlist = Playlist(
        name=playlist_data.name,
        url=playlist_data.url
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    
    # Create EPG source if provided
    if playlist_data.epg_url:
        from app.models.epg_source import EPGSource
        epg_source = EPGSource(
            name=f"{playlist_data.name} EPG",
            url=playlist_data.epg_url,
            playlist_id=playlist.id
        )
        db.add(epg_source)
        db.commit()
    
    # Use import manager for robust background import
    from app.utils.import_manager import import_manager
    import_id = f"playlist_{playlist.id}"
    
    # Create import job
    job = import_manager.create_job(
        import_id=import_id,
        playlist_id=playlist.id,
        url=playlist_data.url,
        epg_url=playlist_data.epg_url if playlist_data.auto_map_epg else None  # Only pass EPG if auto-map requested
    )
    
    # Create progress callback
    async def progress_callback(status: str, progress: float, message: str, details: dict = None):
        from app.api.websocket import send_import_update
        await send_import_update(str(current_user.id), import_id, status, progress, message, details)
    
    # Start import (will run independently)
    background_tasks.add_task(
        import_manager.start_import,
        import_id,
        progress_callback
    )
    
    return {"message": "Playlist import started", "playlist_id": playlist.id, "import_id": import_id}

async def import_channels_from_playlist(playlist_id: int, url: str, user_id: int = None, import_id: str = None, epg_url: str = None):
    from app.api.websocket import send_import_update
    from app.database import SessionLocal
    from app.utils.epg_auto_mapper import EPGAutoMapper, EPGChannel
    parser = M3UParser()
    
    # Create a new database session for the background task
    db = SessionLocal()
    
    # Create progress callback
    async def progress_callback(status: str, progress: int, message: str, details: dict = None):
        if user_id and import_id:
            await send_import_update(str(user_id), import_id, status, progress, message, details)
    
    try:
        # Send start notification
        if user_id and import_id:
            await send_import_update(str(user_id), import_id, "started", 0, "Starting playlist import...")
        
        channels_data = await parser.parse_from_url(url, progress_callback)
        total_channels = len(channels_data)
        
        if user_id and import_id:
            await send_import_update(str(user_id), import_id, "progress", 10, 
                                   f"Found {total_channels} channels", 
                                   {"total": total_channels})
        
        # Don't delete existing channels - we'll update them instead
        # This preserves any custom settings or recordings
        existing_channels = {ch.channel_id: ch for ch in 
                           db.query(Channel).filter(Channel.playlist_id == playlist_id).all()}
        
        # Also get ALL channels to check for global duplicates
        all_channel_ids = set(ch.channel_id for ch in db.query(Channel).all())
        
        # Get or create groups
        groups_cache = {}
        processed = 0
        
        for ch_data in channels_data:
            group_name = ch_data.get('group_title', 'Uncategorized')
            
            if group_name not in groups_cache:
                group = db.query(ChannelGroup).filter(ChannelGroup.name == group_name).first()
                if not group:
                    group = ChannelGroup(name=group_name)
                    db.add(group)
                    db.flush()  # Flush to get ID without committing
                groups_cache[group_name] = group
            
            # Create channel with unique ID
            channel_id = ch_data.get('tvg_id', '').strip()
            if not channel_id:
                # Generate unique ID based on playlist and position
                channel_id = f"ch_{playlist_id}_{processed}"
            
            # Check if this channel already exists for this playlist
            existing = existing_channels.get(channel_id)
            
            if existing:
                # Update existing channel
                existing.name = ch_data['name']
                existing.number = ch_data.get('channel_number')
                existing.logo_url = ch_data.get('tvg_logo')
                existing.stream_url = ch_data['stream_url']
                existing.group_id = groups_cache[group_name].id
                existing.epg_channel_id = ch_data.get('tvg_id')
                existing.country = ch_data.get('tvg_country', '')
                existing.language = ch_data.get('tvg_language', '')
                # Remove from dict so we know it's still active
                del existing_channels[channel_id]
            else:
                # Check if channel_id exists globally (from another playlist)
                # but not in our existing_channels for this playlist
                if channel_id in all_channel_ids and channel_id not in existing_channels:
                    # Make the ID unique by adding playlist suffix
                    original_id = channel_id
                    counter = 1
                    while channel_id in all_channel_ids:
                        channel_id = f"{original_id}_p{playlist_id}_{counter}"
                        counter += 1
                
                # Create new channel
                channel = Channel(
                    channel_id=channel_id,
                    name=ch_data['name'],
                    number=ch_data.get('channel_number'),
                    logo_url=ch_data.get('tvg_logo'),
                    stream_url=ch_data['stream_url'],
                    group_id=groups_cache[group_name].id,
                    epg_channel_id=ch_data.get('tvg_id'),
                    playlist_id=playlist_id,
                    country=ch_data.get('tvg_country', ''),
                    language=ch_data.get('tvg_language', '')
                )
                db.add(channel)
                # Add to our tracking set
                all_channel_ids.add(channel_id)
            
            processed += 1
            
            # Send progress update every 10 channels
            if processed % 10 == 0 or processed == total_channels:
                progress = int((processed / total_channels) * 70) + 10  # Leave room for EPG mapping
                if user_id and import_id:
                    await send_import_update(str(user_id), import_id, "progress", progress,
                                           f"Imported {processed}/{total_channels} channels",
                                           {"processed": processed, "total": total_channels})
        
        db.commit()
        
        # Delete channels that are no longer in the playlist
        if existing_channels:
            # These channels were not in the new import, so remove them
            for channel_id, channel in existing_channels.items():
                db.delete(channel)
            db.commit()
        
        # Auto-map EPG channels if EPG URL provided
        if epg_url:
            if user_id and import_id:
                await send_import_update(str(user_id), import_id, "progress", 85,
                                       "Starting EPG auto-mapping...",
                                       {"step": "epg_mapping"})
            
            try:
                # Import EPG data first
                from app.utils.xmltv_parser import XMLTVParser
                xmltv_parser = XMLTVParser()
                epg_data = await xmltv_parser.parse_from_url(epg_url)
                
                # Convert to EPGChannel objects
                epg_channels = []
                for ch_id, ch_data in epg_data.get('channels', {}).items():
                    epg_channels.append(EPGChannel(
                        id=ch_id,
                        display_names=ch_data.get('display_names', []),
                        icon=ch_data.get('icon')
                    ))
                
                # Perform auto-mapping
                mapper = EPGAutoMapper(db)
                matches = mapper.auto_map_channels(epg_channels)
                applied = mapper.apply_mappings(matches, update_existing=True)
                
                if user_id and import_id:
                    await send_import_update(str(user_id), import_id, "progress", 95,
                                           f"Auto-mapped {applied} channels to EPG data",
                                           {"mapped_channels": applied})
                
            except Exception as e:
                logger.error(f"EPG auto-mapping failed: {e}")
                if user_id and import_id:
                    await send_import_update(str(user_id), import_id, "progress", 90,
                                           f"EPG auto-mapping failed: {str(e)}",
                                           {"epg_error": str(e)})
        
        # Update playlist last_updated
        playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
        if playlist:
            from datetime import datetime
            playlist.last_updated = datetime.utcnow()
            db.commit()
        
        if user_id and import_id:
            await send_import_update(str(user_id), import_id, "completed", 100,
                                   f"Successfully imported {processed} channels",
                                   {"processed": processed, "groups": len(groups_cache)})
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error importing playlist: {e}\n{error_details}")
        
        if user_id and import_id:
            # Send detailed error message with specific solutions
            error_msg = str(e)
            error_type = "unknown"
            
            if "UNIQUE constraint failed" in error_msg:
                error_type = "duplicate_id"
                error_msg = "Duplicate channel IDs detected"
            elif "Server returned status" in error_msg:
                error_type = "server_error"
                error_msg = f"Server error: {error_msg}"
            elif "Downloaded file is empty" in error_msg:
                error_type = "empty_file"
                error_msg = "Empty playlist file"
            elif "Invalid M3U file format" in error_msg:
                error_type = "invalid_format"
                error_msg = "Invalid M3U format"
            elif "timed out" in error_msg.lower():
                error_type = "timeout"
                error_msg = "Connection timeout"
            elif "404" in error_msg:
                error_type = "not_found"
                error_msg = "Playlist not found (404)"
            elif "403" in error_msg:
                error_type = "forbidden"
                error_msg = "Access forbidden (403) - Check credentials"
            elif "401" in error_msg:
                error_type = "unauthorized"
                error_msg = "Unauthorized (401) - Invalid credentials"
            
            await send_import_update(str(user_id), import_id, "failed", 0,
                                   f"Import failed: {error_msg}",
                                   {"error": str(e), "error_type": error_type, "url": url})
    finally:
        db.close()

@router.get("/{channel_id}/stream-url")
async def get_channel_stream_url(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # In production, you might want to proxy this through your server
    # to handle CORS and authentication
    return {"stream_url": channel.stream_url}

@router.get("/{channel_id}/m3u")
async def export_channel_m3u(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    parser = M3UParser()
    channel_data = {
        'tvg_id': channel.epg_channel_id or channel.channel_id,
        'tvg_name': channel.name,
        'tvg_logo': channel.logo_url or '',
        'group_title': channel.group.name if channel.group else '',
        'name': channel.name,
        'stream_url': channel.stream_url
    }
    
    m3u_content = parser.export_channel_m3u(channel_data)
    
    from fastapi.responses import Response
    return Response(content=m3u_content, media_type="application/x-mpegurl")

@router.post("/playlists/upload")
async def upload_playlist(
    name: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    epg_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    # Validate file type
    if not file.filename.endswith(('.m3u', '.m3u8')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only .m3u and .m3u8 files are allowed"
        )
    
    # Read file content
    content = await file.read()
    try:
        content_str = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            content_str = content.decode('latin-1')
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to decode file content"
            )
    
    # Save to temporary file
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.m3u', delete=False) as tmp_file:
        tmp_file.write(content_str)
        tmp_path = tmp_file.name
    
    # Create playlist entry
    playlist = Playlist(
        name=name,
        url=f"file://{tmp_path}"  # Store as file URL
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    
    # Handle EPG file if provided
    epg_path = None
    if epg_file:
        # Validate EPG file type
        if not epg_file.filename.endswith(('.xml', '.gz')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid EPG file type. Only .xml and .gz files are allowed"
            )
        
        # Read and save EPG file
        epg_content = await epg_file.read()
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix=os.path.splitext(epg_file.filename)[1], delete=False) as epg_tmp:
            epg_tmp.write(epg_content)
            epg_path = epg_tmp.name
        
        # Create EPG source entry
        from app.models.epg_source import EPGSource
        epg_source = EPGSource(
            name=f"{name} EPG",
            url=f"file://{epg_path}",
            playlist_id=playlist.id
        )
        db.add(epg_source)
        db.commit()
    
    # Import channels in background
    import_id = f"playlist_file_{playlist.id}"
    background_tasks.add_task(import_channels_from_file, playlist.id, tmp_path, current_user.id, import_id)
    
    return {"message": "Playlist uploaded successfully", "playlist_id": playlist.id}

async def import_channels_from_file(playlist_id: int, file_path: str, user_id: int = None, import_id: str = None):
    from app.api.websocket import send_import_update
    from app.database import SessionLocal
    parser = M3UParser()
    
    # Create a new database session for the background task
    db = SessionLocal()
    
    try:
        channels_data = parser.parse_from_file(file_path)
        
        # Same import logic as URL import
        groups_cache = {}
        for ch_data in channels_data:
            group_name = ch_data.get('group_title', 'Uncategorized')
            
            if group_name not in groups_cache:
                group = db.query(ChannelGroup).filter(ChannelGroup.name == group_name).first()
                if not group:
                    group = ChannelGroup(name=group_name)
                    db.add(group)
                    db.flush()  # Flush to get ID without committing
                groups_cache[group_name] = group
            
            # Create channel
            channel = Channel(
                channel_id=ch_data.get('tvg_id', f"ch_{len(channels_data)}"),
                name=ch_data['name'],
                number=ch_data.get('channel_number'),
                logo_url=ch_data.get('tvg_logo'),
                stream_url=ch_data['stream_url'],
                group_id=groups_cache[group_name].id,
                epg_channel_id=ch_data.get('tvg_id'),
                playlist_id=playlist_id
            )
            db.add(channel)
        
        db.commit()
        
        # Update playlist last_updated
        playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
        if playlist:
            from datetime import datetime
            playlist.last_updated = datetime.utcnow()
            db.commit()
            
    except Exception as e:
        print(f"Error importing playlist from file: {e}")
    finally:
        db.close()
        # Clean up temporary file
        import os
        if os.path.exists(file_path):
            os.remove(file_path)

# Import statistics and history endpoints
@router.get("/import-stats")
async def get_import_status(
    import_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of a specific import job"""
    from app.utils.import_manager import import_manager
    
    status = import_manager.get_job_status(import_id)
    if not status:
        raise HTTPException(status_code=404, detail="Import job not found")
    
    return status

@router.get("/import-statistics")
async def get_import_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get import statistics for the dashboard"""
    from sqlalchemy import func
    from app.models.epg_source import EPGSource
    from app.utils.import_manager import import_manager
    
    # Count total playlists
    total_playlists = db.query(Playlist).count()
    
    # Count total EPG sources
    total_epg_sources = db.query(EPGSource).count()
    
    # Count total channels
    total_channels = db.query(Channel).count()
    
    # Count total groups
    total_groups = db.query(ChannelGroup).count()
    
    # Get channel distribution by group
    channel_distribution = db.query(
        ChannelGroup.name,
        func.count(Channel.id).label('count')
    ).join(Channel).group_by(ChannelGroup.name).all()
    
    # Get recent imports (playlists by last_updated)
    recent_imports = db.query(Playlist).order_by(
        Playlist.last_updated.desc()
    ).limit(10).all()
    
    # Get active import jobs
    active_jobs = []
    for job_id, job in import_manager.jobs.items():
        if job.status not in ['completed', 'failed', 'cancelled']:
            active_jobs.append({
                "id": job.id,
                "playlist_id": job.playlist_id,
                "status": job.status,
                "progress": job.progress,
                "message": job.message
            })
    
    # Get import history
    import_history = []
    
    # Add active jobs first
    for job_id, job in import_manager.jobs.items():
        import_history.append({
            "id": job.id,
            "name": f"Import {job.playlist_id}",
            "type": "m3u",
            "status": job.status,
            "timestamp": job.created_at.isoformat(),
            "progress": job.progress,
            "message": job.message,
            "error": job.error
        })
    
    # Add completed imports from playlists
    for playlist in recent_imports:
        if not any(h['id'] == f"playlist_{playlist.id}" for h in import_history):
            import_history.append({
                "id": f"playlist_{playlist.id}",
                "name": playlist.name,
                "type": "m3u",
                "status": "completed",
                "timestamp": playlist.last_updated.isoformat() if playlist.last_updated else None,
                "channels_imported": db.query(Channel).filter(Channel.playlist_id == playlist.id).count()
            })
    
    return {
        "total_sources": total_playlists + total_epg_sources,
        "total_playlists": total_playlists,
        "total_epg_sources": total_epg_sources,
        "total_channels": total_channels,
        "total_groups": total_groups,
        "channel_distribution": [
            {"name": item.name, "count": item.count} 
            for item in channel_distribution
        ],
        "import_history": import_history[:10],  # Limit to 10 most recent
        "active_imports": active_jobs
    }

@router.post("/playlists/{playlist_id}/update")
async def update_playlist_manually(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger a playlist update"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if not playlist.url:
        raise HTTPException(status_code=400, detail="Playlist has no URL to update from")
    
    # Generate import ID
    import_id = f"playlist_{playlist_id}_{int(time.time())}"
    
    # Start import in background
    import asyncio
    asyncio.create_task(
        import_channels_from_url(playlist_id, playlist.url, current_user.id, import_id)
    )
    
    return {
        "message": "Playlist update started",
        "import_id": import_id
    }

# Custom Playlist endpoints
class CustomPlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: bool = False
    is_public: bool = False
    channel_ids: List[int] = []

class CustomPlaylistResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    user_id: int
    is_default: bool
    is_public: bool
    channel_count: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

@router.get("/custom-playlists", response_model=List[CustomPlaylistResponse])
async def get_custom_playlists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's custom playlists"""
    from app.models.custom_playlist import CustomPlaylist
    
    playlists = db.query(CustomPlaylist).filter(
        CustomPlaylist.user_id == current_user.id
    ).all()
    
    return [
        CustomPlaylistResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            user_id=p.user_id,
            is_default=p.is_default,
            is_public=p.is_public,
            channel_count=len(p.channels),
            created_at=p.created_at,
            updated_at=p.updated_at
        )
        for p in playlists
    ]

@router.post("/custom-playlists", response_model=CustomPlaylistResponse)
async def create_custom_playlist(
    playlist_data: CustomPlaylistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a custom playlist"""
    from app.models.custom_playlist import CustomPlaylist
    
    # If setting as default, unset other defaults
    if playlist_data.is_default:
        db.query(CustomPlaylist).filter(
            CustomPlaylist.user_id == current_user.id,
            CustomPlaylist.is_default == True
        ).update({"is_default": False})
    
    # Create playlist
    playlist = CustomPlaylist(
        name=playlist_data.name,
        description=playlist_data.description,
        user_id=current_user.id,
        is_default=playlist_data.is_default,
        is_public=playlist_data.is_public
    )
    
    # Add channels
    if playlist_data.channel_ids:
        channels = db.query(Channel).filter(
            Channel.id.in_(playlist_data.channel_ids)
        ).all()
        playlist.channels = channels
    
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    
    return CustomPlaylistResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        user_id=playlist.user_id,
        is_default=playlist.is_default,
        is_public=playlist.is_public,
        channel_count=len(playlist.channels),
        created_at=playlist.created_at,
        updated_at=playlist.updated_at
    )

@router.get("/custom-playlists/{playlist_id}/channels", response_model=List[ChannelResponse])
async def get_custom_playlist_channels(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get channels in a custom playlist"""
    from app.models.custom_playlist import CustomPlaylist
    
    playlist = db.query(CustomPlaylist).filter(
        CustomPlaylist.id == playlist_id,
        CustomPlaylist.user_id == current_user.id
    ).first()
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    return playlist.channels

@router.put("/custom-playlists/{playlist_id}")
async def update_custom_playlist(
    playlist_id: int,
    playlist_data: CustomPlaylistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a custom playlist"""
    from app.models.custom_playlist import CustomPlaylist
    
    playlist = db.query(CustomPlaylist).filter(
        CustomPlaylist.id == playlist_id,
        CustomPlaylist.user_id == current_user.id
    ).first()
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Update fields
    playlist.name = playlist_data.name
    playlist.description = playlist_data.description
    playlist.is_public = playlist_data.is_public
    
    # Handle default flag
    if playlist_data.is_default and not playlist.is_default:
        db.query(CustomPlaylist).filter(
            CustomPlaylist.user_id == current_user.id,
            CustomPlaylist.is_default == True,
            CustomPlaylist.id != playlist_id
        ).update({"is_default": False})
    
    playlist.is_default = playlist_data.is_default
    
    # Update channels
    if playlist_data.channel_ids is not None:
        channels = db.query(Channel).filter(
            Channel.id.in_(playlist_data.channel_ids)
        ).all()
        playlist.channels = channels
    
    db.commit()
    
    return {"message": "Playlist updated successfully"}

@router.delete("/custom-playlists/{playlist_id}")
async def delete_custom_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a custom playlist"""
    from app.models.custom_playlist import CustomPlaylist
    
    playlist = db.query(CustomPlaylist).filter(
        CustomPlaylist.id == playlist_id,
        CustomPlaylist.user_id == current_user.id
    ).first()
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    db.delete(playlist)
    db.commit()
    
    return {"message": "Playlist deleted successfully"}

@router.patch("/{channel_id}")
async def update_channel(
    channel_id: int,
    is_active: Optional[bool] = None,
    group_id: Optional[int] = None,
    name: Optional[str] = None,
    number: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update channel properties"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if is_active is not None:
        channel.is_active = is_active
    if group_id is not None:
        channel.group_id = group_id
    if name is not None:
        channel.name = name
    if number is not None:
        channel.number = number
    
    db.commit()
    
    return {"message": "Channel updated successfully"}

# EPG Auto-mapping endpoints
@router.post("/epg-auto-map")
async def auto_map_epg_channels(
    epg_url: Optional[str] = None,
    playlist_id: Optional[int] = None,
    update_existing: bool = True,
    min_confidence: float = 0.6,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Auto-map channels to EPG data"""
    from app.utils.epg_auto_mapper import EPGAutoMapper, EPGChannel
    from app.utils.xmltv_parser import XMLTVParser
    
    try:
        # Get EPG channels from URL or existing EPG sources
        epg_channels = []
        
        if epg_url:
            # Parse from provided URL
            xmltv_parser = XMLTVParser()
            epg_data = await xmltv_parser.parse_from_url(epg_url)
            
            for ch_id, ch_data in epg_data.get('channels', {}).items():
                epg_channels.append(EPGChannel(
                    id=ch_id,
                    display_names=ch_data.get('display_names', []),
                    icon=ch_data.get('icon')
                ))
        
        elif playlist_id:
            # Get EPG sources for the playlist
            from app.models.epg_source import EPGSource
            epg_sources = db.query(EPGSource).filter(
                EPGSource.playlist_id == playlist_id,
                EPGSource.is_active == True
            ).all()
            
            xmltv_parser = XMLTVParser()
            for source in epg_sources:
                try:
                    epg_data = await xmltv_parser.parse_from_url(source.url)
                    for ch_id, ch_data in epg_data.get('channels', {}).items():
                        epg_channels.append(EPGChannel(
                            id=ch_id,
                            display_names=ch_data.get('display_names', []),
                            icon=ch_data.get('icon')
                        ))
                except Exception as e:
                    logger.warning(f"Failed to parse EPG source {source.id}: {e}")
        
        else:
            # Use all available EPG sources
            from app.models.epg_source import EPGSource
            epg_sources = db.query(EPGSource).filter(EPGSource.is_active == True).all()
            
            xmltv_parser = XMLTVParser()
            for source in epg_sources:
                try:
                    epg_data = await xmltv_parser.parse_from_url(source.url)
                    for ch_id, ch_data in epg_data.get('channels', {}).items():
                        epg_channels.append(EPGChannel(
                            id=ch_id,
                            display_names=ch_data.get('display_names', []),
                            icon=ch_data.get('icon')
                        ))
                except Exception as e:
                    logger.warning(f"Failed to parse EPG source {source.id}: {e}")
        
        if not epg_channels:
            raise HTTPException(status_code=400, detail="No EPG channels found")
        
        # Perform auto-mapping
        mapper = EPGAutoMapper(db)
        matches = mapper.auto_map_channels(epg_channels)
        
        # Filter by minimum confidence
        high_confidence_matches = [m for m in matches if m.confidence >= min_confidence]
        
        # Apply mappings
        applied = mapper.apply_mappings(high_confidence_matches, update_existing)
        
        return {
            "message": f"Auto-mapped {applied} channels",
            "total_matches": len(matches),
            "applied_matches": applied,
            "epg_channels_found": len(epg_channels),
            "matches": [
                {
                    "channel_id": m.channel_id,
                    "epg_channel_id": m.epg_channel_id,
                    "confidence": m.confidence,
                    "match_type": m.match_type,
                    "matched_on": m.matched_on
                }
                for m in high_confidence_matches
            ]
        }
        
    except Exception as e:
        logger.error(f"EPG auto-mapping failed: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-mapping failed: {str(e)}")

@router.get("/epg-mapping-suggestions")
async def get_epg_mapping_suggestions(
    playlist_id: Optional[int] = None,
    min_confidence: float = 0.5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get EPG mapping suggestions for unmapped channels"""
    from app.utils.epg_auto_mapper import EPGAutoMapper, EPGChannel
    from app.utils.xmltv_parser import XMLTVParser
    from app.models.epg_source import EPGSource
    
    try:
        # Get EPG channels from available sources
        epg_channels = []
        epg_sources = db.query(EPGSource)
        
        if playlist_id:
            epg_sources = epg_sources.filter(EPGSource.playlist_id == playlist_id)
        
        epg_sources = epg_sources.filter(EPGSource.is_active == True).all()
        
        xmltv_parser = XMLTVParser()
        for source in epg_sources:
            try:
                epg_data = await xmltv_parser.parse_from_url(source.url)
                for ch_id, ch_data in epg_data.get('channels', {}).items():
                    epg_channels.append(EPGChannel(
                        id=ch_id,
                        display_names=ch_data.get('display_names', []),
                        icon=ch_data.get('icon')
                    ))
            except Exception as e:
                logger.warning(f"Failed to parse EPG source {source.id}: {e}")
        
        if not epg_channels:
            return {"suggestions": [], "message": "No EPG sources available"}
        
        # Get mapping suggestions
        mapper = EPGAutoMapper(db)
        suggestions = mapper.get_mapping_suggestions(epg_channels, min_confidence)
        
        # Get channel details for suggestions
        channel_ids = [s.channel_id for s in suggestions]
        channels = {ch.id: ch for ch in db.query(Channel).filter(Channel.id.in_(channel_ids)).all()}
        
        return {
            "suggestions": [
                {
                    "channel_id": s.channel_id,
                    "channel_name": channels[s.channel_id].name if s.channel_id in channels else "Unknown",
                    "epg_channel_id": s.epg_channel_id,
                    "confidence": s.confidence,
                    "match_type": s.match_type,
                    "matched_on": s.matched_on
                }
                for s in suggestions
            ],
            "total_suggestions": len(suggestions),
            "epg_channels_available": len(epg_channels)
        }
        
    except Exception as e:
        logger.error(f"Failed to get EPG mapping suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")

@router.post("/validate-epg-mappings")
async def validate_epg_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Validate existing EPG mappings"""
    from app.utils.epg_auto_mapper import EPGAutoMapper
    
    mapper = EPGAutoMapper(db)
    issues = mapper.validate_mappings()
    
    return {
        "issues": issues,
        "total_issues": sum(len(issue_list) for issue_list in issues.values())
    }