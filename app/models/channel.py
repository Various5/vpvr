from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ChannelGroup(Base):
    __tablename__ = "channel_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    sort_order = Column(Integer, default=0)
    
    channels = relationship("Channel", back_populates="group")

class Channel(Base):
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=False, index=True)
    number = Column(String)
    logo_url = Column(String)
    stream_url = Column(Text, nullable=False)
    group_id = Column(Integer, ForeignKey("channel_groups.id"))
    epg_channel_id = Column(String)
    is_active = Column(Boolean, default=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"))
    country = Column(String)
    language = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Enhanced EPG fields
    epg_auto_mapped = Column(Boolean, default=False)
    epg_mapping_locked = Column(Boolean, default=False)  # Prevent auto-mapping changes
    last_epg_update = Column(DateTime(timezone=True), nullable=True)
    
    group = relationship("ChannelGroup", back_populates="channels")
    playlist = relationship("Playlist", back_populates="channels")
    programs = relationship("EPGProgram", back_populates="channel")
    recordings = relationship("Recording", back_populates="channel")
    epg_mappings = relationship("EPGChannelMapping", back_populates="channel", cascade="all, delete-orphan")