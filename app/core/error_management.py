"""
Unified Error Management System for IPTV PVR
Provides consistent error handling, logging, and user-friendly error messages
"""

import traceback
import logging
import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for better organization"""
    NETWORK = "network"
    VALIDATION = "validation"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    IMPORT = "import"
    PARSING = "parsing"
    SYSTEM = "system"
    CONFIGURATION = "configuration"
    MEDIA = "media"


@dataclass
class ErrorContext:
    """Additional context for debugging"""
    user_id: Optional[int] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


@dataclass
class ErrorDetail:
    """Detailed error information"""
    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    user_message: str
    technical_details: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Optional[ErrorContext] = None
    suggestions: Optional[List[str]] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    def to_user_dict(self) -> Dict[str, Any]:
        """User-safe dictionary without sensitive information"""
        return {
            'error_id': self.error_id,
            'message': self.user_message,
            'category': self.category,
            'severity': self.severity,
            'suggestions': self.suggestions,
            'error_code': self.error_code,
            'timestamp': self.timestamp.isoformat()
        }
    
    def to_copyable_text(self) -> str:
        """Generate copyable error text for debugging"""
        lines = [
            f"Error ID: {self.error_id}",
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Category: {self.category}",
            f"Severity: {self.severity}",
            f"Message: {self.message}",
            f"Error Code: {self.error_code or 'N/A'}",
        ]
        
        if self.context:
            lines.append(f"Endpoint: {self.context.endpoint or 'N/A'}")
            lines.append(f"Method: {self.context.method or 'N/A'}")
            if self.context.source_file:
                lines.append(f"Source: {self.context.source_file}:{self.context.line_number}")
            if self.context.function_name:
                lines.append(f"Function: {self.context.function_name}")
        
        if self.technical_details:
            lines.append(f"\nTechnical Details:\n{self.technical_details}")
        
        if self.stack_trace:
            lines.append(f"\nStack Trace:\n{self.stack_trace}")
        
        return "\n".join(lines)


class ErrorManager:
    """Central error management system"""
    
    def __init__(self):
        self.error_history: List[ErrorDetail] = []
        self.max_history = 1000  # Keep last 1000 errors in memory
        
        # User-friendly error messages mapping
        self.user_messages = {
            # Network errors
            "CONNECTION_REFUSED": "Unable to connect to the server. Please check if the service is running.",
            "CONNECTION_TIMEOUT": "Connection timed out. The server might be busy or unreachable.",
            "DNS_RESOLUTION_FAILED": "Unable to resolve the domain name. Please check the URL.",
            "SSL_ERROR": "Secure connection failed. The certificate might be invalid.",
            
            # Import errors
            "INVALID_M3U_FORMAT": "The playlist file is not in a valid M3U format.",
            "INVALID_EPG_FORMAT": "The EPG file is not in a valid XMLTV format.",
            "DUPLICATE_SOURCE": "This source has already been imported.",
            "IMPORT_SIZE_LIMIT": "The file is too large. Maximum allowed size is {max_size}.",
            "UNSUPPORTED_ENCODING": "The file encoding is not supported. Please use UTF-8.",
            
            # Database errors
            "DUPLICATE_ENTRY": "This item already exists in the database.",
            "FOREIGN_KEY_VIOLATION": "Cannot delete this item as it's being used elsewhere.",
            "DATABASE_LOCKED": "Database is temporarily locked. Please try again.",
            
            # Authentication errors
            "INVALID_CREDENTIALS": "Invalid username or password.",
            "TOKEN_EXPIRED": "Your session has expired. Please log in again.",
            "INSUFFICIENT_PERMISSIONS": "You don't have permission to perform this action.",
            
            # Validation errors
            "REQUIRED_FIELD_MISSING": "Required field '{field_name}' is missing.",
            "INVALID_FORMAT": "Invalid format for '{field_name}'. Expected: {expected_format}.",
            "VALUE_OUT_OF_RANGE": "Value for '{field_name}' is out of allowed range.",
        }
        
        # Suggestion mappings
        self.suggestions = {
            "CONNECTION_REFUSED": [
                "Verify the URL is correct",
                "Check if the server is online",
                "Try again in a few minutes",
                "Check your firewall settings"
            ],
            "INVALID_M3U_FORMAT": [
                "Ensure the file starts with #EXTM3U",
                "Check for proper line formatting",
                "Validate the file with an M3U validator",
                "Try a different M3U source"
            ],
            "TOKEN_EXPIRED": [
                "Click here to go to the login page",
                "Clear your browser cache and cookies",
                "Use 'Remember Me' option when logging in"
            ]
        }
    
    def create_error(
        self,
        exception: Exception,
        category: ErrorCategory,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[ErrorContext] = None,
        error_code: Optional[str] = None,
        user_message: Optional[str] = None,
        suggestions: Optional[List[str]] = None
    ) -> ErrorDetail:
        """Create a detailed error object from an exception"""
        
        # Generate unique error ID
        error_id = str(uuid.uuid4())
        
        # Extract stack trace
        stack_trace = traceback.format_exc()
        
        # Get frame info for source location
        tb = traceback.extract_tb(exception.__traceback__)
        if tb:
            last_frame = tb[-1]
            if context:
                context.source_file = last_frame.filename
                context.line_number = last_frame.lineno
                context.function_name = last_frame.name
        
        # Determine user message
        if not user_message:
            user_message = self.user_messages.get(
                error_code,
                "An unexpected error occurred. Please try again or contact support."
            )
        
        # Format user message with any available data
        if "{" in user_message and hasattr(exception, '__dict__'):
            try:
                user_message = user_message.format(**exception.__dict__)
            except:
                pass
        
        # Get suggestions
        if not suggestions and error_code:
            suggestions = self.suggestions.get(error_code, [])
        
        # Create error detail
        error_detail = ErrorDetail(
            error_id=error_id,
            timestamp=datetime.utcnow(),
            severity=severity,
            category=category,
            message=str(exception),
            user_message=user_message,
            technical_details=repr(exception),
            stack_trace=stack_trace,
            context=context,
            suggestions=suggestions,
            error_code=error_code
        )
        
        # Log the error
        self._log_error(error_detail)
        
        # Store in history
        self._store_error(error_detail)
        
        return error_detail
    
    def _log_error(self, error: ErrorDetail):
        """Log error with appropriate level"""
        log_message = f"[{error.error_id}] {error.category}: {error.message}"
        
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error.severity == ErrorSeverity.ERROR:
            logger.error(log_message)
        elif error.severity == ErrorSeverity.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # Log full details at debug level
        logger.debug(f"Error details: {error.to_dict()}")
    
    def _store_error(self, error: ErrorDetail):
        """Store error in history with size limit"""
        self.error_history.append(error)
        
        # Maintain size limit
        if len(self.error_history) > self.max_history:
            self.error_history = self.error_history[-self.max_history:]
    
    def get_error_by_id(self, error_id: str) -> Optional[ErrorDetail]:
        """Retrieve error by ID"""
        for error in reversed(self.error_history):
            if error.error_id == error_id:
                return error
        return None
    
    def get_recent_errors(
        self,
        limit: int = 10,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None
    ) -> List[ErrorDetail]:
        """Get recent errors with optional filtering"""
        errors = self.error_history[-limit:]
        
        if category:
            errors = [e for e in errors if e.category == category]
        
        if severity:
            errors = [e for e in errors if e.severity == severity]
        
        return list(reversed(errors))


# Global error manager instance
error_manager = ErrorManager()


# FastAPI exception handlers
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with our error system"""
    context = ErrorContext(
        endpoint=str(request.url),
        method=request.method,
        request_id=request.headers.get("X-Request-ID")
    )
    
    # Determine category based on status code
    category = ErrorCategory.SYSTEM
    if 400 <= exc.status_code < 500:
        if exc.status_code == 401:
            category = ErrorCategory.AUTHENTICATION
        elif exc.status_code == 403:
            category = ErrorCategory.AUTHORIZATION
        elif exc.status_code == 422:
            category = ErrorCategory.VALIDATION
    
    error = error_manager.create_error(
        exception=exc,
        category=category,
        context=context,
        user_message=exc.detail
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error.to_user_dict(),
            "copyable_error": error.to_copyable_text()
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    context = ErrorContext(
        endpoint=str(request.url),
        method=request.method,
        request_id=request.headers.get("X-Request-ID")
    )
    
    error = error_manager.create_error(
        exception=exc,
        category=ErrorCategory.SYSTEM,
        severity=ErrorSeverity.ERROR,
        context=context
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": error.to_user_dict(),
            "copyable_error": error.to_copyable_text()
        }
    )


