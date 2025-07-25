from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole
from app.models.credit import UserQuota
from app.auth.dependencies import get_current_user, require_manager_or_admin, require_admin
from app.auth.security import get_password_hash
from pydantic import BaseModel, EmailStr

router = APIRouter()

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    credits: int
    is_active: bool
    max_recordings: int
    max_recurring_shows: int
    max_movies: int
    
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    credits: Optional[int] = None

class UserQuotaUpdate(BaseModel):
    max_recordings: Optional[int] = None
    max_recurring_shows: Optional[int] = None
    max_movies: Optional[int] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    query = db.query(User)
    
    # Managers can only see regular users
    if current_user.role == UserRole.MANAGER:
        query = query.filter(User.role == UserRole.USER)
    
    users = query.offset(skip).limit(limit).all()
    
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            credits=u.credits,
            is_active=u.is_active,
            max_recordings=u.quota.max_recordings if u.quota else 3,
            max_recurring_shows=u.quota.max_recurring_shows if u.quota else 3,
            max_movies=u.quota.max_movies if u.quota else 3
        )
        for u in users
    ]

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Managers can only view regular users
    if current_user.role == UserRole.MANAGER and user.role != UserRole.USER:
        raise HTTPException(status_code=403, detail="Not authorized to view this user")
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        credits=user.credits,
        is_active=user.is_active,
        max_recordings=user.quota.max_recordings if user.quota else 3,
        max_recurring_shows=user.quota.max_recurring_shows if user.quota else 3,
        max_movies=user.quota.max_movies if user.quota else 3
    )

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Managers can only update regular users
    if current_user.role == UserRole.MANAGER and user.role != UserRole.USER:
        raise HTTPException(status_code=403, detail="Not authorized to update this user")
    
    # Update fields
    if user_update.email is not None:
        user.email = user_update.email
    
    if user_update.role is not None:
        # Only admins can change roles
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can change user roles")
        user.role = user_update.role
    
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    
    if user_update.credits is not None:
        user.credits = user_update.credits
    
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        credits=user.credits,
        is_active=user.is_active,
        max_recordings=user.quota.max_recordings if user.quota else 3,
        max_recurring_shows=user.quota.max_recurring_shows if user.quota else 3,
        max_movies=user.quota.max_movies if user.quota else 3
    )

@router.put("/{user_id}/quota", response_model=UserResponse)
async def update_user_quota(
    user_id: int,
    quota_update: UserQuotaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get or create quota
    quota = user.quota
    if not quota:
        quota = UserQuota(user_id=user_id)
        db.add(quota)
    
    # Update quota values
    if quota_update.max_recordings is not None:
        # Managers have a limit of 10
        if current_user.role == UserRole.MANAGER and quota_update.max_recordings > 10:
            raise HTTPException(status_code=400, detail="Managers can only set up to 10 recordings")
        quota.max_recordings = quota_update.max_recordings
    
    if quota_update.max_recurring_shows is not None:
        if current_user.role == UserRole.MANAGER and quota_update.max_recurring_shows > 10:
            raise HTTPException(status_code=400, detail="Managers can only set up to 10 recurring shows")
        quota.max_recurring_shows = quota_update.max_recurring_shows
    
    if quota_update.max_movies is not None:
        if current_user.role == UserRole.MANAGER and quota_update.max_movies > 10:
            raise HTTPException(status_code=400, detail="Managers can only set up to 10 movies")
        quota.max_movies = quota_update.max_movies
    
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        credits=user.credits,
        is_active=user.is_active,
        max_recordings=quota.max_recordings,
        max_recurring_shows=quota.max_recurring_shows,
        max_movies=quota.max_movies
    )

@router.post("/me/change-password")
async def change_password(
    password_data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.auth.security import verify_password
    
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    # Update password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}