from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
from typing import Optional, Dict, Any

class ImportSource(Base):
    """Modern import source model with full metadata support"""
    __tablename__ = "import_sources"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # 'url', 'file', 'api'
    
    # M3U/Playlist data
    m3u_url = Column(Text)
    m3u_file_path = Column(Text)  # For uploaded files
    m3u_headers = Column(JSON)  # Custom headers for auth
    
    # EPG data
    epg_url = Column(Text)
    epg_file_path = Column(Text)  # For uploaded files
    epg_headers = Column(JSON)  # Custom headers for auth
    epg_timezone = Column(String, default='UTC')
    
    # Import settings
    import_settings = Column(JSON, default={})  # All import preferences
    # Example settings:
    # {
    #   "auto_map_epg": false,
    #   "update_existing": true,
    #   "preserve_user_edits": true,
    #   "skip_duplicates": true,
    #   "filter_adult": false,
    #   "only_hd": false,
    #   "test_streams": false,
    #   "group_filter": [],
    #   "country_filter": [],
    #   "language_filter": []
    # }
    
    # Status tracking
    is_active = Column(Boolean, default=True)
    last_import_at = Column(DateTime(timezone=True))
    last_import_status = Column(String)  # 'success', 'failed', 'partial'
    last_import_details = Column(JSON)  # Error messages, stats, etc
    next_refresh_at = Column(DateTime(timezone=True))
    
    # Statistics
    total_channels = Column(Integer, default=0)
    active_channels = Column(Integer, default=0)
    failed_channels = Column(Integer, default=0)
    last_import_duration = Column(Integer)  # seconds
    
    # Auto-refresh settings
    auto_refresh = Column(Boolean, default=False)
    refresh_interval = Column(Integer, default=86400)  # 24 hours in seconds
    refresh_time = Column(String)  # Preferred time like "03:00"
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_id = Column(Integer)
    
    # File metadata for uploads
    original_filename = Column(String)
    file_size = Column(Integer)
    file_hash = Column(String)  # SHA256 for deduplication
    
    # Authentication
    auth_type = Column(String)  # 'none', 'basic', 'bearer', 'custom'
    auth_credentials = Column(JSON)  # Encrypted credentials
    
    # Ensure unique sources
    __table_args__ = (
        UniqueConstraint('m3u_url', 'epg_url', name='_source_urls_uc'),
        UniqueConstraint('file_hash', name='_file_hash_uc'),
        Index('idx_source_active', 'is_active'),
        Index('idx_next_refresh', 'next_refresh_at', 'is_active'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "m3u_url": self.m3u_url,
            "m3u_file_path": self.m3u_file_path,
            "epg_url": self.epg_url,
            "epg_file_path": self.epg_file_path,
            "import_settings": self.import_settings or {},
            "is_active": self.is_active,
            "last_import_at": self.last_import_at.isoformat() if self.last_import_at else None,
            "last_import_status": self.last_import_status,
            "last_import_details": self.last_import_details,
            "next_refresh_at": self.next_refresh_at.isoformat() if self.next_refresh_at else None,
            "total_channels": self.total_channels,
            "active_channels": self.active_channels,
            "failed_channels": self.failed_channels,
            "auto_refresh": self.auto_refresh,
            "refresh_interval": self.refresh_interval,
            "refresh_time": self.refresh_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "original_filename": self.original_filename,
            "file_size": self.file_size
        }
    
    def get_m3u_location(self) -> Optional[str]:
        """Get M3U location (URL or file path)"""
        if self.source_type == 'url':
            return self.m3u_url
        elif self.source_type == 'file':
            return f"file://{self.m3u_file_path}"
        return None
    
    def get_epg_location(self) -> Optional[str]:
        """Get EPG location (URL or file path)"""
        if self.epg_url:
            return self.epg_url
        elif self.epg_file_path:
            return f"file://{self.epg_file_path}"
        return None