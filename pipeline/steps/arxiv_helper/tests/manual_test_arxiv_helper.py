"""
Manual Test for ArXiv Helper Step - VERBOSE MODE

This is a manual test file (not pytest) for verifying the arxiv_helper step works correctly.
Run this file directly to test the ArXiv helper with predetermined data.

Usage:
    python pipeline/steps/arxiv_helper/tests/manual_test_arxiv_helper.py

This will:
- Create a fake PipelineData object simulating Steps 1 and 2 output
- Execute the ArxivHelperStep with REAL ArXiv API calls
- Test both RESEARCH template (runs ArXiv search) and non-RESEARCH (skips)
- Log EVERYTHING verbosely to both console and Logfire
- Display detailed results

NOTE: Requires internet connection for ArXiv API access
"""

import asyncio
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

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

# Import logfire
import logfire

# Import pipeline components and config
from config.settings import settings
from observability.logfire_config import LogfireConfig
from pipeline.steps.arxiv_helper.main import ArxivHelperStep
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


def create_research_pipeline_data() -> PipelineData:
    """
    Create a fake PipelineData object for RESEARCH template type.

    This simulates the output from Steps 1 (TemplateParser) and 2 (WebScraper).
    """
    print_section_header("CREATING TEST PIPELINE DATA - RESEARCH TEMPLATE")

    logger.info("Initializing fake PipelineData object for RESEARCH template")

    # Simulate Step 1 outputs (TemplateParser)
    search_terms = [
        "Dr. Geoffrey Hinton deep learning",
        "Geoffrey Hinton University of Toronto",
        "Geoffrey Hinton neural networks research"
    ]

    # Simulate Step 2 outputs (WebScraper)
    scraped_content = """
Geoffrey Hinton is a University Professor Emeritus at the University of Toronto
and Chief Scientific Adviser at the Vector Institute. His research focuses on
deep learning, neural networks, and artificial intelligence.

He is widely recognized as one of the "Godfathers of AI" for his pioneering work
on backpropagation, Boltzmann machines, and capsule networks. His contributions
have fundamentally shaped modern deep learning.

Recent work includes research on variational autoencoders, unsupervised learning
methods, and the Forward-Forward algorithm as an alternative to backpropagation.
His team has published extensively in top ML conferences including NeurIPS, ICML,
and ICLR.

Hinton was awarded the Turing Award in 2018 (along with Yoshua Bengio and Yann LeCun)
for conceptual and engineering breakthroughs that have made deep neural networks a
critical component of computing.
    """.strip()

    scraped_urls = [
        "https://www.cs.toronto.edu/~hinton/",
        "https://vectorinstitute.ai/team/geoffrey-hinton/",
        "https://en.wikipedia.org/wiki/Geoffrey_Hinton"
    ]

    scraping_metadata = {
        "total_attempts": 5,
        "successful_scrapes": 3,
        "failed_urls": ["https://example1.com", "https://example2.com"],
        "success_rate": 0.6,
        "total_content_length": 12000,
        "final_content_length": len(scraped_content),
        "was_summarized": True,
        "has_uncertainty_markers": False
    }

    # Create PipelineData
    pipeline_data = PipelineData(
        # Required input fields
        task_id=f"test-task-{uuid4().hex[:8]}",
        user_id=f"test-user-{uuid4().hex[:8]}",
        email_template=(
            "Dear {{name}},\n\n"
            "I am writing to express my interest in your research on {{research_area}}. "
            "I have read several of your papers on {{specific_topic}} and found them inspiring.\n\n"
            "I would love to discuss potential research opportunities.\n\n"
            "Best regards"
        ),
        recipient_name="Geoffrey Hinton",
        recipient_interest="deep learning and neural networks",

        # Step 1 outputs (TemplateParser)
        search_terms=search_terms,
        template_type=TemplateType.RESEARCH,
        template_analysis={
            "placeholders": ["name", "research_area", "specific_topic"],
            "requires_publications": True,
            "tone": "professional",
            "word_count_estimate": 150
        },

        # Step 2 outputs (WebScraper)
        scraped_content=scraped_content,
        scraped_urls=scraped_urls,
        scraped_page_contents={
            url: f"Full page content for {url}..." for url in scraped_urls
        },
        scraping_metadata=scraping_metadata
    )

    # Display data summary
    print_subsection("PipelineData Fields")
    print(f"  task_id: {pipeline_data.task_id}")
    print(f"  user_id: {pipeline_data.user_id}")
    print(f"  recipient_name: {pipeline_data.recipient_name}")
    print(f"  recipient_interest: {pipeline_data.recipient_interest}")
    print(f"  template_type: {pipeline_data.template_type.value}")

    print_subsection("Step 1 Output (TemplateParser)")
    print(f"  search_terms count: {len(pipeline_data.search_terms)}")
    for i, term in enumerate(pipeline_data.search_terms, 1):
        print(f"    {i}. {term}")
    print(f"  template_analysis: {pipeline_data.template_analysis}")

    print_subsection("Step 2 Output (WebScraper)")
    print(f"  scraped_content length: {len(pipeline_data.scraped_content)} chars")
    print(f"  scraped_urls count: {len(pipeline_data.scraped_urls)}")
    for i, url in enumerate(pipeline_data.scraped_urls, 1):
        print(f"    {i}. {url}")
    print(f"  scraping_metadata:")
    print_json(pipeline_data.scraping_metadata, indent=4)

    logger.info("PipelineData object created successfully for RESEARCH template")

    return pipeline_data


