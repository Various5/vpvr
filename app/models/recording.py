from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class RecordingStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    RECORDING = "recording"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class RecordingType(str, enum.Enum):
    SINGLE = "single"
    SERIES = "series"
    RECURRING = "recurring"

class Recording(Base):
    __tablename__ = "recordings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("epg_programs.id"))
    title = Column(String, nullable=False)
    status = Column(Enum(RecordingStatus), default=RecordingStatus.SCHEDULED)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    file_path = Column(String)
    file_size = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="recordings")
    channel = relationship("Channel", back_populates="recordings")
    program = relationship("EPGProgram", back_populates="recordings")

class RecordingSchedule(Base):
    __tablename__ = "recording_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"))
    program_id = Column(Integer, ForeignKey("epg_programs.id"))
    series_id = Column(String, index=True)
    title_pattern = Column(String)
    recording_type = Column(Enum(RecordingType), nullable=False)
    is_active = Column(Boolean, default=True)
    max_recordings = Column(Integer)
    keep_days = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="recording_schedules")
    channel = relationship("Channel")
    program = relationship("EPGProgram", back_populates="recording_schedules")