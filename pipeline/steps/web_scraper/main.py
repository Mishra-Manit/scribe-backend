"""
Web Scraper Step - Phase 5 Step 2

Performs web scraping using search terms from Step 1:
- Google Custom Search API to find URLs
- Async scraping with Playwright (headless browser)
- Content cleaning and summarization
- Updates PipelineData with results
"""

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
    Step 2: Web scraping and content extraction.

    Responsibilities:
    - Use search_terms from Step 1
    - Perform Google Custom Search
    - Scrape webpage content asynchronously
    - Clean and summarize content (max 5000 chars)
    - Update PipelineData

    Updates PipelineData fields:
    - scraped_content: str
    - scraped_urls: List[str]
    - scraping_metadata: Dict[str, Any]
    """

    def __init__(self):
        """Initialize web scraper step."""
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
            temperature=0.0,  # Zero temperature for maximum factual accuracy
            max_tokens=2000,  # Reduced to match 3000 char limit (~2k tokens)
            retries=2
        )

        # Configuration
        self.results_per_query = 3
        self.max_pages_to_scrape = 6
        self.scrape_timeout = 10.0
        self.max_concurrent_scrapes = 2  # Depends on celery workers RAM

        # Batch summarization configuration
        self.chunk_size = 30000  # Characters per chunk (for content splitting)
        self.batch_max_output_chars = 2000  # Max chars per batch summary
        self.final_max_output_chars = 3000  # Max chars for final summary

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate prerequisites from Step 1.

        Required:
        - search_terms: Non-empty list
        - template_type: Must be set
        - recipient_name and recipient_interest: Present
        """
        if not pipeline_data.search_terms:
            return "search_terms is empty (Step 1 must run first)"

        if not pipeline_data.template_type:
            return "template_type not set (Step 1 must run first)"

        if not pipeline_data.recipient_name:
            return "recipient_name is missing"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute web scraping logic.

        Steps:
        1. Perform Google Custom Search with all search terms
        2. Scrape URLs asynchronously (with concurrency limit)
        3. Clean and validate scraped content
        4. Summarize content using Anthropic (if too long)
        5. Update PipelineData
        """
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

        # Step 4: Combine and summarize content
        combined_content = self._combine_scraped_content(scraped_pages)

        # ALWAYS summarize with LLM for:
        # 1. Anti-hallucination fact checking
        # 2. Content filtering (removes boilerplate, duplicates)
        # 3. Context optimization for email generation
        # 4. Structured output format
        logfire.info(
            "Summarizing content with LLM for fact verification",
            original_length=len(combined_content),
            num_pages=len(scraped_pages)
        )

        final_content = await self._summarize_content(
            content=combined_content,
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest,
            template_type=pipeline_data.template_type
        )

        # Check for uncertainty markers in the summary
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
                args=['--no-sandbox']  # Required for containers/serverless
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

    def _combine_scraped_content(self, pages: List[ScrapedPage]) -> str:
        """
        Combine content from multiple pages with clear page markers.

        Each page is wrapped with delimiters for batch processing:
        - Start marker: === PAGE {index}: {url} ===
        - End marker: === END PAGE {index} ===

        This allows batch summarization to maintain source attribution.

        Args:
            pages: List of scraped pages

        Returns:
            Combined content string with page markers
        """
        parts = []

        for idx, page in enumerate(pages, start=1):
            # Start marker
            parts.append(f"{'=' * 80}\n")
            parts.append(f"=== PAGE {idx}: {page.url} ===\n")
            parts.append(f"{'=' * 80}\n\n")

            # Page title (if exists)
            if page.title:
                parts.append(f"Title: {page.title}\n\n")

            # Page content
            parts.append(f"{page.content}\n\n")

            # End marker
            parts.append(f"{'=' * 80}\n")
            parts.append(f"=== END PAGE {idx} ===\n")
            parts.append(f"{'=' * 80}\n\n\n")

        return ''.join(parts)

    def _split_into_chunks(self, content: str, chunk_size: int) -> List[str]:
        """
        Split content into chunks of exactly chunk_size characters.

        Args:
            content: Full combined text
            chunk_size: Target chunk size in characters

        Returns:
            List of content chunks, each ≤ chunk_size characters
        """
        if len(content) <= chunk_size:
            return [content]

        chunks = []
        position = 0
        content_length = len(content)

        while position < content_length:
            end_position = min(position + chunk_size, content_length)
            chunks.append(content[position:end_position])
            position = end_position

        return chunks

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
            temperature=0.0,  # Deterministic extraction
            max_tokens=3000,  # ~4000 chars
            retries=2
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

            logfire.info(
                "Batch summarized",
                batch_number=batch_number,
                total_batches=total_batches,
                input_length=len(batch_content),
                output_length=len(summary_text)
            )

            return summary_text[:4000]  # Enforce limit

        except Exception as e:
            logfire.error(
                "Batch summarization failed",
                batch_number=batch_number,
                total_batches=total_batches,
                error=str(e)
            )
            raise ExternalAPIError(
                f"Failed to summarize batch {batch_number}/{total_batches}: {str(e)}"
            )

    async def _summarize_content(
        self,
        content: str,
        recipient_name: str,
        recipient_interest: str,
        template_type: 'TemplateType'
    ) -> str:  # Returns summary text string, not Summary object
        """
        Two-tier summarization with batch processing and final synthesis.

        Architecture:
        1. Split content into 30K-char chunks
        2. Summarize each batch independently (extraction focus)
        3. Combine batch summaries
        4. Final synthesis with COT and anti-hallucination logic

        Args:
            content: Combined scraped content (all pages)
            recipient_name: Professor name
            recipient_interest: Research area
            template_type: Template type (RESEARCH, BOOK, GENERAL)

        Returns:
            Final synthesized summary (max 3000 chars)
        """
        from .prompts import FINAL_SUMMARY_SYSTEM_PROMPT, create_final_summary_prompt

        # Edge case: Content fits in single batch (skip batch layer)
        if len(content) <= self.chunk_size:
            logfire.info(
                "Content fits in single batch, using direct summarization",
                content_length=len(content)
            )

            # Use existing single-pass logic
            user_prompt = create_summarization_prompt(
                scraped_content=content,
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
                    original_length=len(content),
                    summary_length=len(summary_text),
                    content_length=len(content),
                    template_type=template_type.value
                )

                return summary_text[:3000]

            except Exception as e:
                logfire.error(
                    "Direct summarization failed",
                    error=str(e),
                    content_length=len(content),
                    template_type=template_type.value
                )
                raise ExternalAPIError(f"Failed to summarize content: {str(e)}")

        # Main flow: Multi-batch processing
        chunks = self._split_into_chunks(content, chunk_size=self.chunk_size)
        total_batches = len(chunks)

        logfire.info(
            "Starting batch summarization",
            total_content_length=len(content),
            num_batches=total_batches,
            avg_batch_size=len(content) // total_batches
        )

        # Step 1: Batch Summarizations
        # Each batch agent.run() will be auto-instrumented by pydantic-ai
        batch_summaries = []

        logfire.info(
            "Processing batch summarizations",
            total_batches=total_batches,
            content_length=len(content)
        )

        for idx, chunk in enumerate(chunks, start=1):
            batch_summary = await self._summarize_batch(
                batch_content=chunk,
                batch_number=idx,
                total_batches=total_batches,
                recipient_name=recipient_name
            )
            batch_summaries.append(batch_summary)

        # Step 2: Combine batch summaries with markers
        tiered_summarizations = ""
        for idx, summary in enumerate(batch_summaries, start=1):
            tiered_summarizations += f"{'=' * 80}\n"
            tiered_summarizations += f"=== BATCH {idx} SUMMARY ===\n"
            tiered_summarizations += f"{'=' * 80}\n\n"
            tiered_summarizations += f"{summary}\n\n"
            tiered_summarizations += f"{'=' * 80}\n"
            tiered_summarizations += f"=== END BATCH {idx} ===\n"
            tiered_summarizations += f"{'=' * 80}\n\n\n"

        logfire.info(
            "Batch summaries combined",
            num_batches=len(batch_summaries),
            combined_length=len(tiered_summarizations)
        )

        # Step 3: Final Summary Agent (with COT)
        # Agent.run() will be auto-instrumented by pydantic-ai
        final_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            output_type=Summary,
            system_prompt=FINAL_SUMMARY_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2500,
            retries=2
        )

        final_prompt = create_final_summary_prompt(
            batch_summaries=tiered_summarizations,
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
                batches_processed=len(batch_summaries),
                final_length=len(final_summary_text),
                num_batches=len(batch_summaries),
                template_type=template_type.value
            )

            return final_summary_text[:3000]

        except Exception as e:
            logfire.error(
                "Final summary generation failed",
                error=str(e),
                num_batches=len(batch_summaries),
                template_type=template_type.value
            )
            raise ExternalAPIError(f"Failed to generate final summary: {str(e)}")