"""
Error Management API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from app.core.error_management import error_manager, ErrorCategory, ErrorSeverity
from app.api.auth import get_current_user
from app.models import User

router = APIRouter()


@router.get("/recent")
async def get_recent_errors(
    limit: int = 10,
    category: Optional[ErrorCategory] = None,
    severity: Optional[ErrorSeverity] = None,
    current_user: User = Depends(get_current_user)
):
    """Get recent errors (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    errors = error_manager.get_recent_errors(limit, category, severity)
    return {
        "errors": [error.to_user_dict() for error in errors],
        "total": len(errors)
    }


@router.get("/{error_id}")
async def get_error_details(
    error_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed error information"""
    error = error_manager.get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404, detail="Error not found")
    
    # Return full details for admin, limited for regular users
    if current_user.is_admin:
        return {
            "error": error.to_dict(),
            "copyable": error.to_copyable_text()
        }
    else:
        return {
            "error": error.to_user_dict(),
            "copyable": error.to_copyable_text()
        }


@router.post("/report")
async def report_client_error(
    error_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Report an error from the client side"""
    # Create a custom exception from client data
    client_error = Exception(error_data.get("message", "Client-side error"))
    
    # Create error with context
    from app.core.error_management import ErrorContext
    context = ErrorContext(
        user_id=current_user.id,
        additional_data=error_data
    )
    
    error = error_manager.create_error(
        exception=client_error,
        category=ErrorCategory.SYSTEM,
        severity=ErrorSeverity.ERROR,
        context=context,
        user_message=error_data.get("user_message"),
        error_code=error_data.get("error_code")
    )
    
    return {
        "error_id": error.error_id,
        "message": "Error reported successfully"
    }