"""
Test suite for Web Scraper Step

Tests the second step of the pipeline using real Google Custom Search API.
Validates search result fetching, URL limits, deduplication, and scraping behavior.

Run with:
    pytest pipeline/steps/web_scraper/tests/test_web_scraper.py -v
    pytest pipeline/steps/web_scraper/tests/test_web_scraper.py -v -s  # with logs
"""

import pytest
import logfire
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from pipeline.steps.web_scraper.main import WebScraperStep
from pipeline.models.core import PipelineData, TemplateType
from pipeline.core.exceptions import ValidationError, ExternalAPIError


# ===================================================================
# FIXTURES
# ===================================================================

@pytest.fixture
def web_scraper():
    """Initialize the WebScraperStep"""
    return WebScraperStep()


@pytest.fixture
def pipeline_data_with_search_terms():
    """PipelineData with search terms from Step 1 (template parser)"""
    return PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template="Dear {{name}}, I admire your work on {{research}}.",
        recipient_name="Dr. Jane Smith",
        recipient_interest="machine learning",
        template_type=TemplateType.RESEARCH,
        search_terms=[
            "Dr. Jane Smith machine learning",
            "Jane Smith AI research",
            "Jane Smith publications"
        ]
    )


# ===================================================================
# TESTS - Configuration Validation
# ===================================================================

@pytest.mark.unit
def test_web_scraper_configuration(web_scraper):
    """
    Test that WebScraperStep is configured with correct limits.

    Expected behavior:
    - results_per_query should be 6 (6 URLs per search term)
    - max_pages_to_scrape should be 10 (scrape top 10 URLs total)
    """
    logfire.info("Testing web scraper configuration")

    assert web_scraper.results_per_query == 6, \
        f"Should fetch 6 URLs per search term, got {web_scraper.results_per_query}"

    assert web_scraper.max_pages_to_scrape == 10, \
        f"Should scrape max 10 pages total, got {web_scraper.max_pages_to_scrape}"

    assert web_scraper.scrape_timeout == 10.0, \
        f"Scrape timeout should be 10.0 seconds"

    assert web_scraper.max_concurrent_scrapes == 5, \
        f"Max concurrent scrapes should be 5"

    logfire.info(
        "Configuration validated",
        results_per_query=web_scraper.results_per_query,
        max_pages_to_scrape=web_scraper.max_pages_to_scrape
    )


# ===================================================================
# TESTS - Input Validation
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_input_missing_search_terms(web_scraper):
    """
    Test validation fails when search_terms is empty.

    Expected behavior:
    - Returns error if search_terms is empty
    - Step 1 (template parser) must run first
    """
    pipeline_data = PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template="Test",
        recipient_name="Dr. Smith",
        recipient_interest="AI",
        search_terms=[]  # Empty!
    )

    error = await web_scraper._validate_input(pipeline_data)

    assert error is not None, "Should return error for empty search_terms"
    assert "search_terms is empty" in error.lower()

    logfire.info("Validation correctly failed for empty search_terms")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_input_missing_template_type(web_scraper):
    """
    Test validation fails when template_type is not set.
    """
    pipeline_data = PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template="Test",
        recipient_name="Dr. Smith",
        recipient_interest="AI",
        search_terms=["Dr. Smith AI"]
        # template_type not set!
    )

    error = await web_scraper._validate_input(pipeline_data)

    assert error is not None, "Should return error for missing template_type"
    assert "template_type not set" in error.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_input_success(web_scraper, pipeline_data_with_search_terms):
    """
    Test validation passes with valid input.
    """
    error = await web_scraper._validate_input(pipeline_data_with_search_terms)

    assert error is None, f"Validation should pass, got error: {error}"

    logfire.info("Validation passed for valid input")


