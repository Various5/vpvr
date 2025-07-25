from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.credit import CreditTransaction, UserQuota, TransactionType
from app.auth.dependencies import get_current_user, require_manager_or_admin
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class CreditPurchase(BaseModel):
    amount: int
    payment_method: str = "fake_payment"

class QuotaUpgrade(BaseModel):
    upgrade_type: str  # "recordings", "recurring_shows", "movies"
    increase_amount: int  # 1, 5, or 10

class CreditTransactionResponse(BaseModel):
    id: int
    user_id: int
    amount: int
    transaction_type: TransactionType
    description: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class CreditBalance(BaseModel):
    credits: int
    max_recordings: int
    max_recurring_shows: int
    max_movies: int

@router.get("/balance", response_model=CreditBalance)
async def get_credit_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quota = current_user.quota
    return CreditBalance(
        credits=current_user.credits,
        max_recordings=quota.max_recordings if quota else 3,
        max_recurring_shows=quota.max_recurring_shows if quota else 3,
        max_movies=quota.max_movies if quota else 3
    )

@router.post("/purchase")
async def purchase_credits(
    purchase: CreditPurchase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Simulate payment processing
    if purchase.payment_method != "fake_payment":
        raise HTTPException(status_code=400, detail="Invalid payment method")
    
    if purchase.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    
    # Add credits
    current_user.credits += purchase.amount
    
    # Create transaction record
    transaction = CreditTransaction(
        user_id=current_user.id,
        amount=purchase.amount,
        transaction_type=TransactionType.PURCHASE,
        description=f"Purchased {purchase.amount} credits"
    )
    
    db.add(transaction)
    db.commit()
    
    return {
        "message": "Credits purchased successfully",
        "new_balance": current_user.credits
    }

@router.post("/upgrade-quota")
async def upgrade_quota(
    upgrade: QuotaUpgrade,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Calculate cost
    cost_map = {
        1: 1,
        5: 4,
        10: 8
    }
    
    if upgrade.increase_amount not in cost_map:
        raise HTTPException(status_code=400, detail="Invalid upgrade amount")
    
    cost = cost_map[upgrade.increase_amount]
    
    # Check if user has enough credits
    if current_user.credits < cost:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough credits. Need {cost}, have {current_user.credits}"
        )
    
    # Get or create quota
    quota = current_user.quota
    if not quota:
        quota = UserQuota(user_id=current_user.id)
        db.add(quota)
    
    # Apply upgrade
    if upgrade.upgrade_type == "recordings":
        quota.max_recordings += upgrade.increase_amount
        description = f"Upgraded recording limit by {upgrade.increase_amount}"
    elif upgrade.upgrade_type == "recurring_shows":
        quota.max_recurring_shows += upgrade.increase_amount
        description = f"Upgraded recurring shows limit by {upgrade.increase_amount}"
    elif upgrade.upgrade_type == "movies":
        quota.max_movies += upgrade.increase_amount
        description = f"Upgraded movies limit by {upgrade.increase_amount}"
    else:
        raise HTTPException(status_code=400, detail="Invalid upgrade type")
    
    # Deduct credits
    current_user.credits -= cost
    
    # Create transaction
    transaction = CreditTransaction(
        user_id=current_user.id,
        amount=-cost,
        transaction_type=TransactionType.UPGRADE,
        description=description
    )
    
    db.add(transaction)
    db.commit()
    db.refresh(quota)
    
    return {
        "message": "Quota upgraded successfully",
        "new_limits": {
            "max_recordings": quota.max_recordings,
            "max_recurring_shows": quota.max_recurring_shows,
            "max_movies": quota.max_movies
        },
        "credits_remaining": current_user.credits
    }

@router.get("/transactions", response_model=List[CreditTransactionResponse])
async def get_credit_transactions(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(CreditTransaction).filter(
        CreditTransaction.user_id == current_user.id
    ).order_by(CreditTransaction.created_at.desc()).offset(skip).limit(limit).all()
    
    return transactions

@router.post("/grant/{user_id}")
async def grant_credits(
    user_id: int,
    amount: int,
    reason: str = "Admin grant",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    # Get target user
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Grant credits
    target_user.credits += amount
    
    # Create transaction
    transaction = CreditTransaction(
        user_id=user_id,
        amount=amount,
        transaction_type=TransactionType.ADMIN_GRANT,
        description=f"{reason} (by {current_user.username})"
    )
    
    db.add(transaction)
    db.commit()
    
    return {
        "message": f"Granted {amount} credits to {target_user.username}",
        "new_balance": target_user.credits
    }