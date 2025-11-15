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

    relevance_score: float = Field(
        description="Relevance score (0-1, higher is more relevant)",
        ge=0.0,
        le=1.0,
        default=0.0
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
            "abstract": self.abstract[:500],  # Truncate for brevity
            "authors": self.authors,
            "year": self.year,
            "url": self.arxiv_url,
            "relevance_score": self.relevance_score
        }


class ArxivSearchResult(BaseModel):
    """Complete result from ArXiv search."""

    papers_found: List[ArxivPaper] = Field(
        description="All papers found",
        default_factory=list
    )

    papers_filtered: List[ArxivPaper] = Field(
        description="Papers after relevance filtering (top 5)",
        default_factory=list
    )

    search_query: str = Field(
        description="Query used for ArXiv search"
    )

    total_results: int = Field(
        description="Total results from ArXiv API",
        ge=0
    )