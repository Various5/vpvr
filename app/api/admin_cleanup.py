"""Admin cleanup API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List
from datetime import datetime, timedelta
from app.database import get_db
from app.auth.dependencies import require_admin
from app.models import User, Channel, ChannelGroup, EPGProgram, EPGSource, Playlist
from pydantic import BaseModel

router = APIRouter()


class CleanupResponse(BaseModel):
    removed: int
    message: str


class DuplicateChannelsResponse(BaseModel):
    duplicates: List[dict]
    total: int


@router.post("/find-duplicates", response_model=DuplicateChannelsResponse)
async def find_duplicate_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Find duplicate channels based on name and URL."""
    # Find channels with duplicate names
    duplicates = db.query(
        Channel.id,
        Channel.name,
        Channel.url,
        func.count(Channel.name).label('count')
    ).group_by(Channel.name).having(func.count(Channel.name) > 1).all()
    
    duplicate_list = []
    for dup in duplicates:
        # Get all channels with this name
        channels = db.query(Channel).filter(Channel.name == dup.name).all()
        for channel in channels[1:]:  # Skip the first one
            duplicate_list.append({
                "id": channel.id,
                "name": channel.name,
                "url": channel.url,
                "group": channel.group.name if channel.group else None
            })
    
    return {
        "duplicates": duplicate_list,
        "total": len(duplicate_list)
    }


@router.post("/remove-duplicates", response_model=CleanupResponse)
async def remove_duplicate_channels(
    channel_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Remove specified duplicate channels."""
    removed = 0
    for channel_id in channel_ids:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if channel:
            db.delete(channel)
            removed += 1
    
    db.commit()
    
    return {
        "removed": removed,
        "message": f"Removed {removed} duplicate channels"
    }


@router.post("/remove-offline", response_model=CleanupResponse)
async def remove_offline_channels(
    days_offline: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Remove channels that have been offline for specified days."""
    cutoff_date = datetime.utcnow() - timedelta(days=days_offline)
    
    # Remove channels marked as offline before cutoff date
    offline_channels = db.query(Channel).filter(
        Channel.is_active == False,
        Channel.updated_at < cutoff_date
    ).all()
    
    removed = len(offline_channels)
    for channel in offline_channels:
        db.delete(channel)
    
    db.commit()
    
    return {
        "removed": removed,
        "message": f"Removed {removed} offline channels"
    }


@router.post("/clear-failed-imports", response_model=CleanupResponse)
async def clear_failed_imports(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Clear data from failed import attempts."""
    # Remove channels without a playlist association
    orphaned = db.query(Channel).filter(Channel.playlist_id == None).all()
    removed = len(orphaned)
    
    for channel in orphaned:
        db.delete(channel)
    
    db.commit()
    
    return {
        "removed": removed,
        "message": f"Cleared {removed} orphaned channels"
    }


@router.post("/clear-old-epg", response_model=CleanupResponse)
async def clear_old_epg_data(
    days_old: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Remove EPG data older than specified days."""
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
    
    # Delete old programs
    result = db.query(EPGProgram).filter(
        EPGProgram.end_time < cutoff_date
    ).delete(synchronize_session=False)
    
    db.commit()
    
    return {
        "removed": result,
        "message": f"Removed {result} old EPG entries"
    }


@router.post("/optimize", response_model=CleanupResponse)
async def optimize_database(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Optimize database tables."""
    try:
        # For SQLite
        db.execute(text("VACUUM"))
        db.execute(text("ANALYZE"))
        db.commit()
        
        return {
            "removed": 0,
            "message": "Database optimized successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-all", response_model=CleanupResponse)
async def reset_all_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Reset all channel, group, and EPG data."""
    try:
        # Delete in order to respect foreign key constraints
        db.query(EPGProgram).delete()
        db.query(Channel).delete()
        db.query(ChannelGroup).delete()
        db.query(EPGSource).delete()
        db.query(Playlist).delete()
        
        db.commit()
        
        return {
            "removed": -1,
            "message": "All data has been reset"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_cleanup_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get database statistics for cleanup."""
    stats = {
        "total_channels": db.query(func.count(Channel.id)).scalar(),
        "offline_channels": db.query(func.count(Channel.id)).filter(Channel.is_active == False).scalar(),
        "total_groups": db.query(func.count(ChannelGroup.id)).scalar(),
        "total_epg_programs": db.query(func.count(EPGProgram.id)).scalar(),
        "total_playlists": db.query(func.count(Playlist.id)).scalar(),
        "total_epg_sources": db.query(func.count(EPGSource.id)).scalar(),
    }
    
    # Find duplicate channel count
    duplicates = db.query(
        func.count(Channel.name)
    ).group_by(Channel.name).having(func.count(Channel.name) > 1).count()
    
    stats["duplicate_channels"] = duplicates
    
    return stats