from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from app.database import engine, Base, SessionLocal
from app.api import auth, channels, recordings, users, tuner, epg, credits, websocket, system, import_sources, errors, multicore_ops, stream_proxy, enhanced_epg, admin_cleanup, database_admin
from app import views
from app.config import get_settings
from app.core.error_management import error_manager, http_exception_handler, general_exception_handler
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

settings = get_settings()

# Create tables
Base.metadata.create_all(bind=engine)

# Create recording directory
os.makedirs(settings.recording_path, exist_ok=True)

app = FastAPI(
    title="IPTV PVR System",
    description="Full-featured IPTV Web PVR with Network Tuner emulation",
    version="1.0.0"
)

# Add exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(channels.router, prefix="/api/channels", tags=["Channels"])
app.include_router(epg.router, prefix="/api/epg", tags=["EPG"])
app.include_router(recordings.router, prefix="/api/recordings", tags=["Recordings"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(credits.router, prefix="/api/credits", tags=["Credits"])
app.include_router(tuner.router, prefix="/api/tuner", tags=["Network Tuner"])
# Also mount Network Tuner endpoints at root for compatibility
app.include_router(tuner.router, tags=["Network Tuner"])
app.include_router(websocket.router, prefix="/api", tags=["WebSocket"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(import_sources.router, prefix="/api/import-sources", tags=["Import Sources"])
app.include_router(errors.router, prefix="/api/errors", tags=["Error Management"])
app.include_router(multicore_ops.router, prefix="/api/multicore", tags=["Multicore Operations"])
app.include_router(stream_proxy.router, prefix="/api/stream-proxy", tags=["Stream Proxy"])
app.include_router(enhanced_epg.router, prefix="/api/enhanced-epg", tags=["Enhanced EPG"])
app.include_router(admin_cleanup.router, prefix="/api/admin/cleanup", tags=["Admin Cleanup"])
app.include_router(database_admin.router, prefix="/api/admin/database", tags=["Database Admin"])

# Include view routes
app.include_router(views.router)

# Global background tasks
background_tasks = []

# Start scheduler on startup
@app.on_event("startup")
async def startup_event():
    global background_tasks
    
    # Start background tasks (includes scheduler)
    from app.utils.background_tasks import start_background_tasks
    background_tasks = start_background_tasks()
    
    # Start Network Tuner SSDP discovery service
    from app.tuner_discovery import start_discovery
    start_discovery()
    
    # NO AUTOMATIC IMPORTS AT STARTUP
    # - No channels will be imported automatically
    # - No EPG mapping will occur automatically
    # - No channel merging will happen automatically
    # 
    # Imports only happen when:
    # 1. User manually triggers import/refresh
    # 2. Scheduled refresh time is reached (for playlists that were manually imported at least once)
    #
    # When imports do run:
    # - Existing channels preserve user modifications (name, number, EPG mapping)
    # - Removed channels are marked inactive (not deleted)
    # - EPG auto-mapping only happens if explicitly requested
    
    # Create default playlist entry if it doesn't exist (WITHOUT importing)
    if settings.default_m3u_url:
        from app.models.playlist import Playlist
        db = SessionLocal()
        try:
            # Check if default playlist exists (only create if URL is provided)
            if settings.default_m3u_url:
                default_playlist = db.query(Playlist).filter(
                    Playlist.url == settings.default_m3u_url
                ).first()
                
                if not default_playlist:
                    playlist = Playlist(
                        name="Default Playlist",
                        url=settings.default_m3u_url
                    )
                    db.add(playlist)
                    db.commit()
                    logger.info("Created default playlist entry (NO AUTO-IMPORT)")
                    logger.info("Use the Import Manager UI or API to manually import channels")
        finally:
            db.close()

@app.on_event("shutdown")
async def shutdown_event():
    global background_tasks
    
    # Stop Network Tuner discovery service
    from app.tuner_discovery import stop_discovery
    stop_discovery()
    
    # Cancel all background tasks
    for task in background_tasks:
        task.cancel()
    
    # Wait for tasks to complete
    import asyncio
    await asyncio.gather(*background_tasks, return_exceptions=True)
    
    from app.utils.scheduler import stop_scheduler
    stop_scheduler()