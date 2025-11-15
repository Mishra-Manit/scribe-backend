"""
Manual Test for Web Scraper Step - VERBOSE MODE

This is a manual test file (not pytest) for verifying the web_scraper step works correctly.
Run this file directly to test the web scraper with predetermined search terms.

Usage:
    python pipeline/steps/web_scraper/tests/manual_test_web_scraper.py

This will:
- Create a fake PipelineData object with 3 predetermined search terms
- Execute the WebScraperStep
- Log EVERYTHING verbosely to both console and Logfire
- Display detailed results

NOTE: Requires valid Google API credentials in .env file
"""

import asyncio
import sys
import json
from datetime import datetime
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure logging BEFORE any other imports
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Import logfire and configure
import logfire

# Import pipeline components
from pipeline.steps.web_scraper.main import WebScraperStep
from pipeline.models.core import PipelineData, TemplateType


def print_section_header(title: str):
    """Print a formatted section header for verbose output"""
    border = "=" * 80
    print(f"\n{border}")
    print(f"  {title}")
    print(f"{border}\n")


def print_subsection(title: str):
    """Print a formatted subsection header"""
    print(f"\n--- {title} ---")


def print_json(obj, indent=2):
    """Pretty print a JSON-serializable object"""
    print(json.dumps(obj, indent=indent, default=str))


def create_test_pipeline_data() -> PipelineData:
    """
    Create a fake PipelineData object with predetermined values.

    This simulates the output from Step 1 (TemplateParser).
    """
    print_section_header("CREATING TEST PIPELINE DATA")

    logger.info("Initializing fake PipelineData object")

    # Define 3 predetermined search terms
    search_terms = [
        "Dr. Andrew Ng machine learning Stanford",
        "Andrew Ng deep learning research",
        "Stanford AI research publications"
    ]

    logger.info(f"Created {len(search_terms)} search terms")
    print_subsection("Search Terms")
    for i, term in enumerate(search_terms, 1):
        print(f"  {i}. {term}")

    # Create PipelineData
    pipeline_data = PipelineData(
        # Required input fields
        task_id="test-task-12345",
        user_id="test-user-67890",
        email_template=(
            "Dear {{name}},\n\n"
            "I am reaching out regarding your research in {{research_area}}. "
            "I noticed your work on {{specific_topic}} and found it fascinating.\n\n"
            "Best regards"
        ),
        recipient_name="Dr. Andrew Ng",
        recipient_interest="machine learning and deep learning",

        # Step 1 outputs (simulating TemplateParser results)
        search_terms=search_terms,
        template_type=TemplateType.RESEARCH,
        template_analysis={
            "placeholders": ["name", "research_area", "specific_topic"],
            "requires_publications": True,
            "tone": "professional",
            "word_count_estimate": 150
        }
    )

    print_subsection("PipelineData Fields")
    print(f"  task_id: {pipeline_data.task_id}")
    print(f"  user_id: {pipeline_data.user_id}")
    print(f"  recipient_name: {pipeline_data.recipient_name}")
    print(f"  recipient_interest: {pipeline_data.recipient_interest}")
    print(f"  template_type: {pipeline_data.template_type}")
    print(f"  search_terms count: {len(pipeline_data.search_terms)}")

    print_subsection("Template Analysis")
    print_json(pipeline_data.template_analysis)

    logger.info("PipelineData object created successfully")

    return pipeline_data