def create_general_pipeline_data() -> PipelineData:
    """
    Create a fake PipelineData object for GENERAL template type.

    ArXiv search should be SKIPPED for non-RESEARCH templates.
    """
    print_section_header("CREATING TEST PIPELINE DATA - GENERAL TEMPLATE")

    logger.info("Initializing fake PipelineData object for GENERAL template")

    # Simulate Step 1 outputs (TemplateParser)
    search_terms = [
        "Dr. Jane Smith computer science",
        "Jane Smith MIT professor"
    ]

    # Simulate Step 2 outputs (WebScraper)
    scraped_content = """
Dr. Jane Smith is a Professor of Computer Science at MIT. Her research interests
include distributed systems, cloud computing, and software engineering.

She has been teaching at MIT for over 15 years and has received multiple teaching
awards. Dr. Smith is known for her engaging lectures and mentorship of graduate students.
    """.strip()

    # Create PipelineData
    pipeline_data = PipelineData(
        task_id=f"test-task-{uuid4().hex[:8]}",
        user_id=f"test-user-{uuid4().hex[:8]}",
        email_template="Dear {{name}},\n\nI am interested in learning more about {{topic}}.\n\nBest,",
        recipient_name="Dr. Jane Smith",
        recipient_interest="distributed systems",

        # Step 1 outputs
        search_terms=search_terms,
        template_type=TemplateType.GENERAL,  # NOT RESEARCH
        template_analysis={
            "placeholders": ["name", "topic"],
            "requires_publications": False,
            "tone": "professional"
        },

        # Step 2 outputs
        scraped_content=scraped_content,
        scraped_urls=["https://www.mit.edu/~jsmith/"],
        scraped_page_contents={
            "https://www.mit.edu/~jsmith/": "Full page content..."
        },
        scraping_metadata={
            "total_attempts": 1,
            "successful_scrapes": 1,
            "success_rate": 1.0
        }
    )

    print_subsection("PipelineData Fields")
    print(f"  recipient_name: {pipeline_data.recipient_name}")
    print(f"  template_type: {pipeline_data.template_type.value} (ArXiv SKIP expected)")

    logger.info("PipelineData object created successfully for GENERAL template")

    return pipeline_data


