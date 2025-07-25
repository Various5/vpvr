from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class EPGSource(Base):
    __tablename__ = "epg_sources"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(Text, nullable=True)  # URL or file path
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime(timezone=True))
    update_interval = Column(Integer, default=86400)  # 24 hours in seconds
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Enhanced EPG fields
    priority = Column(Integer, default=0)  # Higher priority sources are preferred
    type = Column(String, default='xmltv')  # xmltv, json, api
    auto_map = Column(Boolean, default=True)  # Auto-map channels
    last_error = Column(Text, nullable=True)
    channel_count = Column(Integer, default=0)
    program_count = Column(Integer, default=0)
    import_status = Column(String, default='idle')  # idle, importing, completed, failed
    
    # Relationships
    playlist = relationship("Playlist", back_populates="epg_sources")
    channel_mappings = relationship("EPGChannelMapping", back_populates="epg_source", cascade="all, delete-orphan")
    import_logs = relationship("EPGImportLog", back_populates="epg_source", cascade="all, delete-orphan")
    programs = relationship("EPGProgram", back_populates="epg_source")


class EPGChannelMapping(Base):
    __tablename__ = "epg_channel_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    epg_source_id = Column(Integer, ForeignKey("epg_sources.id", ondelete="CASCADE"), nullable=False)
    epg_channel_id = Column(String, nullable=False)  # Channel ID in the EPG source
    epg_channel_name = Column(String, nullable=True)  # Channel name in the EPG source
    match_confidence = Column(Float, nullable=True)  # 0.0 to 1.0
    match_method = Column(String, nullable=True)  # 'exact', 'fuzzy', 'manual'
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # For ordering when multiple mappings exist
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    channel = relationship("Channel", back_populates="epg_mappings")
    epg_source = relationship("EPGSource", back_populates="channel_mappings")


class EPGImportLog(Base):
    __tablename__ = "epg_import_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    epg_source_id = Column(Integer, ForeignKey("epg_sources.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False)  # 'success', 'failed', 'partial'
    channels_found = Column(Integer, default=0)
    channels_mapped = Column(Integer, default=0)
    programs_imported = Column(Integer, default=0)
    errors = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Relationships
    epg_source = relationship("EPGSource", back_populates="import_logs")