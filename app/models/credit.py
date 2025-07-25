from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class TransactionType(str, enum.Enum):
    PURCHASE = "purchase"
    UPGRADE = "upgrade"
    ADMIN_GRANT = "admin_grant"
    REFUND = "refund"

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="credit_transactions")

class UserQuota(Base):
    __tablename__ = "user_quotas"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    max_recordings = Column(Integer, default=3)
    max_recurring_shows = Column(Integer, default=3)
    max_movies = Column(Integer, default=3)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="quota")