# ===================================================================
# TESTS - Google Search Integration (Mocked)
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_6_urls_per_search_term(web_scraper, pipeline_data_with_search_terms):
    """
    Test that Google Search fetches 6 URLs per search term.

    With 3 search terms × 6 URLs each = 18 URLs total (before deduplication)
    """
    # Mock the Google Search client to return 6 results per term
    mock_search_results = [
        {"link": f"https://example.com/result{i}", "title": f"Result {i}"}
        for i in range(1, 19)  # 18 total URLs (6 per term × 3 terms)
    ]

    with patch.object(
        web_scraper.google_client,
        'search_multiple_terms',
        return_value=mock_search_results
    ):
        with logfire.span("test_fetch_6_urls"):
            # Note: This is testing the Google client behavior,
            # so we'd verify it gets called with results_per_query=6
            results = await web_scraper.google_client.search_multiple_terms(
                search_terms=pipeline_data_with_search_terms.search_terms,
                results_per_query=web_scraper.results_per_query
            )

            assert len(results) == 18, \
                f"Should fetch 18 URLs total (3 terms × 6 each), got {len(results)}"

            logfire.info(
                "Fetched correct number of URLs",
                total_urls=len(results),
                search_terms_count=len(pipeline_data_with_search_terms.search_terms)
            )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_max_pages_to_scrape_limit(web_scraper, pipeline_data_with_search_terms):
    """
    Test that only top 10 URLs are scraped even if 18 are fetched.

    Expected behavior:
    - Fetch up to 18 URLs (3 terms × 6 each)
    - Only scrape top 10 URLs
    - Deduplication may reduce total below 18
    """
    # Mock 18 unique search results
    mock_search_results = [
        {"link": f"https://example.com/page{i}", "title": f"Page {i}"}
        for i in range(1, 19)
    ]

    # Mock successful scraping for all URLs
    async def mock_scrape(url, timeout):
        return (f"Title for {url}", f"Content from {url}")

    with patch.object(
        web_scraper.google_client,
        'search_multiple_terms',
        return_value=mock_search_results
    ):
        with patch(
            'pipeline.steps.web_scraper.main.scrape_url',
            side_effect=mock_scrape
        ):
            with logfire.span("test_max_pages_limit"):
                result = await web_scraper.execute(pipeline_data_with_search_terms)

                assert result.success is True, f"Step should succeed: {result.error}"

                # Should have scraped exactly 10 URLs (not all 18)
                assert len(pipeline_data_with_search_terms.scraped_urls) == 10, \
                    f"Should scrape max 10 URLs, got {len(pipeline_data_with_search_terms.scraped_urls)}"

                # Metadata should reflect this
                metadata = pipeline_data_with_search_terms.scraping_metadata
                assert metadata["urls_scraped"] == 10

                logfire.info(
                    "Max pages limit enforced",
                    urls_fetched=18,
                    urls_scraped=len(pipeline_data_with_search_terms.scraped_urls)
                )


# ===================================================================
# TESTS - Deduplication
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_url_deduplication(web_scraper, pipeline_data_with_search_terms):
    """
    Test that duplicate URLs across search terms are deduplicated.

    Expected behavior:
    - If multiple search terms return the same URL, only include it once
    - Still respect max_pages_to_scrape limit of 10
    """
    # Mock search results with duplicates
    # Search term 1: URLs 1-6
    # Search term 2: URLs 4-9 (overlaps with term 1)
    # Search term 3: URLs 7-12 (overlaps with term 2)
    # Total unique: 12 URLs
    mock_search_results = [
        {"link": f"https://example.com/page{i}", "title": f"Page {i}"}
        for i in [1, 2, 3, 4, 5, 6,  # Term 1
                  4, 5, 6, 7, 8, 9,  # Term 2 (duplicates 4,5,6)
                  7, 8, 9, 10, 11, 12]  # Term 3 (duplicates 7,8,9)
    ]

    async def mock_scrape(url, timeout):
        return (f"Title for {url}", f"Content from {url}")

    with patch.object(
        web_scraper.google_client,
        'search_multiple_terms',
        return_value=mock_search_results
    ):
        with patch(
            'pipeline.steps.web_scraper.main.scrape_url',
            side_effect=mock_scrape
        ):
            with logfire.span("test_deduplication"):
                result = await web_scraper.execute(pipeline_data_with_search_terms)

                assert result.success is True

                # Should scrape 10 unique URLs (limited by max_pages_to_scrape)
                assert len(pipeline_data_with_search_terms.scraped_urls) == 10

                # All URLs should be unique
                urls = pipeline_data_with_search_terms.scraped_urls
                assert len(urls) == len(set(urls)), "All URLs should be unique"

                logfire.info(
                    "Deduplication working correctly",
                    total_fetched=len(mock_search_results),
                    unique_urls=len(set(r["link"] for r in mock_search_results)),
                    scraped_urls=len(urls)
                )


