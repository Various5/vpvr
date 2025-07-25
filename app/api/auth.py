from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole
from app.models.credit import UserQuota
from app.auth.security import verify_password, get_password_hash, create_access_token
from app.auth.dependencies import get_current_user
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    credits: int
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.post("/register", response_model=UserInfo)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    if db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=UserRole.USER
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Create default quota for user
    user_quota = UserQuota(user_id=db_user.id)
    db.add(user_quota)
    db.commit()
    
    return db_user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    # In a real app, you might want to blacklist the token here
    return {"message": "Successfully logged out"}

@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Refresh the access token for the current user.
    This endpoint can be used to get a new token before the current one expires.
    """
    # Create a new token with the same claims
    access_token = create_access_token(data={"sub": current_user.username})
    return {"access_token": access_token, "token_type": "bearer"}

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    
    return {"message": "Password updated successfully"}