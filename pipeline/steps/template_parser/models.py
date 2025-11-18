"""
Template Parser Step Models

Pydantic models for validating LLM responses and intermediate data.
"""

from typing import List
from pydantic import BaseModel, Field, field_validator
from pipeline.models.core import TemplateType


class TemplateAnalysis(BaseModel):
    """
    Structured analysis of an email template.

    This is the response format we expect from Claude.
    """

    template_type: TemplateType = Field(
        description="Type of template (RESEARCH, BOOK, or GENERAL)"
    )

    search_terms: List[str] = Field(
        description="1-2 search queries for Google Custom Search",
        min_length=1,
        max_length=2
    )

    placeholders: List[str] = Field(
        description="List of placeholder variables found in template",
        default_factory=list
    )

    @field_validator("search_terms")
    @classmethod
    def validate_search_terms(cls, v: List[str]) -> List[str]:
        """Ensure search terms are non-empty and reasonable length"""
        cleaned = [term.strip() for term in v if term.strip()]
        if not cleaned:
            raise ValueError("At least one search term is required")

        # Validate each term
        for term in cleaned:
            if len(term) < 3:
                raise ValueError(f"Search term too short: '{term}'")
            if len(term) > 200:
                raise ValueError(f"Search term too long: '{term}'")

        return cleaned

    class Config:
        json_schema_extra = {
            "example": {
                "template_type": "RESEARCH",
                "search_terms": [
                    "Dr. Jane Smith machine learning",
                    "Jane Smith publications research"
                ],
                "placeholders": ["{{name}}", "{{research}}", "{{university}}"]
            }
        }