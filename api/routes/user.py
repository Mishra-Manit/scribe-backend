"""User profile initialization and retrieval endpoints."""

import logfire
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
    Initialize user profile after Supabase signup.

    Idempotent - returns existing profile if already initialized.
    """
    logfire.info(
        "User init endpoint called",
        user_id=supabase_user.id,
        email=supabase_user.email
    )

    # Check if user already exists
    logfire.info("Querying database for existing user", user_id=supabase_user.id)
    existing_user = db.query(User).filter(User.id == supabase_user.id).first()
    logfire.info("Database query completed", found_existing=bool(existing_user))

    if existing_user:
        # User already initialized - return existing profile
        logfire.info("Returning existing user profile", user_id=supabase_user.id)
        return existing_user

    # Create new user in database
    logfire.info("Creating new user in database", user_id=supabase_user.id)
    new_user = User(
        id=supabase_user.id,
        email=supabase_user.email,
        display_name=user_init.display_name,
        generation_count=0,
    )

    try:
        logfire.info("Adding new user to session", user_id=supabase_user.id)
        db.add(new_user)
        logfire.info("Committing transaction", user_id=supabase_user.id)
        db.commit()
        logfire.info("Refreshing user object", user_id=supabase_user.id)
        db.refresh(new_user)
        logfire.info("User created successfully", user_id=supabase_user.id)
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
    """Get current user's profile. Requires initialized account."""
    # The dependency already fetched and validated the user
    # If we reach this point, current_user is a valid User model instance
    return current_user
