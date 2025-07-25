import asyncio
import logging
from datetime import datetime, timedelta
from app.utils.import_manager import import_manager
from app.database import SessionLocal
from app.models.playlist import Playlist
from app.models.epg_source import EPGSource

logger = logging.getLogger(__name__)

async def cleanup_import_jobs():
    """Clean up old import jobs periodically"""
    while True:
        try:
            # Clean up jobs older than 24 hours
            import_manager.cleanup_old_jobs(24)
            logger.info(f"Cleaned up old import jobs. Active jobs: {len(import_manager.jobs)}")
        except Exception as e:
            logger.error(f"Error cleaning up import jobs: {e}")
        
        # Run every hour
        await asyncio.sleep(3600)

async def auto_refresh_playlists():
    """Auto-refresh playlists based on update interval"""
    while True:
        try:
            db = SessionLocal()
            try:
                # Get playlists that need refresh
                now = datetime.utcnow()
                playlists = db.query(Playlist).filter(
                    Playlist.is_active == True,
                    Playlist.url.isnot(None),
                    ~Playlist.url.startswith("file://")
                ).all()
                
                logger.info(f"Auto-refresh check: Found {len(playlists)} active playlists")
                
                for playlist in playlists:
                    # Skip if no last_updated (never imported manually)
                    if not playlist.last_updated:
                        logger.info(f"Skipping playlist {playlist.id} - never imported")
                        continue
                    
                    # Check if needs refresh based on update interval
                    next_update = playlist.last_updated + timedelta(seconds=playlist.update_interval)
                    time_until = (next_update - now).total_seconds()
                    
                    if now < next_update:
                        logger.info(f"Playlist {playlist.id} ({playlist.name}) - next refresh in {time_until/60:.1f} minutes")
                        continue
                    
                    logger.info(f"Playlist {playlist.id} ({playlist.name}) - needs refresh (overdue by {-time_until/60:.1f} minutes)")
                    
                    # Check if already importing
                    import_id = f"playlist_{playlist.id}"
                    job = import_manager.get_job(import_id)
                    if job and job.status not in ['completed', 'failed', 'cancelled']:
                        continue
                    
                    # Create import job WITHOUT EPG auto-mapping
                    logger.info(f"Auto-refreshing playlist {playlist.id}: {playlist.name} (scheduled)")
                    job = import_manager.create_job(
                        import_id=f"playlist_auto_{playlist.id}_{int(now.timestamp())}",
                        playlist_id=playlist.id,
                        url=playlist.url,
                        epg_url=None  # No auto-mapping for scheduled refreshes
                    )
                    
                    # Start import without callback (background)
                    await import_manager.start_import(job.id)
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in auto-refresh: {e}")
        
        # Check every 5 minutes
        await asyncio.sleep(300)

async def monitor_import_health():
    """Monitor and restart stuck imports"""
    while True:
        try:
            for job_id, job in list(import_manager.jobs.items()):
                # Check if job is stuck (no update for 10 minutes)
                if job.status in ['downloading', 'parsing', 'importing']:
                    time_since_update = (datetime.utcnow() - job.updated_at).total_seconds()
                    if time_since_update > 600:  # 10 minutes
                        logger.warning(f"Import job {job_id} appears stuck, marking as failed")
                        job.status = 'failed'
                        job.error = 'Import timed out - no progress for 10 minutes'
                        
                        # Cancel any active task
                        task = import_manager.active_tasks.get(job_id)
                        if task and not task.done():
                            task.cancel()
                            
        except Exception as e:
            logger.error(f"Error monitoring imports: {e}")
        
        # Check every minute
        await asyncio.sleep(60)

def start_background_tasks():
    """Start all background tasks"""
    # Start the scheduler (not async)
    from app.utils.scheduler import start_scheduler
    start_scheduler()
    
    # Create async tasks
    tasks = [
        asyncio.create_task(cleanup_import_jobs()),
        asyncio.create_task(auto_refresh_playlists()),
        asyncio.create_task(monitor_import_health()),
    ]
    
    logger.info("Background tasks started")
    return tasks