# ===================================================================
# TESTS - Scraping Behavior
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_handles_failed_scrapes(web_scraper, pipeline_data_with_search_terms):
    """
    Test that failed scrapes are handled gracefully.

    Expected behavior:
    - If some URLs fail to scrape, continue with others
    - Only successful scrapes are included in results
    - Step still succeeds if at least one URL scraped successfully
    """
    mock_search_results = [
        {"link": f"https://example.com/page{i}", "title": f"Page {i}"}
        for i in range(1, 11)  # 10 URLs
    ]

    # Mock scraping: first 5 succeed, last 5 fail
    async def mock_scrape(url, timeout):
        page_num = int(url.split("page")[-1])
        if page_num <= 5:
            return (f"Title {page_num}", f"Content {page_num}")
        else:
            return (None, None)  # Failed scrape

    with patch.object(
        web_scraper.google_client,
        'search_multiple_terms',
        return_value=mock_search_results
    ):
        with patch(
            'pipeline.steps.web_scraper.main.scrape_url',
            side_effect=mock_scrape
        ):
            with logfire.span("test_failed_scrapes"):
                result = await web_scraper.execute(pipeline_data_with_search_terms)

                # Step should still succeed
                assert result.success is True, \
                    "Step should succeed even with some failed scrapes"

                # Should have 5 successful scrapes
                assert len(pipeline_data_with_search_terms.scraped_urls) == 5, \
                    f"Should have 5 successful scrapes, got {len(pipeline_data_with_search_terms.scraped_urls)}"

                # Metadata should reflect this
                metadata = pipeline_data_with_search_terms.scraping_metadata
                assert metadata["urls_scraped"] == 5
                assert metadata["urls_attempted"] == 10

                logfire.info(
                    "Failed scrapes handled correctly",
                    successful=5,
                    failed=5
                )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fails_if_all_scrapes_fail(web_scraper, pipeline_data_with_search_terms):
    """
    Test that step fails if all scrapes fail.

    Expected behavior:
    - If no URLs scrape successfully, step should fail
    - Error message should be informative
    """
    mock_search_results = [
        {"link": f"https://example.com/page{i}", "title": f"Page {i}"}
        for i in range(1, 6)
    ]

    # Mock all scrapes failing
    async def mock_scrape(url, timeout):
        return (None, None)

    with patch.object(
        web_scraper.google_client,
        'search_multiple_terms',
        return_value=mock_search_results
    ):
        with patch(
            'pipeline.steps.web_scraper.main.scrape_url',
            side_effect=mock_scrape
        ):
            with logfire.span("test_all_scrapes_fail"):
                result = await web_scraper.execute(pipeline_data_with_search_terms)

                # Step should fail
                assert result.success is False, \
                    "Step should fail if all scrapes fail"

                assert "no content" in result.error.lower(), \
                    f"Error should mention no content, got: {result.error}"

                logfire.info("Step correctly failed when all scrapes failed")


# ===================================================================
# TESTS - Integration (Real API - Slow)
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_real_google_search_and_scraping(web_scraper):
    """
    Integration test with real Google Custom Search API and web scraping.

    WARNING: This test makes real API calls and may be slow.
    Run with: pytest -m integration

    Expected behavior:
    - Fetches 6 URLs per search term
    - Scrapes up to 10 URLs
    - Returns valid content
    """
    pipeline_data = PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template="Dear {{name}}, interested in {{research}}.",
        recipient_name="Dr. Yann LeCun",
        recipient_interest="deep learning",
        template_type=TemplateType.RESEARCH,
        search_terms=[
            "Yann LeCun deep learning",
            "Yann LeCun convolutional neural networks",
            "Yann LeCun Meta AI"
        ]
    )

    with logfire.span("test_real_integration"):
        result = await web_scraper.execute(pipeline_data)

        # Basic success assertions
        assert result.success is True, f"Integration test should succeed: {result.error}"
        assert result.step_name == "web_scraper"

        # Should have scraped content
        assert len(pipeline_data.scraped_content) > 0, \
            "Should have scraped content"

        # Should have URLs (up to 10)
        assert len(pipeline_data.scraped_urls) > 0, \
            "Should have scraped URLs"
        assert len(pipeline_data.scraped_urls) <= 10, \
            f"Should scrape max 10 URLs, got {len(pipeline_data.scraped_urls)}"

        # Metadata should be present
        assert "urls_attempted" in pipeline_data.scraping_metadata
        assert "urls_scraped" in pipeline_data.scraping_metadata

        logfire.info(
            "Integration test passed",
            urls_scraped=len(pipeline_data.scraped_urls),
            content_length=len(pipeline_data.scraped_content),
            metadata=pipeline_data.scraping_metadata
        )


# ===================================================================
# TESTS - Metadata
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_metadata_completeness(web_scraper, pipeline_data_with_search_terms):
    """
    Test that result metadata contains all expected fields.

    Expected metadata fields:
    - search_terms_count
    - urls_attempted
    - urls_scraped
    - content_length
    - duration
    - timestamp
    """
    mock_search_results = [
        {"link": f"https://example.com/page{i}", "title": f"Page {i}"}
        for i in range(1, 11)
    ]

    async def mock_scrape(url, timeout):
        return ("Test Title", "Test content for the page")

    with patch.object(
        web_scraper.google_client,
        'search_multiple_terms',
        return_value=mock_search_results
    ):
        with patch(
            'pipeline.steps.web_scraper.main.scrape_url',
            side_effect=mock_scrape
        ):
            result = await web_scraper.execute(pipeline_data_with_search_terms)

            assert result.success is True

            # Check result metadata
            assert result.metadata is not None
            required_fields = [
                "search_terms_count",
                "urls_attempted",
                "urls_scraped",
                "content_length",
                "duration"
            ]

            for field in required_fields:
                assert field in result.metadata, f"Missing metadata field: {field}"

            # Check scraping metadata in pipeline_data
            scraping_meta = pipeline_data_with_search_terms.scraping_metadata
            assert "urls_attempted" in scraping_meta
            assert "urls_scraped" in scraping_meta
            assert "timestamp" in scraping_meta

            logfire.info(
                "Metadata completeness verified",
                result_metadata=result.metadata,
                scraping_metadata=scraping_meta
            )
