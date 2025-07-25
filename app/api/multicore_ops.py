"""
API endpoints for multicore operations
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models import User, UserRole
from app.api.auth import get_current_user
from app.utils.multicore_channel_ops import MultiCoreChannelOperations
from app.api.websocket import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/multicore", tags=["multicore"])

class BulkUpdateRequest(BaseModel):
    channel_ids: List[int]
    updates: Dict[str, Any]

class AutoMapEPGRequest(BaseModel):
    channel_ids: Optional[List[int]] = None

@router.post("/channels/bulk-update")
async def bulk_update_channels(
    request: BulkUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Bulk update channels using multicore processing"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Validate channel IDs exist
    if not request.channel_ids:
        raise HTTPException(status_code=400, detail="No channel IDs provided")
    
    # Start background task
    task_id = f"bulk_update_{current_user.id}_{int(time.time())}"
    
    background_tasks.add_task(
        run_bulk_update,
        task_id,
        request.channel_ids,
        request.updates,
        current_user.id
    )
    
    return {
        "task_id": task_id,
        "message": f"Bulk update started for {len(request.channel_ids)} channels",
        "status": "started"
    }

@router.post("/channels/auto-map-epg")
async def auto_map_epg_channels(
    request: AutoMapEPGRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Auto-map EPG channels using fuzzy matching with multicore processing"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Start background task
    task_id = f"auto_map_epg_{current_user.id}_{int(time.time())}"
    
    background_tasks.add_task(
        run_auto_map_epg,
        task_id,
        request.channel_ids,
        current_user.id
    )
    
    return {
        "task_id": task_id,
        "message": "EPG auto-mapping started",
        "status": "started"
    }

@router.get("/channels/analyze-quality")
async def analyze_channel_quality(
    channel_ids: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analyze channel quality using multicore processing"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Parse channel IDs
    ids = None
    if channel_ids:
        try:
            ids = [int(id) for id in channel_ids.split(',')]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid channel IDs format")
    
    # Run analysis
    ops = MultiCoreChannelOperations()
    
    try:
        result = await ops.analyze_channel_quality_multicore(ids)
        return result
    finally:
        ops.cleanup()

@router.get("/system/info")
async def get_system_info(
    current_user: User = Depends(get_current_user)
):
    """Get multicore system information"""
    import multiprocessing
    import psutil
    
    return {
        "cpu_count": multiprocessing.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": {
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent
        },
        "multicore_enabled": True,
        "worker_processes": max(1, multiprocessing.cpu_count() - 1)
    }

# Background task functions
async def run_bulk_update(
    task_id: str,
    channel_ids: List[int],
    updates: Dict[str, Any],
    user_id: int
):
    """Run bulk update in background"""
    ops = MultiCoreChannelOperations()
    
    try:
        # Progress callback
        async def progress_callback(percentage, message):
            await ws_manager.broadcast_to_user({
                "type": "bulk_update_progress",
                "task_id": task_id,
                "progress": percentage,
                "message": message
            }, user_id)
        
        # Run update
        result = await ops.bulk_update_channels(
            channel_ids,
            updates,
            progress_callback
        )
        
        # Send completion
        await ws_manager.broadcast_to_user({
            "type": "bulk_update_complete",
            "task_id": task_id,
            "result": {
                "success_count": result.success_count,
                "error_count": result.error_count,
                "processing_time": result.processing_time,
                "channels_per_second": result.channels_per_second
            }
        }, user_id)
        
    except Exception as e:
        logger.error(f"Bulk update failed: {str(e)}")
        await ws_manager.broadcast_to_user({
            "type": "bulk_update_error",
            "task_id": task_id,
            "error": str(e)
        }, user_id)
    finally:
        ops.cleanup()

async def run_auto_map_epg(
    task_id: str,
    channel_ids: Optional[List[int]],
    user_id: int
):
    """Run EPG auto-mapping in background"""
    ops = MultiCoreChannelOperations()
    
    try:
        # Progress callback
        async def progress_callback(percentage, message):
            await ws_manager.broadcast_to_user({
                "type": "epg_mapping_progress",
                "task_id": task_id,
                "progress": percentage,
                "message": message
            }, user_id)
        
        # Run mapping
        result = await ops.auto_map_epg_multicore(
            channel_ids,
            progress_callback
        )
        
        # Send completion
        await ws_manager.broadcast_to_user({
            "type": "epg_mapping_complete",
            "task_id": task_id,
            "result": result
        }, user_id)
        
    except Exception as e:
        logger.error(f"EPG auto-mapping failed: {str(e)}")
        await ws_manager.broadcast_to_user({
            "type": "epg_mapping_error",
            "task_id": task_id,
            "error": str(e)
        }, user_id)
    finally:
        ops.cleanup()

# Add missing import
import time