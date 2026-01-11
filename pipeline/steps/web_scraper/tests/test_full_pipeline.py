"""
Web Scraper Demo Script (Exa Dual-Query Strategy)

Demonstrates the web scraper pipeline using REAL Exa API calls:
- Dual parallel queries: background + publications
- AI-synthesized answers with deduplicated citations

Run: python pipeline/steps/web_scraper/tests/test_full_pipeline.py
"""

import asyncio
import os
from uuid import uuid4
from datetime import datetime

from config.settings import settings
from observability.logfire_config import LogfireConfig

# Import pipeline components
from pipeline.steps.web_scraper.main import WebScraperStep
from pipeline.models.core import PipelineData, TemplateType


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title: str):
    """Print a formatted subsection header."""
    print(f"\n--- {title} ---")


async def run_real_web_scraper_demo():
    """
    Demonstrate the web scraper with real Exa API calls.

    This shows how the pipeline works in production with actual data.
    """

    print_section("REAL WEB SCRAPER DEMONSTRATION (Exa Search API)")

    # ============================================================================
    # STEP 1: Configure the search
    # ============================================================================

    print_subsection("Configuration")

    # Choose a well-known researcher for reliable results
    recipient_name = "Dr. Geoffrey Hinton"
    recipient_interest = "deep learning and neural networks"

    # Search terms (used for context, Exa builds its own query)
    search_terms = [
        "Geoffrey Hinton deep learning research",
        "Geoffrey Hinton University of Toronto",
    ]

    print(f"Target Recipient: {recipient_name}")
    print(f"Research Interest: {recipient_interest}")
    print(f"Search Context:")
    for i, term in enumerate(search_terms, 1):
        print(f"  {i}. {term}")

    # ============================================================================
    # STEP 2: Create pipeline data
    # ============================================================================

    print_subsection("Creating Pipeline Data")

    pipeline_data = PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template="Dear {{name}}, I am interested in {{research}}.",
        recipient_name=recipient_name,
        recipient_interest=recipient_interest,
        template_type=TemplateType.RESEARCH,
        search_terms=search_terms,
    )

    print(f"Pipeline data created")
    print(f"  Task ID: {pipeline_data.task_id}")
    print(f"  Template Type: {pipeline_data.template_type.value}")

    # ============================================================================
    # STEP 3: Initialize web scraper
    # ============================================================================

    print_subsection("Initializing Web Scraper")

    scraper = WebScraperStep()

    print(f"Web scraper initialized (Exa Search API)")

    # ============================================================================
    # STEP 4: Execute the pipeline (REAL API CALLS!)
    # ============================================================================

    print_section("EXECUTING PIPELINE WITH REAL DATA")
    print("This will make dual Exa API calls (background + publications)...")
    print("This should complete in 10-20 seconds...\n")

    start_time = datetime.now()

    # Execute with real Exa Search API
    result = await scraper.execute(pipeline_data)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # ============================================================================
    # STEP 5: Display results
    # ============================================================================

    print_section("RESULTS")

    print_subsection("Execution Summary")
    print(f"Pipeline Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Total Duration: {duration:.2f} seconds")

    if not result.success:
        print(f"Error: {result.error}")
        return

    # ============================================================================
    # STEP 6: Show search statistics
    # ============================================================================

    print_subsection("Search Statistics (Dual Query)")

    metadata = pipeline_data.scraping_metadata

    print(f"Source: {metadata.get('source', 'unknown')}")
    print(f"Success: {metadata.get('success', False)}")
    print(f"Citation Count: {metadata.get('citation_count', 0)}")
    print(f"Background Length: {metadata.get('background_length', 0):,} chars")
    print(f"Publications Length: {metadata.get('publications_length', 0):,} chars")
    print(f"Combined Length: {metadata.get('combined_length', 0):,} chars")

    # ============================================================================
    # STEP 7: Show citation URLs
    # ============================================================================

    print_subsection("Citation URLs")

    if pipeline_data.scraped_urls:
        for i, url in enumerate(pipeline_data.scraped_urls, 1):
            print(f"  {i}. {url}")
    else:
        print("  (No citations)")

    # ============================================================================
    # STEP 8: Show content preview
    # ============================================================================

    print_subsection("Scraped Content (Full)")

    if pipeline_data.scraped_content:
        print(f"\n{pipeline_data.scraped_content}")
    else:
        print("  (No content)")

    # ============================================================================
    # STEP 9: Validate content quality
    # ============================================================================

    print_subsection("Content Quality Checks")

    content_lower = pipeline_data.scraped_content.lower()

    # Check for relevant keywords
    keywords = ["hinton", "deep learning", "neural network", "machine learning"]
    found_keywords = [kw for kw in keywords if kw in content_lower]

    print(f"Keywords Found: {', '.join(found_keywords) if found_keywords else 'None'}")
    print(f"Content Contains Relevant Info: {len(found_keywords) > 0}")
    print(f"Has Citations: {len(pipeline_data.scraped_urls) > 0}")

    # ============================================================================
    # Summary
    # ============================================================================

    print_section("DEMONSTRATION COMPLETE")

    print(f"Citation Count: {len(pipeline_data.scraped_urls)}")
    print(f"Answer Content: {len(pipeline_data.scraped_content):,} characters")
    print(f"Execution Time: {duration:.2f} seconds")
    print(f"\nThis demonstrates the Exa-powered web scraper pipeline:")
    print(f"  - Dual-query strategy: background + publications")
    print(f"  - Parallel Exa API calls for efficiency")
    print(f"  - Combined AI-synthesized answers with deduplicated citations")


# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("  WEB SCRAPER DEMONSTRATION - EXA SEARCH API")
    print("  This script uses REAL Exa API calls for search + synthesis")
    print("=" * 80)

    # Check for required environment variables using application settings
    required_vars = {
        "EXA_API_KEY": settings.exa_api_key,
    }
    missing_vars = [var for var, value in required_vars.items() if not value]

    if missing_vars:
        print("\n ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables in your .env file or environment.")
        exit(1)

    print("\n All required environment variables are set")

    # Initialize Logfire for observability (optional but recommended)
    if settings.logfire_token:
        LogfireConfig.initialize(token=settings.logfire_token)
        print("Logfire observability enabled - spans will be sent to remote server")
    else:
        # Suppress warnings if no token is available
        os.environ['LOGFIRE_IGNORE_NO_CONFIG'] = '1'
        print("Logfire token not set - observability disabled (no remote logging)")

    print("Starting demonstration...\n")

    # Run the async demo
    asyncio.run(run_real_web_scraper_demo())

    print("\n" + "=" * 80)
    print("  END OF DEMONSTRATION")
    print("=" * 80 + "\n")
