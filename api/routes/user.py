"""
User management API endpoints.

This module provides endpoints for user profile initialization and retrieval.
All endpoints require valid Supabase JWT authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.user import User
from database import get_db
from api.dependencies import get_supabase_user, get_current_user
from schemas.auth import SupabaseUser, UserResponse, UserInit


router = APIRouter(prefix="/api/user", tags=["User Management"])


@router.post("/init", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def initialize_user_profile(
    user_init: UserInit,
    supabase_user: SupabaseUser = Depends(get_supabase_user),
    db: Session = Depends(get_db),
):
    """
    Initialize a user profile in the local database.

    This endpoint should be called ONCE after a user signs up via Supabase Auth.
    It creates a corresponding user record in our local database with the user's
    Supabase Auth ID.

    **Authentication**: Requires valid Supabase JWT token in Authorization header.

    **Idempotent**: If the user already exists, returns the existing profile.

    Args:
        user_init: Initialization data with display_name (auto-derived from OAuth by frontend)
        supabase_user: Validated user from JWT token (injected by dependency)
        db: Database session (injected by dependency)

    Returns:
        UserResponse: Created or existing user profile

    Raises:
        HTTPException 500: If database operation fails
        HTTPException 401: If JWT token is invalid (handled by dependency)
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.id == supabase_user.id).first()

    if existing_user:
        # User already initialized - return existing profile
        return existing_user

    # Create new user in database
    new_user = User(
        id=supabase_user.id,
        email=supabase_user.email,
        display_name=user_init.display_name,
        generation_count=0,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError as e:
        db.rollback()
        # This could happen if another request created the user concurrently
        # Try to fetch the existing user
        existing_user = db.query(User).filter(User.id == supabase_user.id).first()
        if existing_user:
            return existing_user
        # If still not found, something else went wrong
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user due to integrity constraint: {str(e)}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}",
        )


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Get the current authenticated user's profile.

    This endpoint returns the full user profile from our local database.
    The user must have been initialized via POST /api/user/init first.

    **Authentication**: Requires valid Supabase JWT token in Authorization header.

    Args:
        current_user: Authenticated user from database (injected by dependency)

    Returns:
        UserResponse: User profile with all fields

    Raises:
        HTTPException 401: If JWT token is invalid (handled by dependency)
        HTTPException 403: If user is not initialized in database (handled by dependency)
    """
    # The dependency already fetched and validated the user
    # If we reach this point, current_user is a valid User model instance
    return current_user
