"""
ArXiv Helper Utilities

ArXiv API utilities and relevance scoring.
"""

import arxiv
import logfire
from typing import List
from datetime import datetime

from .models import ArxivPaper


def search_arxiv(
    author_name: str,
    max_results: int = 20,
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


def calculate_relevance_score(
    paper: ArxivPaper,
    recipient_name: str,
    recipient_interest: str
) -> float:
    """
    Calculate relevance score for a paper.

    Scoring factors:
    - Author match (0.4): Is recipient an author?
    - Topic match (0.3): Does abstract mention interest?
    - Recency (0.2): More recent papers score higher
    - Primary author (0.1): Bonus if recipient is first author

    Args:
        paper: ArxivPaper to score
        recipient_name: Expected author name
        recipient_interest: Research interest/topic

    Returns:
        Relevance score (0-1)
    """
    score = 0.0

    # Extract last name for matching
    recipient_last_name = recipient_name.split()[-1].lower()

    # Factor 1: Author match (0.4 weight)
    author_match = any(
        recipient_last_name in author.lower()
        for author in paper.authors
    )

    if author_match:
        score += 0.4

    # Factor 2: Topic match in abstract (0.3 weight)
    interest_keywords = recipient_interest.lower().split()
    abstract_lower = paper.abstract.lower()

    keyword_matches = sum(
        1 for keyword in interest_keywords
        if keyword in abstract_lower
    )

    # Normalize by number of keywords
    topic_score = min(keyword_matches / len(interest_keywords), 1.0) * 0.3
    score += topic_score

    # Factor 3: Recency (0.2 weight)
    # Papers from last 5 years get full score, older papers decay
    current_year = datetime.now().year
    years_old = current_year - paper.year

    if years_old <= 5:
        recency_score = 0.2
    elif years_old <= 10:
        recency_score = 0.1
    else:
        recency_score = 0.0

    score += recency_score

    # Factor 4: Primary author bonus (0.1 weight)
    if paper.authors and recipient_last_name in paper.authors[0].lower():
        score += 0.1

    return min(score, 1.0)  # Cap at 1.0


def filter_top_papers(
    papers: List[ArxivPaper],
    recipient_name: str,
    recipient_interest: str,
    top_n: int = 5
) -> List[ArxivPaper]:
    """
    Score and filter papers to top N most relevant.

    Args:
        papers: List of papers to filter
        recipient_name: Recipient name
        recipient_interest: Research interest
        top_n: Number of top papers to return

    Returns:
        Sorted list of top N papers
    """
    # Score all papers
    for paper in papers:
        paper.relevance_score = calculate_relevance_score(
            paper=paper,
            recipient_name=recipient_name,
            recipient_interest=recipient_interest
        )

    # Sort by relevance (descending)
    sorted_papers = sorted(
        papers,
        key=lambda p: p.relevance_score,
        reverse=True
    )

    # Return top N
    top_papers = sorted_papers[:top_n]

    logfire.info(
        "Papers filtered",
        total_papers=len(papers),
        top_papers=len(top_papers),
        avg_relevance=sum(p.relevance_score for p in top_papers) / len(top_papers) if top_papers else 0.0
    )

    return top_papers