"""Application configuration using Pydantic Settings."""

import os
from typing import List
from pydantic import Field, field_validator, model_validator
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
    db_port: int = Field(default=6543, description="Transaction pooler port (6543) or Session pooler port (5432)")
    db_name: str = Field(..., description="Database name")

    # Database Connection Configuration
    db_connect_timeout: int = Field(
        default=30,
        description="Connection timeout in seconds (30s handles cold starts and network latency)"
    )
    db_statement_timeout: int = Field(default=30000, description="Statement timeout in milliseconds")

    # Supabase Configuration
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_service_role_key: str = Field(..., description="Supabase service role key for backend operations")

    # External APIs
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    exa_api_key: str = Field(default="", description="Exa API key for web search")

    # Optional API keys for alternative LLM providers
    fireworks_api_key: str = Field(default="", description="Fireworks AI API key (optional, for DeepSeek v3.2 and other models)")

    # LLM Model Configuration (hot-swappable via environment variables)
    template_parser_model: str = Field(
        #default="anthropic:claude-haiku-4-5",
        default="fireworks:accounts/fireworks/models/deepseek-v3p2",
    )
    email_composer_model: str = Field(
        #default="anthropic:claude-sonnet-4-5",
        default="fireworks:accounts/fireworks/models/deepseek-v3p2",
    )
    template_generator_model: str = Field(
        #default="anthropic:claude-haiku-4-5",
        default="fireworks:accounts/fireworks/models/deepseek-v3p2",
    )

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

    @field_validator("db_port")
    @classmethod
    def validate_db_port_matches_host(cls, v: int) -> int:
        """
        Validate that DB_PORT matches the connection mode.
        - Port 6543: Transaction pooler (for auto-scaling, serverless)
        - Port 5432: Session pooler or direct connection
        """
        if v not in [5432, 6543]:
            raise ValueError(
                f"Invalid database port: {v}. "
                "Use 6543 for transaction pooler or 5432 for session pooler."
            )
        return v

    @model_validator(mode="after")
    def validate_pooler_configuration(self):
        """
        Warn if DB_HOST and DB_PORT don't match expected transaction pooler setup.
        Transaction pooler should use:
        - Port 6543
        - Host containing '.pooler.supabase.com'
        """
        if self.db_port == 6543:
            if ".pooler.supabase.com" not in self.db_host:
                import warnings
                warnings.warn(
                    f"Port 6543 is for transaction pooler, but DB_HOST "
                    f"({self.db_host}) doesn't contain '.pooler.supabase.com'. "
                    "Verify you're using the correct connection string."
                )

        return self

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
