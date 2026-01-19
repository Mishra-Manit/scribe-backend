"""
API route handlers.
"""

from api.routes.user import router as user_router
from api.routes.email import router as email_router
from api.routes.template import router as template_router
from api.routes.queue import router as queue_router

__all__ = ["user_router", "email_router", "template_router", "queue_router"]
