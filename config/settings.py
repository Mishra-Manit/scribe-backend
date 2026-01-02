"""Application configuration using Pydantic Settings."""

import os
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# NOTE: Logfire configured in main.py/conftest.py, not here (prevents test conflicts)


class Settings(BaseSettings):
    """Application settings loaded from environment variables with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application Settings
    environment: str = Field(default="development", description="Environment: development, staging, production")
    debug: bool = Field(default=False, description="Debug mode")

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # CORS Settings
    allowed_origins: str = Field(
        default="http://localhost:3000, https://scribe.manitmishra.com",
        description="Comma-separated list of allowed CORS origins"
    )

    # Database Configuration (Supabase Direct Connection)
    db_user: str = Field(..., description="Database user")
    db_password: str = Field(..., description="Database password")
    db_host: str = Field(..., description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(..., description="Database name")

    # Database Connection Pool Configuration
    db_pool_size: int = Field(default=10, description="SQLAlchemy connection pool size")
    db_pool_max_overflow: int = Field(default=20, description="SQLAlchemy pool overflow")
    db_pool_recycle: int = Field(default=300, description="Recycle connections every N seconds")
    db_connect_timeout: int = Field(default=10, description="Connection timeout in seconds")
    db_statement_timeout: int = Field(default=30000, description="Statement timeout in milliseconds")

    # Supabase Configuration
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_service_role_key: str = Field(..., description="Supabase service role key for backend operations")

    # External APIs
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    google_api_key: str = Field(default="", description="Google API key for Custom Search")
    google_cse_id: str = Field(default="", description="Google Custom Search Engine ID")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Observability
    logfire_token: str = Field(default="", description="Logfire observability token")

    # Usage Limits
    template_generation_limit: int = Field(
        default=5,
        description="Maximum templates per user"
    )
    pagination_max_limit: int = Field(
        default=100,
        description="Maximum pagination limit for list endpoints"
    )
    pagination_default_limit: int = Field(
        default=20,
        description="Default pagination limit"
    )

    @field_validator("allowed_origins")
    @classmethod
    def parse_origins(cls, v: str) -> List[str]:
        """Parse comma-separated origins into a list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("db_host")
    @classmethod
    def validate_db_host(cls, v: str) -> str:
        """Validate that the database host is provided."""
        if not v.strip():
            raise ValueError("Database host cannot be empty")
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"

    @property
    def is_celery_worker(self) -> bool:
        """
        Detect if running as a Celery worker on Render.
        Workers need smaller pools to reduce stale connections when they're idle
        and then suddenly need a database connection.
        """
        render_service_name = os.getenv("RENDER_SERVICE_NAME", "").lower()
        return "backend" in render_service_name

    @property
    def effective_db_pool_size(self) -> int:
        """
        Return pool size adjusted for Celery workers.
        Workers use smaller pools (2) vs API servers (10) to reduce stale connections.
        """
        return 2 if self.is_celery_worker else self.db_pool_size

    @property
    def effective_db_pool_max_overflow(self) -> int:
        """
        Return max overflow adjusted for Celery workers.
        Workers use smaller overflow (5) vs API servers (20).
        """
        return 5 if self.is_celery_worker else self.db_pool_max_overflow

    @property
    def database_url(self) -> str:
        """
        Construct the SQLAlchemy database URL for Supabase direct connection.
        Uses psycopg2 driver and requires SSL mode for Supabase connections.
        """
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        )


# Create a singleton instance
settings = Settings()

# Ensure SDKs that read ANTHROPIC_API_KEY at import time see the configured value.
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)


def get_settings() -> "Settings":
    """Return the singleton settings instance.

    Provided for backward-compatibility with modules that import
    `config.settings.get_settings` instead of the `settings` variable.
    """
    return settings
