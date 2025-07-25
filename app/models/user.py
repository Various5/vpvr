from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True)
    credits = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    recordings = relationship("Recording", back_populates="user")
    recording_schedules = relationship("RecordingSchedule", back_populates="user")
    credit_transactions = relationship("CreditTransaction", back_populates="user")
    quota = relationship("UserQuota", back_populates="user", uselist=False)
    custom_playlists = relationship("CustomPlaylist", back_populates="user")

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    max_recordings = Column(Integer, default=3)
    max_recurring_shows = Column(Integer, default=3)
    max_movies = Column(Integer, default=3)
    can_manage_users = Column(Boolean, default=False)
    can_manage_system = Column(Boolean, default=False)
    unlimited_recordings = Column(Boolean, default=False)