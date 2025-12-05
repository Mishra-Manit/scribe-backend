"""
Supabase client singleton for backend operations.

This module provides a singleton Supabase client instance using the service role key
for administrative operations like JWT validation and database operations.
"""

import logfire
from supabase import create_client, Client
from config import settings

# Global singleton instance
_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    """
    Get or create the Supabase client singleton.

    Uses the service role key for backend operations with full permissions.
    The client is lazily initialized on first access.

    Returns:
        Client: Supabase client instance

    Raises:
        ValueError: If Supabase configuration is missing
        Exception: If client initialization fails
    """
    global _supabase_client

    if _supabase_client is None:
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is not configured")
        if not settings.supabase_service_role_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is not configured")

        try:
            _supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key
            )
        except Exception as e:
            logfire.error(
                "Failed to initialize Supabase client",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    return _supabase_client


def get_supabase_client_safe() -> Client | None:
    """Get Supabase client without raising exceptions."""
    try:
        return get_supabase_client()
    except Exception:
        return None
