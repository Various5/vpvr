from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database import get_db
from app.models.recording import Recording, RecordingSchedule, RecordingStatus, RecordingType
from app.models.epg import EPGProgram
from app.models.channel import Channel
from app.models.user import User
from app.auth.dependencies import get_current_user
from app.utils.recorder import Recorder
from pydantic import BaseModel

router = APIRouter()

class RecordingCreate(BaseModel):
    channel_id: int
    program_id: Optional[int] = None
    title: str
    start_time: datetime
    end_time: datetime

class RecordingScheduleCreate(BaseModel):
    channel_id: Optional[int] = None
    program_id: Optional[int] = None
    series_id: Optional[str] = None
    title_pattern: Optional[str] = None
    recording_type: RecordingType
    max_recordings: Optional[int] = None
    keep_days: Optional[int] = None

class RecordingResponse(BaseModel):
    id: int
    user_id: int
    channel_id: int
    channel_name: str
    title: str
    status: RecordingStatus
    start_time: datetime
    end_time: datetime
    file_path: Optional[str]
    file_size: Optional[int]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True

class RecordingScheduleResponse(BaseModel):
    id: int
    user_id: int
    channel_id: Optional[int]
    channel_name: Optional[str]
    series_id: Optional[str]
    title_pattern: Optional[str]
    recording_type: RecordingType
    is_active: bool
    max_recordings: Optional[int]
    keep_days: Optional[int]
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[RecordingResponse])
async def get_recordings(
    status: Optional[RecordingStatus] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Recording).filter(Recording.user_id == current_user.id)
    
    if status:
        query = query.filter(Recording.status == status)
    
    recordings = query.order_by(Recording.start_time.desc()).offset(skip).limit(limit).all()
    
    return [
        RecordingResponse(
            id=r.id,
            user_id=r.user_id,
            channel_id=r.channel_id,
            channel_name=r.channel.name,
            title=r.title,
            status=r.status,
            start_time=r.start_time,
            end_time=r.end_time,
            file_path=r.file_path,
            file_size=r.file_size,
            error_message=r.error_message
        )
        for r in recordings
    ]

@router.post("/record-now")
async def record_now(
    channel_id: int,
    background_tasks: BackgroundTasks,
    duration_minutes: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check user quota
    active_recordings = db.query(Recording).filter(
        and_(
            Recording.user_id == current_user.id,
            Recording.status.in_([RecordingStatus.SCHEDULED, RecordingStatus.RECORDING])
        )
    ).count()
    
    if not current_user.quota:
        raise HTTPException(status_code=400, detail="User quota not configured")
    
    if active_recordings >= current_user.quota.max_recordings:
        raise HTTPException(status_code=400, detail="Recording limit reached")
    
    # Get channel
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Create recording
    now = datetime.utcnow()
    recording = Recording(
        user_id=current_user.id,
        channel_id=channel_id,
        title=f"Recording - {channel.name}",
        status=RecordingStatus.RECORDING,
        start_time=now,
        end_time=now + timedelta(minutes=duration_minutes)
    )
    
    db.add(recording)
    db.commit()
    db.refresh(recording)
    
    # Start recording in background
    recorder = Recorder()
    background_tasks.add_task(recorder.record, recording.id)
    
    return {"message": "Recording started", "recording_id": recording.id}

@router.post("/schedule")
async def schedule_recording(
    recording_data: RecordingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check user quota
    scheduled_count = db.query(Recording).filter(
        and_(
            Recording.user_id == current_user.id,
            Recording.status == RecordingStatus.SCHEDULED
        )
    ).count()
    
    if scheduled_count >= current_user.quota.max_recordings:
        raise HTTPException(status_code=400, detail="Recording limit reached")
    
    # Create scheduled recording
    recording = Recording(
        user_id=current_user.id,
        channel_id=recording_data.channel_id,
        program_id=recording_data.program_id,
        title=recording_data.title,
        status=RecordingStatus.SCHEDULED,
        start_time=recording_data.start_time,
        end_time=recording_data.end_time
    )
    
    db.add(recording)
    db.commit()
    db.refresh(recording)
    
    return {"message": "Recording scheduled", "recording_id": recording.id}

@router.post("/schedule/series")
async def schedule_series_recording(
    schedule_data: RecordingScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check user quota for recurring shows
    recurring_count = db.query(RecordingSchedule).filter(
        and_(
            RecordingSchedule.user_id == current_user.id,
            RecordingSchedule.recording_type == RecordingType.SERIES,
            RecordingSchedule.is_active == True
        )
    ).count()
    
    if recurring_count >= current_user.quota.max_recurring_shows:
        raise HTTPException(status_code=400, detail="Recurring show limit reached")
    
    # Create recording schedule
    schedule = RecordingSchedule(
        user_id=current_user.id,
        channel_id=schedule_data.channel_id,
        program_id=schedule_data.program_id,
        series_id=schedule_data.series_id,
        title_pattern=schedule_data.title_pattern,
        recording_type=schedule_data.recording_type,
        max_recordings=schedule_data.max_recordings,
        keep_days=schedule_data.keep_days
    )
    
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    
    return {"message": "Series recording scheduled", "schedule_id": schedule.id}

@router.get("/schedules", response_model=List[RecordingScheduleResponse])
async def get_recording_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    schedules = db.query(RecordingSchedule).filter(
        RecordingSchedule.user_id == current_user.id
    ).all()
    
    return [
        RecordingScheduleResponse(
            id=s.id,
            user_id=s.user_id,
            channel_id=s.channel_id,
            channel_name=s.channel.name if s.channel else None,
            series_id=s.series_id,
            title_pattern=s.title_pattern,
            recording_type=s.recording_type,
            is_active=s.is_active,
            max_recordings=s.max_recordings,
            keep_days=s.keep_days
        )
        for s in schedules
    ]

@router.delete("/{recording_id}")
async def delete_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    recording = db.query(Recording).filter(
        and_(
            Recording.id == recording_id,
            Recording.user_id == current_user.id
        )
    ).first()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if recording.status == RecordingStatus.RECORDING:
        # Stop active recording
        recording.status = RecordingStatus.CANCELLED
        db.commit()
    else:
        # Delete recording and file
        if recording.file_path:
            import os
            try:
                os.remove(recording.file_path)
            except:
                pass
        
        db.delete(recording)
        db.commit()
    
    return {"message": "Recording deleted"}

@router.delete("/schedules/{schedule_id}")
async def delete_recording_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    schedule = db.query(RecordingSchedule).filter(
        and_(
            RecordingSchedule.id == schedule_id,
            RecordingSchedule.user_id == current_user.id
        )
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    db.delete(schedule)
    db.commit()
    
    return {"message": "Schedule deleted"}

@router.get("/{recording_id}/download")
async def download_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    recording = db.query(Recording).filter(
        and_(
            Recording.id == recording_id,
            Recording.user_id == current_user.id
        )
    ).first()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if not recording.file_path or recording.status != RecordingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Recording file not available")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        recording.file_path,
        media_type='video/mp2t',
        filename=f"{recording.title}.ts"
    )