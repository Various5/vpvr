from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User, UserRole
from app.models.import_source import ImportSource
from app.services.import_service import import_service
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ImportSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    m3u_url: Optional[str] = None
    epg_url: Optional[str] = None
    import_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    auto_refresh: bool = False
    refresh_interval: int = Field(default=86400, ge=3600)  # Min 1 hour
    refresh_time: Optional[str] = None

class ImportSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    epg_url: Optional[str] = None
    import_settings: Optional[Dict[str, Any]] = None
    auto_refresh: Optional[bool] = None
    refresh_interval: Optional[int] = Field(None, ge=3600)
    refresh_time: Optional[str] = None
    is_active: Optional[bool] = None

class ImportSourceResponse(BaseModel):
    id: int
    name: str
    source_type: str
    m3u_url: Optional[str]
    epg_url: Optional[str]
    import_settings: Dict[str, Any]
    is_active: bool
    last_import_at: Optional[str]
    last_import_status: Optional[str]
    last_import_details: Optional[Dict[str, Any]]
    next_refresh_at: Optional[str]
    total_channels: int
    active_channels: int
    failed_channels: int
    auto_refresh: bool
    refresh_interval: int
    refresh_time: Optional[str]
    created_at: str
    updated_at: Optional[str]
    original_filename: Optional[str]
    file_size: Optional[int]
    
    class Config:
        from_attributes = True

