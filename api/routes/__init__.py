"""
API route handlers.
"""

from api.routes.user import router as user_router
from api.routes.email import router as email_router

__all__ = ["user_router", "email_router"]
