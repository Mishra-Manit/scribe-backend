"""
FastAPI dependencies for authentication and authorization.

This module provides reusable dependencies that validate JWT tokens,
verify user authentication, and inject user data into route handlers.
"""

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
    Dependency to validate Supabase JWT token and return user data.

    This validates the token using the Supabase service client's remote
    validation endpoint. It DOES NOT check the local database.

    Args:
        creds: HTTP Authorization credentials (Bearer token)

    Returns:
        SupabaseUser: Validated user data from token (id and email)

    Raises:
        HTTPException 401: If token is invalid, expired, or missing
        HTTPException 503: If Supabase client is not initialized
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
    Dependency to get the authenticated user from the local database.

    This depends on get_supabase_user(), so the JWT token is already
    validated before this function is called. It then fetches the user
    from our local database.

    Args:
        supabase_user: Validated user data from JWT token
        db: Database session

    Returns:
        User: User model instance from local database

    Raises:
        HTTPException 403: If user exists in Supabase but not initialized in our database
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
    """
    Reusable pagination parameters with automatic validation.

    Args:
        limit: Maximum records to return (configurable via settings, default from config)
        offset: Number of records to skip (default 0)

    Returns:
        dict with 'limit' and 'offset' keys
    """
    # Use configured defaults and enforce maximum
    if limit is None:
        limit = settings.pagination_default_limit
    limit = min(limit, settings.pagination_max_limit)

    return {"limit": limit, "offset": offset}


# Type alias for dependency injection
PaginationParams = Annotated[dict, Depends(pagination_params)]
