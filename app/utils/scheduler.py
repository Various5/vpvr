from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models.recording import Recording, RecordingSchedule, RecordingStatus, RecordingType
from app.models.epg import EPGProgram
from app.models.playlist import Playlist
from app.utils.recorder import recorder
import pytz
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def check_scheduled_recordings():
    """Check for recordings that need to start"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        upcoming_time = now + timedelta(minutes=5)
        
        # Find recordings scheduled to start soon
        recordings = db.query(Recording).filter(
            and_(
                Recording.status == RecordingStatus.SCHEDULED,
                Recording.start_time >= now,
                Recording.start_time <= upcoming_time
            )
        ).all()
        
        for recording in recordings:
            # Schedule the recording
            scheduler.add_job(
                start_recording,
                'date',
                run_date=recording.start_time,
                args=[recording.id],
                id=f"recording_{recording.id}",
                replace_existing=True
            )
    finally:
        db.close()

async def check_series_recordings():
    """Check for series recordings that need new episodes scheduled"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        future_time = now + timedelta(days=7)  # Look ahead 7 days
        
        # Get active series schedules
        schedules = db.query(RecordingSchedule).filter(
            and_(
                RecordingSchedule.is_active == True,
                RecordingSchedule.recording_type.in_([RecordingType.SERIES, RecordingType.RECURRING])
            )
        ).all()
        
        for schedule in schedules:
            # Find matching programs
            if schedule.series_id:
                # Match by series ID
                programs = db.query(EPGProgram).filter(
                    and_(
                        EPGProgram.series_id == schedule.series_id,
                        EPGProgram.start_time >= now,
                        EPGProgram.start_time <= future_time
                    )
                ).all()
            elif schedule.title_pattern:
                # Match by title pattern
                programs = db.query(EPGProgram).filter(
                    and_(
                        EPGProgram.title.ilike(f"%{schedule.title_pattern}%"),
                        EPGProgram.start_time >= now,
                        EPGProgram.start_time <= future_time
                    )
                ).all()
                
                if schedule.channel_id:
                    programs = [p for p in programs if p.channel_id == schedule.channel_id]
            else:
                continue
            
            # Create recordings for matching programs
            for program in programs:
                # Check if recording already exists
                existing = db.query(Recording).filter(
                    and_(
                        Recording.user_id == schedule.user_id,
                        Recording.program_id == program.id
                    )
                ).first()
                
                if not existing:
                    # Check user's recording limit
                    active_count = db.query(Recording).filter(
                        and_(
                            Recording.user_id == schedule.user_id,
                            Recording.status.in_([RecordingStatus.SCHEDULED, RecordingStatus.RECORDING])
                        )
                    ).count()
                    
                    if schedule.max_recordings and active_count >= schedule.max_recordings:
                        continue
                    
                    # Create recording
                    recording = Recording(
                        user_id=schedule.user_id,
                        channel_id=program.channel_id,
                        program_id=program.id,
                        title=program.title,
                        status=RecordingStatus.SCHEDULED,
                        start_time=program.start_time,
                        end_time=program.end_time
                    )
                    db.add(recording)
            
            db.commit()
    finally:
        db.close()

async def start_recording(recording_id: int):
    """Start a scheduled recording"""
    await recorder.record(recording_id)

async def cleanup_old_recordings():
    """Clean up old recordings based on retention settings"""
    db = SessionLocal()
    try:
        # Get all recording schedules with keep_days set
        schedules = db.query(RecordingSchedule).filter(
            RecordingSchedule.keep_days.isnot(None)
        ).all()
        
        for schedule in schedules:
            cutoff_date = datetime.utcnow() - timedelta(days=schedule.keep_days)
            
            # Find old recordings
            old_recordings = db.query(Recording).filter(
                and_(
                    Recording.user_id == schedule.user_id,
                    Recording.status == RecordingStatus.COMPLETED,
                    Recording.created_at < cutoff_date
                )
            ).all()
            
            for recording in old_recordings:
                # Delete file
                if recording.file_path:
                    import os
                    try:
                        os.remove(recording.file_path)
                    except:
                        pass
                
                # Delete record
                db.delete(recording)
        
        db.commit()
    finally:
        db.close()

# DEPRECATED - Playlist updates are handled by background_tasks.py
async def update_playlists():
    """DEPRECATED - This function is no longer used"""
    pass

# DEPRECATED - EPG updates are handled manually
async def update_epg_sources():
    """DEPRECATED - This function is no longer used"""
    pass

def start_scheduler():
    """Start the scheduler with all jobs"""
    # Check scheduled recordings every minute
    scheduler.add_job(
        check_scheduled_recordings,
        IntervalTrigger(minutes=1),
        id='check_scheduled_recordings',
        replace_existing=True
    )
    
    # Check series recordings every 30 minutes
    scheduler.add_job(
        check_series_recordings,
        IntervalTrigger(minutes=30),
        id='check_series_recordings',
        replace_existing=True
    )
    
    # Clean up old recordings daily
    scheduler.add_job(
        cleanup_old_recordings,
        IntervalTrigger(days=1),
        id='cleanup_old_recordings',
        replace_existing=True
    )
    
    # Playlist updates disabled - only allow manual updates
    # scheduler.add_job(
    #     update_playlists,
    #     'cron',
    #     hour=3,
    #     minute=0,
    #     id='update_playlists',
    #     replace_existing=True
    # )
    
    # EPG updates disabled - only allow manual updates
    # scheduler.add_job(
    #     update_epg_sources,
    #     IntervalTrigger(hours=6),
    #     id='update_epg_sources',
    #     replace_existing=True
    # )
    
    scheduler.start()

def stop_scheduler():
    """Stop the scheduler"""
    scheduler.shutdown()