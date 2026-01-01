"""Authentication and authorization dependencies for JWT validation."""

from typing import Annotated
from fastapi import Depends, HTTPException, status, Security, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from gotrue.errors import AuthApiError

from services.supabase import get_supabase_client
from database import get_db
from models.user import User
from schemas.auth import SupabaseUser
from config.settings import settings


# HTTP Bearer security scheme (checks for "Authorization: Bearer ..." header)
security_scheme = HTTPBearer()


async def get_supabase_user(
    creds: HTTPAuthorizationCredentials = Security(security_scheme),
) -> SupabaseUser:
    """
    Validate JWT token via Supabase API. Does not check local database.

    Raises:
        HTTPException: 401 if token invalid, 503 if Supabase unavailable
    """
    token = creds.credentials

    # Get Supabase client
    try:
        supabase = get_supabase_client()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Supabase client not available: {str(e)}",
        )

    # Validate token with Supabase
    try:
        # This makes a network call to Supabase to validate the token
        supabase_response = supabase.auth.get_user(token)

        # Extract user data from response
        if not supabase_response or not supabase_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no user data returned",
            )

        user_data = supabase_response.user

        # Return validated user data
        return SupabaseUser(
            id=user_data.id,
            email=user_data.email,
        )

    except AuthApiError as e:
        # Supabase-specific auth errors (invalid/expired token, etc.)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e.message}",
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
        )


async def get_current_user(
    supabase_user: SupabaseUser = Depends(get_supabase_user),
    db: Session = Depends(get_db),
) -> User:
    """
    Get authenticated user from local database after JWT validation.

    Raises:
        HTTPException: 403 if user not initialized (requires POST /api/user/init)
    """
    # Query local database for user
    db_user = db.query(User).filter(User.id == supabase_user.id).first()

    if not db_user:
        # Valid Supabase user, but not initialized in our backend
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not initialized. Please call POST /api/user/init first.",
        )

    return db_user


def pagination_params(
    limit: int = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0)
) -> dict:
    """Reusable pagination with configurable defaults and max limits from settings."""
    # Use configured defaults and enforce maximum
    if limit is None:
        limit = settings.pagination_default_limit
    limit = min(limit, settings.pagination_max_limit)

    return {"limit": limit, "offset": offset}


# Type alias for dependency injection
PaginationParams = Annotated[dict, Depends(pagination_params)]
