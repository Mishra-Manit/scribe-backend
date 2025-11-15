"""
Web Scraper Step - Phase 5 Step 2

Performs web scraping using search terms from Step 1:
- Google Custom Search API to find URLs
- Async scraping with BeautifulSoup
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

from .models import ScrapedPage, ScrapingResult
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
        # Using Sonnet for high-quality summarization
        self.summarization_agent = create_agent(
            model="anthropic:claude-haiku-4-5",
            system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=3000,
            retries=2
        )

        # Configuration
        self.results_per_query = 6
        self.max_pages_to_scrape = 10
        self.scrape_timeout = 10.0
        self.max_concurrent_scrapes = 5

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
        try:
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

            # If too long, summarize with LLM
            if len(combined_content) > 15000:
                logfire.info(
                    "Content too long, summarizing with LLM",
                    original_length=len(combined_content)
                )

                final_content = await self._summarize_content(
                    content=combined_content,
                    recipient_name=pipeline_data.recipient_name,
                    recipient_interest=pipeline_data.recipient_interest,
                    template_type=pipeline_data.template_type
                )
            else:
                # Content is reasonable length - use as is (with truncation)
                final_content = combined_content[:5000]

            # Step 5: Update PipelineData
            pipeline_data.scraped_content = final_content
            pipeline_data.scraped_urls = [page.url for page in scraped_pages]
            pipeline_data.scraping_metadata = {
                "total_attempts": scraping_result.total_attempts,
                "successful_scrapes": len(scraped_pages),
                "failed_urls": scraping_result.failed_urls,
                "success_rate": scraping_result.success_rate,
                "total_content_length": scraping_result.total_content_length,
                "final_content_length": len(final_content),
                "was_summarized": len(combined_content) > 15000
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

        except ExternalAPIError:
            raise
        except Exception as e:
            logfire.error(
                "Unexpected error in web scraper",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def _scrape_urls_concurrent(
        self,
        urls: List[str]
    ) -> List[ScrapedPage]:
        """
        Scrape multiple URLs concurrently with semaphore.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of successfully scraped pages
        """
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent_scrapes)

        async def scrape_with_semaphore(url: str) -> Optional[ScrapedPage]:
            async with semaphore:
                import time
                start = time.time()

                title, content = await scrape_url(url, timeout=self.scrape_timeout)

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

    def _combine_scraped_content(self, pages: List[ScrapedPage]) -> str:
        """
        Combine content from multiple pages.

        Args:
            pages: List of scraped pages

        Returns:
            Combined content string
        """
        combined = ""

        for page in pages:
            combined += f"URL: {page.url}\n"
            if page.title:
                combined += f"Title: {page.title}\n"
            combined += f"\n{page.content}\n\n"
            combined += "#" * 100 + "\n\n"

        return combined

    async def _summarize_content(
        self,
        content: str,
        recipient_name: str,
        recipient_interest: str,
        template_type: 'TemplateType'
    ) -> str:
        """
        Summarize content using pydantic-ai agent.

        Args:
            content: Combined scraped content
            recipient_name: Professor name
            recipient_interest: Research area
            template_type: Type of template (RESEARCH, BOOK, or GENERAL)

        Returns:
            Summarized content (max 5000 chars)
        """
        user_prompt = create_summarization_prompt(
            scraped_content=content,
            recipient_name=recipient_name,
            recipient_interest=recipient_interest,
            template_type=template_type
        )

        try:
            # Use pydantic-ai agent for summarization
            # Agent automatically logs to Logfire (prompt, response, tokens, cost, latency)
            result = await self.summarization_agent.run(user_prompt)
            summary = result.output

            logfire.info(
                "Content summarized successfully",
                original_length=len(content),
                summary_length=len(summary)
            )

            return summary[:5000]  # Enforce limit

        except Exception as e:
            logfire.error("Failed to summarize content", error=str(e))
            # Fallback: truncate original content
            return content[:5000]