from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class EPGProgram(Base):
    __tablename__ = "epg_programs"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    category = Column(String)
    episode_num = Column(String)
    season_num = Column(String)
    series_id = Column(String, index=True)
    icon_url = Column(String)
    is_new = Column(Boolean, default=False)
    is_live = Column(Boolean, default=False)
    is_repeat = Column(Boolean, default=False)
    
    # Track which EPG source this program came from
    epg_source_id = Column(Integer, ForeignKey("epg_sources.id", ondelete="SET NULL"), nullable=True)
    original_channel_id = Column(String, nullable=True)  # Channel ID from the EPG source
    
    channel = relationship("Channel", back_populates="programs")
    recordings = relationship("Recording", back_populates="program")
    recording_schedules = relationship("RecordingSchedule", back_populates="program")
    epg_source = relationship("EPGSource", back_populates="programs")