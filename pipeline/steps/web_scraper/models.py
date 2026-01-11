"""Web Scraper Step Models."""

from typing import Optional
from pydantic import BaseModel, Field


class ScrapingMetadata(BaseModel):
    """Metadata from dual-query scraping operation."""
    source: str = Field(default="exa_dual", description="Search provider")
    success: bool
    citation_count: int = 0
    background_length: Optional[int] = None
    publications_length: Optional[int] = None
    combined_length: Optional[int] = None
