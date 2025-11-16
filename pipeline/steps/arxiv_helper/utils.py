"""
ArXiv Helper Utilities

ArXiv API utilities for paper search.
"""

import arxiv
import logfire
from typing import List

from .models import ArxivPaper


def search_arxiv(
    author_name: str,
    max_results: int = 5,
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance
) -> List[ArxivPaper]:
    """
    Search ArXiv for papers by author.

    Args:
        author_name: Author name to search
        max_results: Maximum papers to fetch
        sort_by: Sort criterion

    Returns:
        List of ArxivPaper objects

    Note:
        arxiv library doesn't support async, but we wrap it
        for consistency with other steps.
    """
    # Build search query
    # Format: au:"Last Name, First Name" for better results
    query = f'au:"{author_name}"'

    logfire.info(
        "Searching ArXiv",
        query=query,
        max_results=max_results
    )

    try:
        # Create search client
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_by
        )

        papers = []

        # Fetch results (synchronous)
        for result in search.results():
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

        logfire.info(
            "ArXiv search completed",
            papers_found=len(papers)
        )

        return papers

    except Exception as e:
        logfire.error(
            "ArXiv search failed",
            error=str(e),
            query=query
        )
        return []