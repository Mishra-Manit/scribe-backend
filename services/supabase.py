"""
Supabase client singleton for backend operations.

This module provides a singleton Supabase client instance using the service role key
for administrative operations like JWT validation and database operations.
"""

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
        # Validate configuration
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is not configured")
        if not settings.supabase_service_role_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is not configured")

        try:
            _supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key
            )
            print(f" Supabase client initialized: {settings.supabase_url}")
        except Exception as e:
            print(f" Failed to initialize Supabase client: {e}")
            raise

    return _supabase_client


def get_supabase_client_safe() -> Client | None:
    """
    Get the Supabase client without raising exceptions.

    Useful for startup checks and health endpoints.

    Returns:
        Client | None: Supabase client instance or None if initialization fails
    """
    try:
        return get_supabase_client()
    except Exception:
        return None