# Utility functions for common error scenarios
def handle_import_error(exception: Exception, source_url: str, user_id: Optional[int] = None) -> ErrorDetail:
    """Handle import-specific errors"""
    context = ErrorContext(
        user_id=user_id,
        additional_data={"source_url": source_url}
    )
    
    error_code = None
    if "codec" in str(exception).lower():
        error_code = "UNSUPPORTED_ENCODING"
    elif "EXTM3U" in str(exception):
        error_code = "INVALID_M3U_FORMAT"
    elif "connection" in str(exception).lower():
        error_code = "CONNECTION_REFUSED"
    
    return error_manager.create_error(
        exception=exception,
        category=ErrorCategory.IMPORT,
        context=context,
        error_code=error_code
    )


def handle_database_error(exception: Exception, operation: str, user_id: Optional[int] = None) -> ErrorDetail:
    """Handle database-specific errors"""
    context = ErrorContext(
        user_id=user_id,
        additional_data={"operation": operation}
    )
    
    error_code = None
    if "UNIQUE constraint" in str(exception):
        error_code = "DUPLICATE_ENTRY"
    elif "FOREIGN KEY" in str(exception):
        error_code = "FOREIGN_KEY_VIOLATION"
    elif "locked" in str(exception).lower():
        error_code = "DATABASE_LOCKED"
    
    return error_manager.create_error(
        exception=exception,
        category=ErrorCategory.DATABASE,
        context=context,
        error_code=error_code
    )