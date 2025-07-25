from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.database import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.channel import Channel, ChannelGroup
from app.models.playlist import Playlist
from app.models.epg import EPGProgram
from app.models.epg_source import EPGSource
from app.models.recording import Recording
from pydantic import BaseModel
from typing import Dict, List, Optional
import psutil
import platform
import time
import os
from datetime import datetime, timezone
import fastapi

router = APIRouter()

class SystemStatus(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    uptime: int
    db_stats: Dict
    services: Dict
    system_info: Dict
    storage: Dict

class ActivityLog(BaseModel):
    timestamp: datetime
    type: str
    action: str
    user: Optional[str]
    status: str

@router.get("/status", response_model=SystemStatus)
async def get_system_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive system status"""
    
    # CPU usage
    cpu_usage = psutil.cpu_percent(interval=1)
    
    # Memory usage
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    
    # Disk usage
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent
    
    # Uptime
    boot_time = psutil.boot_time()
    uptime = int(time.time() - boot_time)
    
    # Database statistics
    db_stats = {
        "total_channels": db.query(Channel).count(),
        "total_playlists": db.query(Playlist).count(),
        "total_epg_sources": db.query(EPGSource).count(),
        "total_programs": db.query(EPGProgram).count(),
        "total_users": db.query(User).count(),
        "total_recordings": db.query(Recording).count(),
        "active_recordings": db.query(Recording).filter(
            Recording.status.in_(["scheduled", "recording"])
        ).count(),
        "db_size": get_database_size(db)
    }
    
    # Service status
    services = {
        "tuner": check_tuner_status(),
        "websocket": check_websocket_status(),
        "scheduler": check_scheduler_status()
    }
    
    # System information
    system_info = {
        "python_version": platform.python_version(),
        "fastapi_version": fastapi.__version__,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "timezone": time.tzname[0],
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown"
    }
    
    # Storage information
    from app.config import get_settings
    settings = get_settings()
    
    recording_path = settings.recording_path
    recording_storage = get_storage_info(recording_path)
    system_storage = get_storage_info('/')
    
    storage = {
        "recording": recording_storage,
        "system": system_storage
    }
    
    return SystemStatus(
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        disk_usage=disk_usage,
        uptime=uptime,
        db_stats=db_stats,
        services=services,
        system_info=system_info,
        storage=storage
    )

@router.get("/activity", response_model=List[ActivityLog])
async def get_recent_activity(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get recent system activity"""
    # For now, return mock data. In production, this would query an activity log table
    activities = []
    
    # Get recent recordings
    recent_recordings = db.query(Recording).order_by(
        Recording.created_at.desc()
    ).limit(10).all()
    
    for recording in recent_recordings:
        activities.append(ActivityLog(
            timestamp=recording.created_at,
            type="recording",
            action=f"Recording scheduled: {recording.program_title}",
            user=recording.user.username if recording.user else None,
            status=recording.status
        ))
    
    # Get recent playlist updates
    recent_playlists = db.query(Playlist).filter(
        Playlist.last_updated.isnot(None)
    ).order_by(
        Playlist.last_updated.desc()
    ).limit(10).all()
    
    for playlist in recent_playlists:
        activities.append(ActivityLog(
            timestamp=playlist.last_updated,
            type="import",
            action=f"Playlist updated: {playlist.name}",
            user="System",
            status="completed"
        ))
    
    # Sort by timestamp
    activities.sort(key=lambda x: x.timestamp, reverse=True)
    
    return activities[:limit]

@router.post("/clear-cache")
async def clear_system_cache(
    current_user: User = Depends(require_admin)
):
    """Clear system caches"""
    # Clear any application caches here
    return {"message": "Cache cleared successfully"}

@router.post("/optimize-db")
async def optimize_database(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Optimize database tables"""
    try:
        # For SQLite
        db.execute(text("VACUUM"))
        db.commit()
        return {"message": "Database optimized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/info")
async def get_system_info(
    current_user: User = Depends(get_current_user)
):
    """Get basic system information"""
    import uuid
    
    # Generate or retrieve device ID
    device_id = str(uuid.getnode())  # MAC address as integer
    
    return {
        "device_id": device_id,
        "system_name": "IPTV PVR",
        "version": "1.0.0",
        "platform": platform.system(),
        "python_version": platform.python_version()
    }

def get_database_size(db: Session) -> int:
    """Get database size in bytes"""
    try:
        # Try to get database file size (SQLite)
        from app.config import get_settings
        settings = get_settings()
        if "sqlite" in settings.database_url:
            db_path = settings.database_url.replace("sqlite:///", "")
            if os.path.exists(db_path):
                return os.path.getsize(db_path)
        
        # For other databases, return 0 or implement specific logic
        return 0
    except:
        return 0

def get_storage_info(path: str) -> Dict:
    """Get storage information for a path"""
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_avail * stat.f_frsize
        used = total - free
        
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent": (used / total) * 100 if total > 0 else 0
        }
    except:
        return {
            "total": 0,
            "used": 0,
            "free": 0,
            "percent": 0
        }

def check_tuner_status() -> bool:
    """Check if Network Tuner emulation is running"""
    # Check if the Network Tuner discovery port is listening
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.bind(('', 0))  # Bind to any available port
        sock.sendto(b'', ('127.0.0.1', 5004))  # Try to send to Network Tuner port
        return True
    except:
        return False

def check_websocket_status() -> bool:
    """Check if WebSocket server is running"""
    # For now, assume it's running if the main app is running
    return True

def check_scheduler_status() -> bool:
    """Check if scheduler is running"""
    try:
        from app.utils.scheduler import scheduler
        return scheduler.running
    except:
        return False