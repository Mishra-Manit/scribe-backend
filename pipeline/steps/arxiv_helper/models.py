"""
ArXiv Helper Step Models

Pydantic models for academic paper data.
"""

from typing import List
from pydantic import BaseModel, Field
from datetime import datetime


class ArxivPaper(BaseModel):
    """Single academic paper from ArXiv."""

    title: str = Field(description="Paper title")

    abstract: str = Field(
        description="Paper abstract",
        max_length=5000
    )

    authors: List[str] = Field(
        description="List of author names",
        min_length=1
    )

    published_date: datetime = Field(
        description="Publication date"
    )

    arxiv_id: str = Field(
        description="ArXiv paper ID (e.g., '2301.12345')"
    )

    arxiv_url: str = Field(
        description="ArXiv paper URL"
    )

    pdf_url: str = Field(
        description="Direct PDF link"
    )

    primary_category: str = Field(
        description="Primary ArXiv category (e.g., 'cs.AI')"
    )

    @property
    def year(self) -> int:
        """Extract year from published_date"""
        return self.published_date.year

    @property
    def primary_author(self) -> str:
        """Get first author"""
        return self.authors[0] if self.authors else "Unknown"

    def to_dict(self) -> dict:
        """Convert to dict for PipelineData.arxiv_papers"""
        return {
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "published_date": self.published_date.isoformat(),
            "year": self.year,
            "arxiv_url": self.arxiv_url
        }