async def run_arxiv_test():
    """
    Main test function - runs the ArXiv helper step with verbose logging.

    Tests both scenarios:
    1. RESEARCH template - should fetch papers from ArXiv
    2. GENERAL template - should skip ArXiv search
    """
    print_section_header("ARXIV HELPER MANUAL TEST - STARTING")

    with logfire.span("manual_test_arxiv_helper", test_type="manual", verbose=True):

        # ===================================================================
        # TEST 1: RESEARCH TEMPLATE (Should run ArXiv search)
        # ===================================================================

        print_section_header("TEST 1: RESEARCH TEMPLATE TYPE")
        logger.info("=" * 50)
        logger.info("TEST 1: Running with RESEARCH template")
        logger.info("=" * 50)

        # Step 1: Create test data
        pipeline_data_research = create_research_pipeline_data()

        # Step 2: Initialize ArxivHelperStep
        print_section_header("INITIALIZING ARXIV HELPER STEP")

        logger.info("Creating ArxivHelperStep instance")

        with logfire.span("initialize_arxiv_helper"):
            try:
                arxiv_helper = ArxivHelperStep()
                logger.info("ArxivHelperStep initialized successfully")

                print_subsection("Configuration")
                print(f"  Step name: {arxiv_helper.step_name}")
                print(f"  Max papers to fetch: {arxiv_helper.max_papers_to_fetch}")
                print(f"  Top N papers: {arxiv_helper.top_n_papers}")

            except Exception as e:
                logger.error(f"Failed to initialize ArxivHelperStep: {e}", exc_info=True)
                print(f"\n❌ ERROR: {e}\n")
                return

        # Step 3: Validate input
        print_section_header("VALIDATING INPUT DATA")

        logger.info("Running input validation")

        with logfire.span("validate_input"):
            validation_error = await arxiv_helper._validate_input(pipeline_data_research)

            if validation_error:
                logger.error(f"Validation failed: {validation_error}")
                print(f"\n❌ VALIDATION ERROR: {validation_error}\n")
                return
            else:
                logger.info("✓ Input validation passed")
                print("  ✓ template_type is set")
                print("  ✓ recipient_name is present")
                print("  ✓ recipient_interest is present")

        # Step 4: Execute the ArXiv helper
        print_section_header("EXECUTING ARXIV HELPER STEP (RESEARCH)")

        logger.info("=" * 50)
        logger.info("STEP 2: Beginning ArXiv helper execution")
        logger.info("=" * 50)

        start_time = datetime.now()
        logger.info(f"Start time: {start_time.isoformat()}")

        with logfire.span(
            "execute_arxiv_helper_research",
            template_type=pipeline_data_research.template_type.value,
            recipient=pipeline_data_research.recipient_name
        ):
            try:
                print("\n📚 Starting ArXiv search...")
                print(f"   Searching for papers by: {pipeline_data_research.recipient_name}")
                print(f"   Interest area: {pipeline_data_research.recipient_interest}")
                print("   This may take 5-15 seconds depending on API response\n")

                # Execute the step
                result = await arxiv_helper.execute(pipeline_data_research)

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.info(f"Execution completed in {duration:.2f} seconds")

                # Step 5: Display results
                print_section_header("EXECUTION RESULTS (RESEARCH)")

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
                print_section_header("UPDATED PIPELINE DATA (RESEARCH)")

                print_subsection("ArXiv Papers Found")
                print(f"  Total papers: {len(pipeline_data_research.arxiv_papers)}")

                if pipeline_data_research.arxiv_papers:
                    for i, paper in enumerate(pipeline_data_research.arxiv_papers, 1):
                        print(f"\n  Paper {i}:")
                        print(f"    Title: {paper['title']}")
                        print(f"    Authors: {', '.join(paper['authors'][:3])}")
                        if len(paper['authors']) > 3:
                            print(f"             ... and {len(paper['authors']) - 3} more")
                        print(f"    Year: {paper['year']}")
                        print(f"    Relevance Score: {paper['relevance_score']:.3f}")
                        print(f"    URL: {paper['url']}")
                        print(f"    Abstract (truncated): {paper['abstract'][:150]}...")
                else:
                    print("  (no papers found)")

                print_subsection("Enrichment Metadata")
                if pipeline_data_research.enrichment_metadata:
                    print_json(pipeline_data_research.enrichment_metadata)
                else:
                    print("  (none)")

                # Log comprehensive summary
                logfire.info(
                    "ArXiv helper test 1 completed (RESEARCH)",
                    success=result.success,
                    duration_seconds=duration,
                    papers_found=len(pipeline_data_research.arxiv_papers),
                    has_warnings=len(result.warnings) > 0,
                    metadata=pipeline_data_research.enrichment_metadata
                )

                print_section_header("TEST 1 SUMMARY")
                print(f"  Test Status: {'✓ PASSED' if result.success else '✗ FAILED'}")
                print(f"  Execution Time: {duration:.2f} seconds")
                print(f"  Template Type: {pipeline_data_research.template_type.value}")
                print(f"  Papers Found: {len(pipeline_data_research.arxiv_papers)}")

                if pipeline_data_research.enrichment_metadata.get('avg_relevance_score'):
                    avg_score = pipeline_data_research.enrichment_metadata['avg_relevance_score']
                    print(f"  Avg Relevance Score: {avg_score:.3f}")

                print()

                if result.success:
                    logger.info("🎉 TEST 1 PASSED - ArXiv helper executed successfully")
                    print("🎉 TEST 1 PASSED - ArXiv helper executed successfully\n")
                else:
                    logger.error("❌ TEST 1 FAILED - See errors above")
                    print("❌ TEST 1 FAILED - See errors above\n")

            except Exception as e:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.error(f"Unexpected error during execution: {e}", exc_info=True)

                print_section_header("EXECUTION FAILED (RESEARCH)")
                print(f"  ❌ Error Type: {type(e).__name__}")
                print(f"  ❌ Error Message: {str(e)}")
                print(f"  Duration before failure: {duration:.2f} seconds")
                print()

                logfire.error(
                    "ArXiv helper test 1 failed with exception",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    duration_seconds=duration
                )

        # ===================================================================
        # TEST 2: GENERAL TEMPLATE (Should skip ArXiv search)
        # ===================================================================

        print("\n\n")
        print_section_header("TEST 2: GENERAL TEMPLATE TYPE (SKIP TEST)")
        logger.info("=" * 50)
        logger.info("TEST 2: Running with GENERAL template (should skip)")
        logger.info("=" * 50)

        # Step 1: Create test data
        pipeline_data_general = create_general_pipeline_data()

        # Step 2: Execute the ArXiv helper
        print_section_header("EXECUTING ARXIV HELPER STEP (GENERAL)")

        start_time = datetime.now()
        logger.info(f"Start time: {start_time.isoformat()}")

        with logfire.span(
            "execute_arxiv_helper_general",
            template_type=pipeline_data_general.template_type.value,
            recipient=pipeline_data_general.recipient_name
        ):
            try:
                print("\n📚 Starting ArXiv helper...")
                print(f"   Template type: {pipeline_data_general.template_type.value}")
                print("   Expected: SKIP ArXiv search (not RESEARCH template)\n")

                # Execute the step
                result = await arxiv_helper.execute(pipeline_data_general)

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.info(f"Execution completed in {duration:.2f} seconds")

                # Display results
                print_section_header("EXECUTION RESULTS (GENERAL)")

                print_subsection("Step Result")
                print(f"  Success: {result.success}")
                print(f"  Step name: {result.step_name}")
                print(f"  Duration: {duration:.2f} seconds")
                print(f"  Skipped: {result.metadata.get('skipped', False)}")

                if result.metadata:
                    print_subsection("Result Metadata")
                    print_json(result.metadata)

                print_subsection("Updated PipelineData")
                print(f"  ArXiv papers: {len(pipeline_data_general.arxiv_papers)} (should be 0)")
                print(f"  Enrichment metadata:")
                print_json(pipeline_data_general.enrichment_metadata)

                # Verify skip behavior
                was_skipped = result.metadata.get('skipped', False)
                papers_empty = len(pipeline_data_general.arxiv_papers) == 0

                print_section_header("TEST 2 SUMMARY")
                print(f"  Test Status: {'✓ PASSED' if (result.success and was_skipped and papers_empty) else '✗ FAILED'}")
                print(f"  Execution Time: {duration:.2f} seconds")
                print(f"  Template Type: {pipeline_data_general.template_type.value}")
                print(f"  ArXiv Search Skipped: {was_skipped}")
                print(f"  Papers Found: {len(pipeline_data_general.arxiv_papers)} (expected 0)")
                print()

                if result.success and was_skipped and papers_empty:
                    logger.info("🎉 TEST 2 PASSED - ArXiv correctly skipped for GENERAL template")
                    print("🎉 TEST 2 PASSED - ArXiv correctly skipped for GENERAL template\n")
                else:
                    logger.error("❌ TEST 2 FAILED - Skip behavior incorrect")
                    print("❌ TEST 2 FAILED - Skip behavior incorrect\n")

                logfire.info(
                    "ArXiv helper test 2 completed (GENERAL)",
                    success=result.success,
                    duration_seconds=duration,
                    was_skipped=was_skipped,
                    papers_found=len(pipeline_data_general.arxiv_papers)
                )

            except Exception as e:
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.error(f"Unexpected error during execution: {e}", exc_info=True)

                print_section_header("EXECUTION FAILED (GENERAL)")
                print(f"  ❌ Error Type: {type(e).__name__}")
                print(f"  ❌ Error Message: {str(e)}")
                print(f"  Duration before failure: {duration:.2f} seconds")
                print()

                logfire.error(
                    "ArXiv helper test 2 failed with exception",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    duration_seconds=duration
                )


def main():
    """Entry point for manual test"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  ARXIV HELPER MANUAL TEST - VERBOSE MODE".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # Initialize Logfire for observability (optional but recommended)
    if settings.logfire_token:
        LogfireConfig.initialize(token=settings.logfire_token)
        print("✓ Logfire observability enabled - spans will be sent to remote server\n")
    else:
        # Suppress warnings if no token is available
        os.environ['LOGFIRE_IGNORE_NO_CONFIG'] = '1'
        print("⚠ Logfire token not set - observability disabled (no remote logging)\n")

    logger.info("Starting manual test execution")
    logfire.info("Manual test script started", script_name=__file__)

    try:
        # Run the async test
        asyncio.run(run_arxiv_test())

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
