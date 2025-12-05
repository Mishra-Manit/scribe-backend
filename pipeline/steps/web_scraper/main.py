"""Web scraper using Google Search and Playwright to extract professor information."""

import logfire
import asyncio
from typing import Optional, List
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError
from config.settings import settings
from utils.llm_agent import create_agent

from .models import ScrapedPage, ScrapingResult, Summary
from .google_search import GoogleSearchClient
from .utils import scrape_url
from .prompts import SUMMARIZATION_SYSTEM_PROMPT, create_summarization_prompt

class WebScraperStep(BasePipelineStep):
    """
    Scrape and summarize professor info via Google Search + Playwright.

    Sets: scraped_content, scraped_urls, scraping_metadata
    """

    def __init__(self):
        super().__init__(step_name="web_scraper")

        # Initialize clients
        self.google_client = GoogleSearchClient()

        # Create pydantic-ai agent for content summarization
        # Using Haiku 4.5 for fast, cost-effective fact extraction
        # Low temperature for factual, grounded output (anti-hallucination)
        self.summarization_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            output_type=Summary,
            system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2000,
            retries=2,
            timeout=60.0
        )

        self.results_per_query = 2
        self.max_pages_to_scrape = 5
        self.scrape_timeout = 10.0
        self.max_concurrent_scrapes = 1 # Lowered to stop server crashes

        # Page-based summarization configuration
        self.chunk_size = 10000  # Single page chunk size for direct summarization
        self.max_page_content_size = 10000  # Maximum characters per page for batch summarization
        self.batch_max_output_chars = 1000  # Max chars per page summary
        self.final_max_output_chars = 2000  # Max chars for final summary
        self.max_batches_allowed = 5  # Maximum number of pages allowed for summarization

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """Validate search_terms, template_type, and recipient_name from Step 1."""
        if not pipeline_data.search_terms:
            return "search_terms is empty (Step 1 must run first)"

        if not pipeline_data.template_type:
            return "template_type not set (Step 1 must run first)"

        if not pipeline_data.recipient_name:
            return "recipient_name is missing"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """Search Google, scrape URLs, and summarize content for PipelineData."""
        # Step 1: Google Custom Search
        logfire.info(
            "Performing Google searches",
            search_terms=pipeline_data.search_terms,
            results_per_query=self.results_per_query
        )

        search_results = await self.google_client.search_multiple_terms(
            queries=pipeline_data.search_terms,
            results_per_query=self.results_per_query
        )

        if not search_results:
            logfire.warning("No search results found")
            pipeline_data.scraped_content = "No search results found."
            pipeline_data.scraped_page_contents = {}
            pipeline_data.scraped_urls = []
            pipeline_data.scraping_metadata = {
                "total_attempts": 0,
                "successful_scrapes": 0,
                "failed_urls": []
            }

            return StepResult(
                success=True,
                step_name=self.step_name,
                warnings=["No search results found for any query"],
                metadata={"search_results_count": 0}
            )

        # Extract URLs from search results
        urls_to_scrape = [
            result.get('link', '')
            for result in search_results
            if result.get('link')
        ][:self.max_pages_to_scrape]

        logfire.info(
            "URLs to scrape",
            total_urls=len(urls_to_scrape)
        )

        # Step 2: Scrape URLs concurrently
        scraped_pages = await self._scrape_urls_concurrent(urls_to_scrape)

        # Step 3: Build scraping result
        scraping_result = ScrapingResult(
            pages_scraped=scraped_pages,
            failed_urls=[
                url for url in urls_to_scrape
                if url not in [page.url for page in scraped_pages]
            ],
            total_attempts=len(urls_to_scrape),
            total_content_length=sum(len(page.content) for page in scraped_pages)
        )

        logfire.info(
            "Scraping completed",
            successful=len(scraped_pages),
            failed=len(scraping_result.failed_urls),
            success_rate=scraping_result.success_rate,
            total_content_length=scraping_result.total_content_length
        )

        if not scraped_pages:
            pipeline_data.scraped_content = "Failed to scrape any content."
            pipeline_data.scraped_page_contents = {}
            pipeline_data.scraped_urls = []
            pipeline_data.scraping_metadata = scraping_result.model_dump()

            return StepResult(
                success=True,
                step_name=self.step_name,
                warnings=["Failed to scrape any URLs"],
                metadata={"scraped_pages": 0}
            )

        # Step 4: Summarize content (page-based)
        # ALWAYS summarize with LLM for:
        # 1. Anti-hallucination fact checking
        # 2. Content filtering (removes boilerplate, duplicates)
        # 3. Context optimization for email generation
        # 4. Structured output format
        total_content_length = sum(len(page.content) for page in scraped_pages)
        logfire.info(
            "Summarizing content with LLM for fact verification",
            total_content_length=total_content_length,
            num_pages=len(scraped_pages)
        )

        final_content = await self._summarize_content(
            scraped_pages=scraped_pages,
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest,
            template_type=pipeline_data.template_type
        )

        # Check for uncertainty markers in the summary; just for logging
        has_uncertainty = "[UNCERTAIN]" in final_content or "[SINGLE SOURCE]" in final_content
        if has_uncertainty:
            logfire.warning(
                "Summary contains uncertainty markers",
                has_uncertain=("[UNCERTAIN]" in final_content),
                has_single_source=("[SINGLE SOURCE]" in final_content)
            )

        # Step 5: Update PipelineData
        pipeline_data.scraped_content = final_content
        pipeline_data.scraped_urls = [page.url for page in scraped_pages]
        pipeline_data.scraped_page_contents = {page.url: page.content for page in scraped_pages}
        pipeline_data.scraping_metadata = {
            "total_attempts": scraping_result.total_attempts,
            "successful_scrapes": len(scraped_pages),
            "failed_urls": scraping_result.failed_urls,
            "success_rate": scraping_result.success_rate,
            "total_content_length": scraping_result.total_content_length,
            "final_content_length": len(final_content),
            "was_summarized": True,
            "has_uncertainty_markers": has_uncertainty
        }

        # Return success
        return StepResult(
            success=True,
            step_name=self.step_name,
            metadata={
                "pages_scraped": len(scraped_pages),
                "urls_scraped": pipeline_data.scraped_urls,
                "content_length": len(final_content)
            },
            warnings=[
                f"{len(scraping_result.failed_urls)} URLs failed to scrape"
            ] if scraping_result.failed_urls else []
        )

    async def _scrape_urls_concurrent(
        self,
        urls: List[str]
    ) -> List[ScrapedPage]:
        """
        Scrape multiple URLs concurrently with semaphore using Playwright.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of successfully scraped pages
        """
        from playwright.async_api import async_playwright
        import time

        # Launch persistent browser for all scrapes
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox']
            )

            try:
                # Create semaphore for concurrency control
                semaphore = asyncio.Semaphore(self.max_concurrent_scrapes)

                async def scrape_with_semaphore(url: str) -> Optional[ScrapedPage]:
                    async with semaphore:
                        start = time.time()

                        # Pass browser to scrape_url (creates new context per URL)
                        title, content = await scrape_url(
                            url,
                            browser,
                            timeout=self.scrape_timeout
                        )

                        if content:
                            return ScrapedPage(
                                url=url,
                                title=title,
                                content=content,
                                word_count=len(content.split()),
                                scrape_time_seconds=time.time() - start
                            )
                        return None

                # Scrape all URLs
                tasks = [scrape_with_semaphore(url) for url in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Filter successful results
                scraped_pages = [
                    result for result in results
                    if isinstance(result, ScrapedPage)
                ]

                return scraped_pages

            finally:
                # Always close browser
                await browser.close()

    async def _summarize_batch(
        self,
        batch_content: str,
        batch_number: int,
        total_batches: int,
        recipient_name: str
    ) -> str:  # Returns summary text string, not Summary object
        """
        Summarize a single content batch using Haiku.

        This is an intermediate extraction step - focuses on completeness
        over conciseness. The final summary will filter and synthesize.

        Args:
            batch_content: Content chunk to summarize
            batch_number: Current batch index (1-based)
            total_batches: Total number of batches
            recipient_name: Professor name

        Returns:
            Batch summary (max 4000 chars)
        """
        from .prompts import BATCH_SUMMARIZATION_SYSTEM_PROMPT, create_batch_summarization_prompt

        # Create batch-specific agent (ephemeral)
        batch_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            output_type=Summary,
            system_prompt=BATCH_SUMMARIZATION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=3000,
            retries=2,
            timeout=60.0
        )

        user_prompt = create_batch_summarization_prompt(
            batch_content=batch_content,
            batch_number=batch_number,
            total_batches=total_batches,
            recipient_name=recipient_name
        )

        try:
            result = await batch_agent.run(user_prompt)
            summary_obj: Summary = result.output  # Summary object from pydantic-ai
            summary_text: str = summary_obj.summary  # Extract string field

            # Validate that summary is not empty
            if not summary_text or not summary_text.strip():
                logfire.warning(
                    "Batch summary is empty, using fallback",
                    batch_number=batch_number,
                    total_batches=total_batches
                )
                summary_text = f"No relevant information extracted from batch {batch_number}."

            logfire.info(
                "Batch summarized",
                batch_number=batch_number,
                total_batches=total_batches,
                input_length=len(batch_content),
                output_length=len(summary_text)
            )

            return summary_text[:4000]  # Enforce limit

        except Exception as e:
            error_msg = str(e)
            logfire.error(
                "Batch summarization failed",
                batch_number=batch_number,
                total_batches=total_batches,
                error=error_msg,
                error_type=type(e).__name__,
                input_size=len(batch_content)
            )

            # If validation failed due to empty summary, return a fallback
            if "Field required" in error_msg or "missing" in error_msg.lower():
                logfire.warning(
                    "Validation error detected, using fallback summary",
                    batch_number=batch_number,
                    input_length=len(batch_content)
                )
                return f"[Page {batch_number} content could not be summarized due to validation error. Input size: {len(batch_content)} chars. This may indicate the page was too large or contained incompatible content.]"

            # For other errors, raise
            raise ExternalAPIError(
                f"Failed to summarize batch {batch_number}/{total_batches}: {error_msg}"
            )

    async def _summarize_content(
        self,
        scraped_pages: List[ScrapedPage],
        recipient_name: str,
        recipient_interest: str,
        template_type: 'TemplateType'
    ) -> str:  # Returns summary text string, not Summary object
        """
        Two-tier page-based summarization with final synthesis.

        Architecture:
        1. Summarize each page independently (preserves source attribution)
        2. Combine page summaries
        3. Final synthesis with COT and anti-hallucination logic

        Args:
            scraped_pages: List of scraped pages (each with url and content)
            recipient_name: Professor name
            recipient_interest: Research area
            template_type: Template type (RESEARCH, BOOK, GENERAL)

        Returns:
            Final synthesized summary (max 3000 chars)
        """
        from .prompts import FINAL_SUMMARY_SYSTEM_PROMPT, create_final_summary_prompt

        # Edge case: No pages scraped
        if not scraped_pages:
            logfire.warning("No pages to summarize")
            return "No content available to summarize."

        # Edge case: Single page with small content (skip batch layer)
        if len(scraped_pages) == 1 and len(scraped_pages[0].content) <= self.chunk_size:
            logfire.info(
                "Single small page, using direct summarization",
                content_length=len(scraped_pages[0].content)
            )

            # Use existing single-pass logic
            user_prompt = create_summarization_prompt(
                scraped_content=scraped_pages[0].content,
                recipient_name=recipient_name,
                recipient_interest=recipient_interest,
                template_type=template_type
            )

            # Direct summarization without manual span wrapper
            # Let pydantic-ai's auto-instrumentation handle agent spans
            try:
                result = await self.summarization_agent.run(user_prompt)
                summary_obj: Summary = result.output  # Summary object from pydantic-ai
                summary_text: str = summary_obj.summary  # Extract string field

                logfire.info(
                    "Direct summarization completed",
                    original_length=len(scraped_pages[0].content),
                    summary_length=len(summary_text),
                    template_type=template_type.value
                )

                return summary_text[:3000]

            except Exception as e:
                logfire.error(
                    "Direct summarization failed",
                    error=str(e),
                    content_length=len(scraped_pages[0].content),
                    template_type=template_type.value
                )
                raise ExternalAPIError(f"Failed to summarize content: {str(e)}")

        # Main flow: Page-based batch processing
        total_pages = len(scraped_pages)

        # Enforce maximum number of pages allowed
        if total_pages > self.max_batches_allowed:
            logfire.warning(
                "Too many pages, limiting to max allowed",
                original_count=total_pages,
                limited_to=self.max_batches_allowed
            )
            scraped_pages = scraped_pages[:self.max_batches_allowed]
            total_pages = self.max_batches_allowed

        total_content_length = sum(len(page.content) for page in scraped_pages)

        logfire.info(
            "Starting page-based summarization",
            total_pages=total_pages,
            total_content_length=total_content_length,
            avg_page_length=total_content_length // total_pages
        )

        # Step 1: Page-level Summarizations
        # Each batch agent.run() will be auto-instrumented by pydantic-ai
        page_summaries = []

        logfire.info(
            "Processing page summarizations",
            total_pages=total_pages
        )

        for idx, page in enumerate(scraped_pages, start=1):
            # Truncate page content if it exceeds maximum size
            page_content = page.content
            was_truncated = False

            if len(page_content) > self.max_page_content_size:
                logfire.warning(
                    "Page content exceeds limit, truncating",
                    page_number=idx,
                    original_size=len(page_content),
                    truncated_to=self.max_page_content_size,
                    url=page.url
                )
                page_content = page_content[:self.max_page_content_size]
                was_truncated = True

            # Add truncation notice if content was truncated
            truncation_notice = "\n\n[CONTENT TRUNCATED - Original length exceeded 30,000 character limit]\n" if was_truncated else ""

            # Format page with URL marker for source attribution
            page_content_with_marker = f"""{'=' * 80}
=== PAGE {idx}: {page.url} ===
{'=' * 80}

Title: {page.title or 'N/A'}

{page_content}{truncation_notice}

{'=' * 80}
=== END PAGE {idx} ===
{'=' * 80}"""

            # Summarize this page (reusing existing batch summarization logic)
            page_summary = await self._summarize_batch(
                batch_content=page_content_with_marker,
                batch_number=idx,
                total_batches=total_pages,
                recipient_name=recipient_name
            )
            page_summaries.append(page_summary)

            # Add delay between page API calls to avoid rate limiting (429 errors)
            if idx < total_pages:
                await asyncio.sleep(2)

        # Step 2: Combine page summaries with markers
        combined_page_summaries = ""
        for idx, summary in enumerate(page_summaries, start=1):
            combined_page_summaries += f"{'=' * 80}\n"
            combined_page_summaries += f"=== PAGE {idx} SUMMARY ===\n"
            combined_page_summaries += f"{'=' * 80}\n\n"
            combined_page_summaries += f"{summary}\n\n"
            combined_page_summaries += f"{'=' * 80}\n"
            combined_page_summaries += f"=== END PAGE {idx} ===\n"
            combined_page_summaries += f"{'=' * 80}\n\n\n"

        logfire.info(
            "Page summaries combined",
            num_pages=len(page_summaries),
            combined_length=len(combined_page_summaries)
        )

        # Step 3: Final Summary Agent (with COT)
        # Agent.run() will be auto-instrumented by pydantic-ai
        final_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            output_type=Summary,
            system_prompt=FINAL_SUMMARY_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2500,
            retries=2,
            timeout=60.0
        )

        final_prompt = create_final_summary_prompt(
            batch_summaries=combined_page_summaries,
            recipient_name=recipient_name,
            recipient_interest=recipient_interest,
            template_type=template_type
        )

        try:
            result = await final_agent.run(final_prompt)
            summary_obj: Summary = result.output  # Summary object from pydantic-ai
            final_summary_text: str = summary_obj.summary  # Extract string field

            logfire.info(
                "Final summary completed",
                pages_processed=len(page_summaries),
                final_length=len(final_summary_text),
                template_type=template_type.value
            )

            return final_summary_text[:3000]

        except Exception as e:
            logfire.error(
                "Final summary generation failed",
                error=str(e),
                num_pages=len(page_summaries),
                template_type=template_type.value
            )
            raise ExternalAPIError(f"Failed to generate final summary: {str(e)}")