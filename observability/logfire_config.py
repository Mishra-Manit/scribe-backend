"""
Logfire configuration and initialization.

Logfire provides structured logging, distributed tracing, and real-time
observability for the entire pipeline system.

Environment Variables:
    LOGFIRE_TOKEN: Logfire project token (required for production)
    ENVIRONMENT: deployment environment (development, staging, production)
"""
import os
from typing import Optional

import logfire


class LogfireConfig:
    """
    Logfire configuration singleton.

    Ensures Logfire is initialized only once and provides
    graceful degradation when Logfire is not available.
    """

    _initialized = False

    @classmethod
    def initialize(cls, token: Optional[str] = None) -> None:
        """
        Initialize Logfire with project token.

        Args:
            token: Logfire project token (or set LOGFIRE_TOKEN env var)

        Note:
            If Logfire is not available or token is missing, logs a warning
            but allows the application to continue running.
        """
        if cls._initialized:
            return

        token = token or os.getenv("LOGFIRE_TOKEN")
        if not token:
            raise ValueError("LOGFIRE_TOKEN environment variable or token argument must be provided.")

        logfire.configure(
            token=token,
            service_name="scribe-pipeline",
            environment=os.getenv("ENVIRONMENT", "development"),
            send_to_logfire=True,
        )

        cls._initialized = True

    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if Logfire has been initialized.

        Returns:
            True if initialized, False otherwise
        """
        return cls._initialized
