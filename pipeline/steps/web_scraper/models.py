"""
Web Scraper Step Models

Pydantic models for scraping results and validation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Summary(BaseModel):
    """LLM summary output."""

    summary: str = Field(description="Summarized content")


class ScrapedPage(BaseModel):
    """Single scraped webpage."""

    url: str = Field(description="Source URL")

    title: Optional[str] = Field(
        description="Page title",
        default=None,
        max_length=500
    )

    content: str = Field(
        description="Cleaned text content from page",
        max_length=10000
    )

    word_count: int = Field(
        description="Word count of content",
        ge=0
    )

    scrape_time_seconds: float = Field(
        description="Time taken to scrape this page",
        default=0.0
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is non-empty after cleaning"""
        if not v.strip():
            raise ValueError("Content cannot be empty")
        return v.strip()


class ScrapingResult(BaseModel):
    """Complete result from web scraping step."""

    pages_scraped: List[ScrapedPage] = Field(
        description="Successfully scraped pages",
        default_factory=list
    )

    failed_urls: List[str] = Field(
        description="URLs that failed to scrape",
        default_factory=list
    )

    total_attempts: int = Field(
        description="Total URLs attempted",
        ge=0
    )

    total_content_length: int = Field(
        description="Combined character count of all content",
        ge=0
    )

    @property
    def success_rate(self) -> float:
        """Calculate scraping success rate"""
        if self.total_attempts == 0:
            return 0.0
        return len(self.pages_scraped) / self.total_attempts