@router.get("/", response_model=Dict[str, Any])
async def get_import_sources(
    skip: int = 0,
    limit: int = 50,
    active_only: bool = True,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all import sources with pagination"""
    sources, total = await import_service.get_sources(
        db, skip, limit, active_only, search
    )
    
    return {
        "sources": [source.to_dict() for source in sources],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/stats", response_model=Dict[str, Any])
async def get_import_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get import statistics"""
    return await import_service.get_source_stats(db)

@router.get("/active")
async def get_active_imports(
    current_user: User = Depends(get_current_user)
):
    """Get all active import jobs"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from app.utils.import_manager import import_manager
    active_imports = import_manager.get_active_imports()
    return {"active_imports": active_imports}

@router.get("/{source_id}", response_model=ImportSourceResponse)
async def get_import_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific import source"""
    source = db.query(ImportSource).filter(ImportSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Import source not found")
    
    return ImportSourceResponse(**source.to_dict())

@router.post("/", response_model=ImportSourceResponse)
async def create_import_source(
    source_data: ImportSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new import source from URL"""
    try:
        source = await import_service.create_source(
            db=db,
            name=source_data.name,
            m3u_url=source_data.m3u_url,
            epg_url=source_data.epg_url,
            import_settings=source_data.import_settings,
            auto_refresh=source_data.auto_refresh,
            refresh_interval=source_data.refresh_interval,
            created_by_id=current_user.id
        )
        
        return ImportSourceResponse(**source.to_dict())
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create import source: {e}")
        raise HTTPException(status_code=500, detail="Failed to create import source")

@router.post("/upload", response_model=ImportSourceResponse)
async def upload_import_source(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    m3u_file: Optional[UploadFile] = File(None),
    epg_file: Optional[UploadFile] = File(None),
    epg_url: Optional[str] = Form(None),
    import_settings: str = Form("{}"),
    auto_refresh: bool = Form(False),
    refresh_interval: int = Form(86400),
    auto_import: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Upload M3U/EPG files to create import source"""
    try:
        # Validate files
        if not m3u_file:
            raise HTTPException(status_code=400, detail="M3U file is required")
        
        if not m3u_file.filename.endswith(('.m3u', '.m3u8')):
            raise HTTPException(
                status_code=400, 
                detail="Invalid file type. Only .m3u and .m3u8 files are allowed"
            )
        
        if epg_file and not epg_file.filename.endswith(('.xml', '.gz')):
            raise HTTPException(
                status_code=400,
                detail="Invalid EPG file type. Only .xml and .gz files are allowed"
            )
        
        # Parse import settings
        try:
            settings = json.loads(import_settings)
        except:
            settings = {}
        
        # Create source
        source = await import_service.create_source(
            db=db,
            name=name,
            m3u_file=m3u_file,
            epg_file=epg_file,
            epg_url=epg_url,
            import_settings=settings,
            auto_refresh=auto_refresh,
            refresh_interval=refresh_interval,
            created_by_id=current_user.id
        )
        
        # Auto-import if requested
        if auto_import:
            background_tasks.add_task(
                import_service.import_from_source,
                db,
                source.id,
                current_user.id
            )
        
        return ImportSourceResponse(**source.to_dict())
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to upload import source: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload import source")

@router.put("/{source_id}", response_model=ImportSourceResponse)
async def update_import_source(
    source_id: int,
    source_data: ImportSourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an import source"""
    try:
        source = await import_service.update_source(
            db=db,
            source_id=source_id,
            **source_data.dict(exclude_unset=True)
        )
        
        return ImportSourceResponse(**source.to_dict())
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update import source: {e}")
        raise HTTPException(status_code=500, detail="Failed to update import source")

@router.delete("/{source_id}")
async def delete_import_source(
    source_id: int,
    delete_channels: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an import source"""
    success = await import_service.delete_source(
        db, source_id, delete_channels
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Import source not found")
    
    return {"message": "Import source deleted successfully"}

@router.post("/{source_id}/import")
async def import_from_source(
    source_id: int,
    background_tasks: BackgroundTasks,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Trigger import from a source"""
    try:
        job_id = await import_service.import_from_source(
            db=db,
            source_id=source_id,
            user_id=current_user.id,
            force_refresh=force_refresh
        )
        
        return {
            "message": "Import started",
            "import_id": job_id,
            "source_id": source_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start import: {e}")
        raise HTTPException(status_code=500, detail="Failed to start import")

@router.post("/refresh-all")
async def refresh_all_sources(
    background_tasks: BackgroundTasks,
    force_all: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Refresh all sources that need updating"""
    job_ids = await import_service.refresh_sources(db, force_all)
    
    return {
        "message": f"Started refresh for {len(job_ids)} sources",
        "job_ids": job_ids
    }

@router.post("/validate")
async def validate_import_source(
    m3u_url: Optional[str] = None,
    epg_url: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Validate import source URLs before creating"""
    if not m3u_url:
        raise HTTPException(status_code=400, detail="M3U URL is required")
    
    result = await import_service.validate_source(
        m3u_url=m3u_url,
        epg_url=epg_url
    )
    
    return result

@router.get("/{source_id}/channels")
async def get_source_channels(
    source_id: int,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get channels from a specific source"""
    # Get source
    source = db.query(ImportSource).filter(ImportSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Import source not found")
    
    # Get associated playlist
    from app.models.playlist import Playlist
    from app.models.channel import Channel
    
    playlist = db.query(Playlist).filter(
        Playlist.name == f"Source: {source.name}"
    ).first()
    
    if not playlist:
        return {"channels": [], "total": 0}
    
    # Get channels
    query = db.query(Channel).filter(Channel.playlist_id == playlist.id)
    
    if active_only:
        query = query.filter(Channel.is_active == True)
    
    total = query.count()
    channels = query.offset(skip).limit(limit).all()
    
    return {
        "channels": [
            {
                "id": ch.id,
                "channel_id": ch.channel_id,
                "name": ch.name,
                "number": ch.number,
                "logo_url": ch.logo_url,
                "group_name": ch.group.name if ch.group else None,
                "epg_channel_id": ch.epg_channel_id,
                "is_active": ch.is_active
            }
            for ch in channels
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

# Import status response model
class ImportStatusResponse(BaseModel):
    import_id: str
    status: str
    progress: float
    message: str
    details: Dict[str, Any]
    error: Optional[str]
    created_at: str
    updated_at: str

@router.get("/status/{import_id}", response_model=ImportStatusResponse)
async def get_import_status(
    import_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the status of an import job"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from app.utils.import_manager import import_manager
    status = import_manager.get_job_status(import_id)
    if not status:
        raise HTTPException(status_code=404, detail="Import job not found")
        
    return ImportStatusResponse(**status)

@router.post("/cancel/{import_id}")
async def cancel_import(
    import_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel an active import job"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from app.utils.import_manager import import_manager
    success = import_manager.cancel_import(import_id)
    if not success:
        raise HTTPException(status_code=404, detail="Import job not found or already completed")
        
    return {"message": "Import cancelled successfully"}