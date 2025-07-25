import os
import asyncio
import subprocess
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.recording import Recording, RecordingStatus
from app.config import get_settings

settings = get_settings()

class Recorder:
    def __init__(self):
        self.active_recordings = {}
        
    async def record(self, recording_id: int):
        db = SessionLocal()
        try:
            recording = db.query(Recording).filter(Recording.id == recording_id).first()
            if not recording:
                return
            
            # Create recording directory
            user_dir = os.path.join(settings.recording_path, str(recording.user_id))
            os.makedirs(user_dir, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = "".join(c for c in recording.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"{safe_title}_{timestamp}.ts"
            file_path = os.path.join(user_dir, filename)
            
            # Update recording status
            recording.file_path = file_path
            recording.status = RecordingStatus.RECORDING
            db.commit()
            
            # Start ffmpeg recording
            process = await self._start_ffmpeg(
                recording.channel.stream_url,
                file_path,
                recording.end_time
            )
            
            # Store process reference
            self.active_recordings[recording_id] = process
            
            # Wait for recording to complete
            await process.wait()
            
            # Check if recording was successful
            if process.returncode == 0 and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                recording.status = RecordingStatus.COMPLETED
                recording.file_size = file_size
            else:
                recording.status = RecordingStatus.FAILED
                recording.error_message = f"FFmpeg exited with code {process.returncode}"
                
                # Clean up failed recording
                if os.path.exists(file_path):
                    os.remove(file_path)
                    recording.file_path = None
            
            db.commit()
            
        except Exception as e:
            if recording:
                recording.status = RecordingStatus.FAILED
                recording.error_message = str(e)
                db.commit()
        finally:
            # Remove from active recordings
            if recording_id in self.active_recordings:
                del self.active_recordings[recording_id]
            db.close()
    
    async def _start_ffmpeg(self, stream_url: str, output_path: str, end_time: datetime):
        # Calculate duration
        duration = (end_time - datetime.utcnow()).total_seconds()
        if duration <= 0:
            duration = 60  # Default 1 minute if end time has passed
        
        # FFmpeg command
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', stream_url,
            '-t', str(int(duration)),
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-f', 'mpegts',
            output_path
        ]
        
        # Start process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        return process
    
    async def stop_recording(self, recording_id: int):
        if recording_id in self.active_recordings:
            process = self.active_recordings[recording_id]
            process.terminate()
            await process.wait()
            
            # Update status
            db = SessionLocal()
            try:
                recording = db.query(Recording).filter(Recording.id == recording_id).first()
                if recording and recording.status == RecordingStatus.RECORDING:
                    recording.status = RecordingStatus.CANCELLED
                    db.commit()
            finally:
                db.close()

# Singleton recorder instance
recorder = Recorder()