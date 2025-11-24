"""Application configuration using Pydantic Settings."""

import os
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# NOTE: logfire.configure() was removed from here to prevent conflicts with test configuration.
# Logfire should be configured once at application startup (main.py via observability/logfire_config.py)
# or in pytest hooks (conftest.py). Calling configure() at module import time creates a local-only
# instance that prevents proper remote logging and pydantic-ai instrumentation.


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings are validated at startup to ensure the application
    has the required configuration before it starts.
    """

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
