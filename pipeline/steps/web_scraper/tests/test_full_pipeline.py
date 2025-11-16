"""
Real-World Web Scraper Demonstration Script

This script demonstrates the web scraper pipeline using REAL data:
- Real Google Custom Search API calls
- Real Playwright web scraping of actual websites
- Real content extraction and summarization

Run this script directly:
    python pipeline/steps/web_scraper/tests/test_full_pipeline.py

Or from project root:
    python -m pipeline.steps.web_scraper.tests.test_full_pipeline
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
    Demonstrate the web scraper with real Google searches and real website scraping.

    This shows how the pipeline works in production with actual data.
    """

    print_section("🚀 REAL WEB SCRAPER DEMONSTRATION")

    # ============================================================================
    # STEP 1: Configure the search
    # ============================================================================

    print_subsection("Configuration")

    # Choose a well-known researcher for reliable results
    recipient_name = "Dr. Geoffrey Hinton"
    recipient_interest = "deep learning and neural networks"

    # Create realistic search queries
    search_terms = [
        "Geoffrey Hinton deep learning research",
        "Geoffrey Hinton University of Toronto",
        "Geoffrey Hinton neural networks research",
    ]

    print(f"Target Recipient: {recipient_name}")
    print(f"Research Interest: {recipient_interest}")
    print(f"Search Queries:")
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

    print(f"✓ Pipeline data created")
    print(f"  Task ID: {pipeline_data.task_id}")
    print(f"  Template Type: {pipeline_data.template_type.value}")

    # ============================================================================
    # STEP 3: Initialize web scraper
    # ============================================================================

    print_subsection("Initializing Web Scraper")

    scraper = WebScraperStep()

    print(f"✓ Web scraper initialized")
    print(f"  Results per query: {scraper.results_per_query}")
    print(f"  Max pages to scrape: {scraper.max_pages_to_scrape}")
    print(f"  Scrape timeout: {scraper.scrape_timeout}s")
    print(f"  Max concurrent scrapes: {scraper.max_concurrent_scrapes}")

    # ============================================================================
    # STEP 4: Execute the pipeline (REAL API CALLS!)
    # ============================================================================

    print_section("🌐 EXECUTING PIPELINE WITH REAL DATA")
    print("⏳ This will make real Google API calls and scrape real websites...")
    print("⏳ This may take 30-60 seconds depending on network speed...\n")

    start_time = datetime.now()

    # Execute with real Google Search and real Playwright scraping
    result = await scraper.execute(pipeline_data)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # ============================================================================
    # STEP 5: Display results
    # ============================================================================

    print_section("📊 RESULTS")

    print_subsection("Execution Summary")
    print(f"✓ Pipeline Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"✓ Total Duration: {duration:.2f} seconds")

    if not result.success:
        print(f"✗ Error: {result.error}")
        return

    # ============================================================================
    # STEP 6: Show scraping statistics
    # ============================================================================

    print_subsection("Scraping Statistics")

    metadata = pipeline_data.scraping_metadata

    print(f"Total URLs Attempted: {metadata.get('total_attempts', 0)}")
    print(f"Successful Scrapes: {metadata.get('successful_scrapes', 0)}")
    print(f"Failed URLs: {len(metadata.get('failed_urls', []))}")
    print(f"Success Rate: {metadata.get('success_rate', 0):.1%}")
    print(f"Total Content Length: {metadata.get('total_content_length', 0):,} chars")
    print(f"Final Summary Length: {metadata.get('final_content_length', 0):,} chars")
    print(f"Was Summarized: {metadata.get('was_summarized', False)}")
    print(f"Has Uncertainty Markers: {metadata.get('has_uncertainty_markers', False)}")

    # ============================================================================
    # STEP 7: Show scraped URLs
    # ============================================================================

    print_subsection("Successfully Scraped URLs")

    if pipeline_data.scraped_urls:
        for i, url in enumerate(pipeline_data.scraped_urls, 1):
            print(f"  {i}. {url}")
    else:
        print("  (No URLs scraped)")

    # ============================================================================
    # STEP 8: Show failed URLs (if any)
    # ============================================================================

    failed_urls = metadata.get('failed_urls', [])
    if failed_urls:
        print_subsection("Failed URLs")
        for i, url in enumerate(failed_urls, 1):
            print(f"  {i}. {url}")

    # ============================================================================
    # STEP 9: Show content preview
    # ============================================================================

    print_subsection("Scraped Content Preview (First 1000 characters)")

    if pipeline_data.scraped_content:
        preview = pipeline_data.scraped_content[:1000]
        print(f"\n{preview}")
        if len(pipeline_data.scraped_content) > 1000:
            print(f"\n... ({len(pipeline_data.scraped_content) - 1000:,} more characters)")
    else:
        print("  (No content scraped)")

    # ============================================================================
    # STEP 10: Validate content quality
    # ============================================================================

    print_subsection("Content Quality Checks")

    content_lower = pipeline_data.scraped_content.lower()

    # Check for relevant keywords
    keywords = ["hinton", "deep learning", "neural network", "machine learning", "toronto"]
    found_keywords = [kw for kw in keywords if kw in content_lower]

    print(f"Keywords Found: {', '.join(found_keywords) if found_keywords else 'None'}")
    print(f"Content Contains Relevant Info: {len(found_keywords) > 0}")
    print(f"Content Length Reasonable: {len(pipeline_data.scraped_content) < 5000}")
    print(f"Minimum URLs Scraped: {len(pipeline_data.scraped_urls) >= 2}")

    # ============================================================================
    # STEP 11: Show individual page samples
    # ============================================================================

    print_subsection("Individual Page Samples (First 3 pages)")

    for i, (url, content) in enumerate(list(pipeline_data.scraped_page_contents.items())[:3], 1):
        print(f"\nPage {i}: {url}")
        print(f"Length: {len(content):,} characters")
        print(f"Preview: {content[:200]}...")

    # ============================================================================
    # STEP 12: Batch Summaries
    # ============================================================================
    print_subsection("Batch-Level Summaries")

    if pipeline_data.scraped_page_contents:
        # Re-combine scraped page contents for batch processing
        combined_content = "\n".join(pipeline_data.scraped_page_contents.values())

        # Split content into chunks based on scraper configuration
        chunks = scraper._split_into_chunks(combined_content, scraper.chunk_size)
        total_batches = len(chunks)

        for idx, chunk in enumerate(chunks, start=1):
            batch_summary = await scraper._summarize_batch(
                batch_content=chunk,
                batch_number=idx,
                total_batches=total_batches,
                recipient_name=pipeline_data.recipient_name,
            )
            # Pretty print batch summary with clear delimiters
            print("\n" + "=" * 80)
            print(f"=== BATCH {idx}/{total_batches} SUMMARY ===")
            print("=" * 80 + "\n")
            print(batch_summary.strip() + "\n")
            print("=" * 80)
            print(f"=== END BATCH {idx} ===")
            print("=" * 80 + "\n")
    else:
        print("  (No scraped content available for batch summarization)")

    # ============================================================================
    # STEP 13: Final Summarization
    # ============================================================================
    print_subsection("Final LLM Summary")
    print(pipeline_data.scraped_content)

    # ============================================================================
    # Summary
    # ============================================================================

    print_section("✅ DEMONSTRATION COMPLETE")

    print(f"Total URLs Scraped: {len(pipeline_data.scraped_urls)}")
    print(f"Total Content Extracted: {metadata.get('total_content_length', 0):,} characters")
    print(f"Final Summarized Content: {len(pipeline_data.scraped_content):,} characters")
    print(f"Execution Time: {duration:.2f} seconds")
    print(f"\nThis demonstrates the full web scraper pipeline working with:")
    print(f"  ✓ Real Google Custom Search API")
    print(f"  ✓ Real Playwright web scraping")
    print(f"  ✓ Real website content")
    print(f"  ✓ Real LLM summarization")


# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("  WEB SCRAPER DEMONSTRATION - REAL DATA")
    print("  This script uses REAL Google searches and REAL website scraping")
    print("=" * 80)

    # Check for required environment variables using application settings
    required_vars = {
        "GOOGLE_API_KEY": settings.google_api_key,
        "GOOGLE_CSE_ID": settings.google_cse_id,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    }
    missing_vars = [var for var, value in required_vars.items() if not value]

    if missing_vars:
        print("\n❌ ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables in your .env file or environment.")
        exit(1)

    print("\n✓ All required environment variables are set")

    # Initialize Logfire for observability (optional but recommended)
    if settings.logfire_token:
        LogfireConfig.initialize(token=settings.logfire_token)
        print("✓ Logfire observability enabled - spans will be sent to remote server")
    else:
        # Suppress warnings if no token is available
        os.environ['LOGFIRE_IGNORE_NO_CONFIG'] = '1'
        print("⚠ Logfire token not set - observability disabled (no remote logging)")

    print("✓ Starting demonstration...\n")

    # Run the async demo
    asyncio.run(run_real_web_scraper_demo())

    print("\n" + "=" * 80)
    print("  END OF DEMONSTRATION")
    print("=" * 80 + "\n")
