"""
Web Scraper Step

Fetches and synthesizes professor information using Exa Search API.
"""

from .main import WebScraperStep
from .exa_search import ExaSearchClient, ExaCitation, ExaAnswerResult

__all__ = ["WebScraperStep", "ExaSearchClient", "ExaCitation", "ExaAnswerResult"]
