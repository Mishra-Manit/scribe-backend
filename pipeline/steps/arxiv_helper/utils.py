"""
ArXiv Helper Utilities

ArXiv API utilities for paper search.
"""

import asyncio
import arxiv
import logfire
from typing import List

from .models import ArxivPaper

# ArXiv search timeout configuration (in seconds)
ARXIV_SEARCH_TIMEOUT = 30


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

        return papers

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
    max_results: int = 5,
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
            "ArXiv search completed successfully",
            papers_found=len(papers),
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