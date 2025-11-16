"""
Quick ArXiv Query Tester

A minimal test script for experimenting with different ArXiv queries.
Modify the QUERIES list below to test different author searches.

Usage:
    python pipeline/steps/arxiv_helper/tests/quick_arxiv_test.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from pipeline.steps.arxiv_helper.utils import search_arxiv
from config.settings import settings
from observability.logfire_config import LogfireConfig
import arxiv


def print_papers(author_name: str, papers: list, max_results: int):
    """Display papers in a clean format."""
    print(f"\n{'='*80}")
    print(f"QUERY: {author_name}")
    print(f"{'='*80}")
    print(f"Papers found: {len(papers)} (max requested: {max_results})\n")

    if not papers:
        print("  ❌ No papers found\n")
        return

    for i, paper in enumerate(papers, 1):
        print(f"📄 Paper {i}")
        print(f"   Title: {paper.title}")
        print(f"   Authors: {', '.join(paper.authors[:3])}")
        if len(paper.authors) > 3:
            print(f"            ... +{len(paper.authors) - 3} more")
        print(f"   Year: {paper.year}")
        print(f"   Category: {paper.primary_category}")
        print(f"   ArXiv ID: {paper.arxiv_id}")
        print(f"   URL: {paper.arxiv_url}")
        print(f"   Abstract: {paper.abstract[:150]}...")
        print()


def main():
    """Run ArXiv queries and display results."""

    # Initialize Logfire for observability (optional but recommended)
    if settings.logfire_token:
        LogfireConfig.initialize(token=settings.logfire_token)
        print("✓ Logfire observability enabled\n")
    else:
        # Suppress warnings if no token is available
        os.environ['LOGFIRE_IGNORE_NO_CONFIG'] = '1'
        print("⚠ Logfire token not set - observability disabled\n")

    # ========================================================================
    # MODIFY THIS LIST TO TEST DIFFERENT QUERIES
    # ========================================================================
    QUERIES = [
        "Geoffrey Hinton",           # AI pioneer
        "Yann LeCun",                # Deep learning expert
        "Andrew Ng",                 # ML educator
        # Add your own queries here:
        # "Your Author Name",
    ]

    # Max papers to fetch per query
    MAX_RESULTS = 5

    # Sort order: Relevance, SubmittedDate, or LastUpdatedDate
    SORT_BY = arxiv.SortCriterion.Relevance

    # ========================================================================

    print("\n" + "="*80)
    print("ARXIV QUICK TEST".center(80))
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  Max results per query: {MAX_RESULTS}")
    print(f"  Sort by: {SORT_BY.name}")
    print(f"  Total queries: {len(QUERIES)}")

    # Run each query
    for query in QUERIES:
        papers = search_arxiv(
            author_name=query,
            max_results=MAX_RESULTS,
            sort_by=SORT_BY
        )
        print_papers(query, papers, MAX_RESULTS)

    print("="*80)
    print("TEST COMPLETE".center(80))
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
