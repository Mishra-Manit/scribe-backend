"""
Redis configuration for Celery broker and result backend.

This module provides Redis connection settings with support for
both local development and production environments.
"""
from typing import Optional
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    """Redis configuration settings."""

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    @property
    def broker_url(self) -> str:
        """
        Construct Celery broker URL.
        """
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def result_backend(self) -> str:
        """
        Construct Celery result backend URL.
        """
        # Use a different DB for result backend (db+1)
        result_db = self.redis_db + 1
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{result_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{result_db}"


# Global instance
redis_settings = RedisSettings()
