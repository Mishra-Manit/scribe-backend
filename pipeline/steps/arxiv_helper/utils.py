"""
ArXiv Helper Utilities

ArXiv API utilities for paper search.
"""

import asyncio
import arxiv
import logfire
from typing import List

from .models import ArxivPaper
from datetime import datetime

# ArXiv search timeout configuration (in seconds)
ARXIV_SEARCH_TIMEOUT = 30

# Year recency filtering configuration
INITIAL_FETCH_COUNT = 15        # Fetch more papers for filtering
MIN_YEAR_THRESHOLD = 10          # Only include papers from last 10 years
MAX_FINAL_RESULTS = 5           # Return top 5 after filtering


def _filter_recent_papers(papers: List[ArxivPaper]) -> List[ArxivPaper]:
    """
    Filter papers to only include those from the last N years.
    """
    current_year = datetime.now().year
    cutoff_year = current_year - MIN_YEAR_THRESHOLD

    # Filter papers by year threshold
    recent_papers = [
        paper for paper in papers
        if paper.year >= cutoff_year
    ]

    logfire.info(
        "Filtered papers by recency",
        total_fetched=len(papers),
        after_filtering=len(recent_papers),
        cutoff_year=cutoff_year,
        years_included=[p.year for p in recent_papers[:5]]
    )

    # Return top 5 after filtering
    return recent_papers[:MAX_FINAL_RESULTS]

def _search_arxiv_sync(
    author_name: str,
    max_results: int,
    sort_by: arxiv.SortCriterion
) -> List[ArxivPaper]:
    """
    Synchronous ArXiv search implementation.

    Internal function - use search_arxiv() for timeout protection.

    Args:
        author_name: Author name to search
        max_results: Maximum papers to fetch
        sort_by: Sort criterion

    Returns:
        List of ArxivPaper objects
    """
    # Build search query
    # Format: au:"Last Name, First Name" for better results
    query = f'au:"{author_name}"'

    try:
        client = arxiv.Client(
            page_size=max_results,      # Fetch max_results per page (efficient)
            delay_seconds=0.5,          # Rate limiting: 0.5s between requests
            num_retries=2 
        )

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_by
        )

        papers = []

        for result in client.results(search):
            paper = ArxivPaper(
                title=result.title,
                abstract=result.summary,
                authors=[author.name for author in result.authors],
                published_date=result.published,
                arxiv_id=result.entry_id.split('/')[-1],  # Extract ID
                arxiv_url=result.entry_id,
                pdf_url=result.pdf_url,
                primary_category=result.primary_category
            )

            papers.append(paper)

        # Filter to recent papers (last 7 years) and limit to top 5
        filtered_papers = _filter_recent_papers(papers)
        return filtered_papers

    except Exception as e:
        logfire.error(
            "ArXiv sync search failed",
            error=str(e),
            error_type=type(e).__name__,
            query=query
        )
        raise  # Re-raise for async wrapper to handle


async def search_arxiv(
    author_name: str,
    max_results: int = INITIAL_FETCH_COUNT,  # Fetch 15 for filtering
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance,
    timeout: int = ARXIV_SEARCH_TIMEOUT
) -> List[ArxivPaper]:
    """
    Search ArXiv for papers by author with timeout protection.

    Args:
        author_name: Author name to search
        max_results: Maximum papers to fetch (default: 5)
        sort_by: Sort criterion (default: Relevance)
        timeout: Search timeout in seconds (default: 30)

    Returns:
        List of ArxivPaper objects
    """
    query = f'au:"{author_name}"'

    logfire.info(
        "Starting ArXiv search with timeout protection",
        query=query,
        max_results=max_results,
        timeout=timeout
    )

    try:
        # Run synchronous arxiv search in thread pool with timeout
        papers = await asyncio.wait_for(
            asyncio.to_thread(
                _search_arxiv_sync,
                author_name=author_name,
                max_results=max_results,
                sort_by=sort_by
            ),
            timeout=timeout
        )

        logfire.info(
            "ArXiv search completed successfully (after filtering)",
            papers_returned=len(papers),
            paper_years=[p.year for p in papers] if papers else [],
            paper_titles=[p.title for p in papers[:3]] if papers else []
        )

        return papers

    except asyncio.TimeoutError:
        logfire.warning(
            "ArXiv search timed out",
            query=query,
            timeout=timeout
        )
        # Return empty list to allow pipeline to continue
        return []

    except Exception as e:
        logfire.error(
            "ArXiv search failed",
            error=str(e),
            error_type=type(e).__name__,
            query=query
        )
        return []