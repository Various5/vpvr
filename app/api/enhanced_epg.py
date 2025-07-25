"""Enhanced EPG API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.auth.dependencies import require_admin, require_manager_or_admin, get_current_user
from app.models import User, EPGSource, EPGChannelMapping
from app.services.enhanced_epg_service import EnhancedEPGService
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class EPGSourceCreate(BaseModel):
    name: str
    url: Optional[str] = None
    type: str = "xmltv"
    priority: int = 0
    auto_map: bool = True
    playlist_id: Optional[int] = None


class EPGSourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    auto_map: Optional[bool] = None


class ChannelMapping(BaseModel):
    channel_id: int
    epg_source_id: int
    epg_channel_id: str


class AutoMapRequest(BaseModel):
    force: bool = False


@router.get("/status")
async def get_epg_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get comprehensive EPG status for all channels."""
    service = EnhancedEPGService(db)
    return service.get_epg_status()


@router.get("/sources")
async def list_epg_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all EPG sources."""
    sources = db.query(EPGSource).order_by(EPGSource.priority.desc()).all()
    return sources


@router.post("/sources")
async def create_epg_source(
    source: EPGSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new EPG source."""
    # Check if source with same URL already exists
    if source.url:
        existing = db.query(EPGSource).filter(EPGSource.url == source.url).first()
        if existing:
            raise HTTPException(400, "EPG source with this URL already exists")
    
    epg_source = EPGSource(
        name=source.name,
        url=source.url,
        type=source.type,
        priority=source.priority,
        auto_map=source.auto_map,
        playlist_id=source.playlist_id
    )
    db.add(epg_source)
    db.commit()
    db.refresh(epg_source)
    
    return epg_source


@router.patch("/sources/{source_id}")
async def update_epg_source(
    source_id: int,
    update: EPGSourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an EPG source."""
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "EPG source not found")
    
    if update.name is not None:
        source.name = update.name
    if update.url is not None:
        source.url = update.url
    if update.is_active is not None:
        source.is_active = update.is_active
    if update.priority is not None:
        source.priority = update.priority
    if update.auto_map is not None:
        source.auto_map = update.auto_map
    
    db.commit()
    db.refresh(source)
    
    return source


@router.delete("/sources/{source_id}")
async def delete_epg_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an EPG source."""
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "EPG source not found")
    
    db.delete(source)
    db.commit()
    
    return {"message": "EPG source deleted successfully"}


@router.post("/sources/{source_id}/import")
async def import_epg_data(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Import EPG data from a source."""
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "EPG source not found")
    
    if source.import_status == 'importing':
        raise HTTPException(400, "Import already in progress")
    
    # Run import in background
    async def run_import():
        service = EnhancedEPGService(db)
        await service.import_epg_data(source_id)
    
    background_tasks.add_task(run_import)
    
    return {"message": "EPG import started", "source_id": source_id}


@router.post("/sources/{source_id}/auto-map")
async def auto_map_channels(
    source_id: int,
    request: AutoMapRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Automatically map channels to EPG data."""
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "EPG source not found")
    
    service = EnhancedEPGService(db)
    result = service.auto_map_channels(source_id, force=request.force)
    
    return result


@router.get("/mappings")
async def list_channel_mappings(
    channel_id: Optional[int] = None,
    epg_source_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List channel EPG mappings."""
    query = db.query(EPGChannelMapping)
    
    if channel_id:
        query = query.filter(EPGChannelMapping.channel_id == channel_id)
    if epg_source_id:
        query = query.filter(EPGChannelMapping.epg_source_id == epg_source_id)
    
    mappings = query.all()
    return mappings


@router.post("/mappings")
async def create_channel_mapping(
    mapping: ChannelMapping,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a manual channel EPG mapping."""
    service = EnhancedEPGService(db)
    result = service.manual_map_channel(
        mapping.channel_id,
        mapping.epg_source_id,
        mapping.epg_channel_id
    )
    
    return result


@router.delete("/mappings/{channel_id}/{epg_source_id}")
async def delete_channel_mapping(
    channel_id: int,
    epg_source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a channel EPG mapping."""
    service = EnhancedEPGService(db)
    success = service.remove_channel_mapping(channel_id, epg_source_id)
    
    if not success:
        raise HTTPException(404, "Mapping not found")
    
    return {"message": "Mapping deleted successfully"}


@router.post("/channels/{channel_id}/lock-mapping")
async def lock_channel_mapping(
    channel_id: int,
    locked: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Lock/unlock a channel's EPG mapping to prevent auto-mapping changes."""
    from app.models import Channel
    
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    
    channel.epg_mapping_locked = locked
    db.commit()
    
    return {
        "channel_id": channel_id,
        "epg_mapping_locked": locked,
        "message": f"Channel mapping {'locked' if locked else 'unlocked'}"
    }


@router.get("/sources/{source_id}/channels")
async def get_epg_source_channels(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get available channels from an EPG source."""
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "EPG source not found")
    
    # This would parse the EPG source and return available channels
    # For now, return a placeholder
    return {
        "source_id": source_id,
        "channels": [],
        "message": "Channel listing not yet implemented"
    }


@router.get("/import-logs")
async def get_import_logs(
    epg_source_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get EPG import logs."""
    from app.models import EPGImportLog
    
    query = db.query(EPGImportLog)
    
    if epg_source_id:
        query = query.filter(EPGImportLog.epg_source_id == epg_source_id)
    
    logs = query.order_by(EPGImportLog.started_at.desc()).limit(limit).all()
    return logs