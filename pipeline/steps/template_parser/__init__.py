"""
Template Parser Step

Analyzes email templates using Anthropic Claude to extract:
- Search terms for web scraping
- Template type classification (RESEARCH/BOOK/GENERAL)
- Template characteristics (tone, placeholders, topics)
"""

from .main import TemplateParserStep

__all__ = ["TemplateParserStep"]