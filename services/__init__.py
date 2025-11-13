"""
Services module for external integrations and business logic.
"""

from services.supabase import get_supabase_client

__all__ = ["get_supabase_client"]
