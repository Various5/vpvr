from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# Association table for many-to-many relationship between custom playlists and channels
custom_playlist_channels = Table(
    'custom_playlist_channels',
    Base.metadata,
    Column('playlist_id', Integer, ForeignKey('custom_playlists.id', ondelete='CASCADE')),
    Column('channel_id', Integer, ForeignKey('channels.id', ondelete='CASCADE')),
    Column('position', Integer, default=0)  # For custom ordering
)

class CustomPlaylist(Base):
    __tablename__ = "custom_playlists"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_default = Column(Boolean, default=False)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="custom_playlists")
    channels = relationship("Channel", secondary=custom_playlist_channels, backref="custom_playlists")