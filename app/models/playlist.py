from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Playlist(Base):
    __tablename__ = "playlists"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime(timezone=True))
    update_interval = Column(Integer, default=3600)  # seconds
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    channels = relationship("Channel", back_populates="playlist")
    epg_sources = relationship("EPGSource", back_populates="playlist", cascade="all, delete-orphan")