async def run_web_scraper_test():
    """
    Main test function - runs the web scraper step with verbose logging.
    """
    print_section_header("WEB SCRAPER MANUAL TEST - STARTING")

    with logfire.span("manual_test_web_scraper", test_type="manual", verbose=True):

        # Step 1: Create test data
        logger.info("=" * 50)
        logger.info("STEP 1: Creating test data")
        logger.info("=" * 50)

        pipeline_data = create_test_pipeline_data()

        # Step 2: Initialize WebScraperStep
        print_section_header("INITIALIZING WEB SCRAPER STEP")

        logger.info("Creating WebScraperStep instance")

        with logfire.span("initialize_web_scraper"):
            try:
                scraper = WebScraperStep()
                logger.info("WebScraperStep initialized successfully")

                print_subsection("Configuration")
                print(f"  Step name: {scraper.step_name}")
                print(f"  Results per query: {scraper.results_per_query}")
                print(f"  Max pages to scrape: {scraper.max_pages_to_scrape}")
                print(f"  Scrape timeout: {scraper.scrape_timeout}s")
                print(f"  Max concurrent scrapes: {scraper.max_concurrent_scrapes}")

            except Exception as e:
                logger.error(f"Failed to initialize WebScraperStep: {e}", exc_info=True)
                print(f"\n❌ ERROR: {e}\n")
                return

        # Step 3: Validate input
        print_section_header("VALIDATING INPUT DATA")

        logger.info("Running input validation")

        with logfire.span("validate_input"):
            validation_error = await scraper._validate_input(pipeline_data)

            if validation_error:
                logger.error(f"Validation failed: {validation_error}")
                print(f"\n❌ VALIDATION ERROR: {validation_error}\n")
                return
            else:
                logger.info("✓ Input validation passed")
                print("  ✓ All required fields present")
                print("  ✓ Search terms not empty")
                print("  ✓ Template type is set")
                print("  ✓ Recipient information present")

        # Step 4: Execute the web scraper
        print_section_header("EXECUTING WEB SCRAPER STEP")

        logger.info("=" * 50)
        logger.info("STEP 2: Beginning web scraper execution")
        logger.info("=" * 50)

        start_time = datetime.now()
        logger.info(f"Start time: {start_time.isoformat()}")

        with logfire.span(
            "execute_web_scraper",
            search_terms_count=len(pipeline_data.search_terms),
            recipient=pipeline_data.recipient_name
        ):
            try:
                print("\n🔍 Starting web scraper execution...")
                print("   This may take 30-60 seconds depending on search results\n")

                # Execute the step
                result = await scraper.execute(pipeline_data)

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.info(f"Execution completed in {duration:.2f} seconds")

                # Step 5: Display results
                print_section_header("EXECUTION RESULTS")

                print_subsection("Step Result")
                print(f"  Success: {result.success}")
                print(f"  Step name: {result.step_name}")
                print(f"  Duration: {duration:.2f} seconds")

                if result.error:
                    print(f"  ❌ Error: {result.error}")
                    logger.error(f"Step failed with error: {result.error}")
                else:
                    print("  ✓ No errors")

                if result.warnings:
                    print(f"\n  ⚠️  Warnings ({len(result.warnings)}):")
                    for warning in result.warnings:
                        print(f"    - {warning}")
                        logger.warning(warning)
                else:
                    print("  ✓ No warnings")

                if result.metadata:
                    print_subsection("Result Metadata")
                    print_json(result.metadata)

                # Step 6: Display updated PipelineData
                print_section_header("UPDATED PIPELINE DATA")

                print_subsection("Scraped Content")
                print(f"  Content length: {len(pipeline_data.scraped_content)} characters")
                print(f"  Content preview (first 500 chars):")
                print("  " + "-" * 76)
                if pipeline_data.scraped_content:
                    preview = pipeline_data.scraped_content[:500]
                    for line in preview.split('\n'):
                        print(f"  {line}")
                    if len(pipeline_data.scraped_content) > 500:
                        print(f"  ... ({len(pipeline_data.scraped_content) - 500} more characters)")
                else:
                    print("  (empty)")
                print("  " + "-" * 76)

                print_subsection("Scraped URLs")
                print(f"  Total URLs scraped: {len(pipeline_data.scraped_urls)}")
                for i, url in enumerate(pipeline_data.scraped_urls, 1):
                    print(f"  {i}. {url}")

                print_subsection("Scraping Metadata")
                if pipeline_data.scraping_metadata:
                    print_json(pipeline_data.scraping_metadata)
                else:
                    print("  (none)")

                # Step 7: Log comprehensive summary
                print_section_header("TEST SUMMARY")

                logfire.info(
                    "Web scraper test completed",
                    success=result.success,
                    duration_seconds=duration,
                    search_terms_count=len(pipeline_data.search_terms),
                    urls_scraped=len(pipeline_data.scraped_urls),
                    content_length=len(pipeline_data.scraped_content),
                    has_warnings=len(result.warnings) > 0,
                    metadata=pipeline_data.scraping_metadata
                )

                print(f"  Test Status: {'✓ PASSED' if result.success else '✗ FAILED'}")
                print(f"  Execution Time: {duration:.2f} seconds")
                print(f"  Search Terms: {len(pipeline_data.search_terms)}")
                print(f"  URLs Scraped: {len(pipeline_data.scraped_urls)}")
                print(f"  Content Length: {len(pipeline_data.scraped_content)} chars")

                if pipeline_data.scraping_metadata:
                    success_rate = pipeline_data.scraping_metadata.get('success_rate', 0)
                    print(f"  Success Rate: {success_rate:.1%}")

                print()

                if result.success:
                    logger.info("🎉 TEST PASSED - Web scraper executed successfully")
                    print("🎉 TEST PASSED - Web scraper executed successfully\n")
                else:
                    logger.error("❌ TEST FAILED - See errors above")
                    print("❌ TEST FAILED - See errors above\n")

            except Exception as e:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.error(f"Unexpected error during execution: {e}", exc_info=True)

                print_section_header("EXECUTION FAILED")
                print(f"  ❌ Error Type: {type(e).__name__}")
                print(f"  ❌ Error Message: {str(e)}")
                print(f"  Duration before failure: {duration:.2f} seconds")
                print()

                # Log to logfire
                logfire.error(
                    "Web scraper test failed with exception",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    duration_seconds=duration
                )

                raise


def main():
    """Entry point for manual test"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  WEB SCRAPER MANUAL TEST - VERBOSE MODE".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    logger.info("Starting manual test execution")
    logfire.info("Manual test script started", script_name=__file__)

    try:
        # Run the async test
        asyncio.run(run_web_scraper_test())

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user (Ctrl+C)\n")
        logger.warning("Test interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n💥 FATAL ERROR: {e}\n")
        logger.critical(f"Fatal error in test execution: {e}", exc_info=True)
        sys.exit(1)

    finally:
        print_section_header("TEST COMPLETE")
        logger.info("Manual test execution finished")
        logfire.info("Manual test script finished")


if __name__ == "__main__":
    main()
