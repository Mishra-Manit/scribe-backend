"""Web scraper step using Exa Search API with dual-query strategy."""

import logfire
from typing import Optional
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError

from .exa_search import ExaSearchClient, DualQueryResult
from .prompts import build_background_query, build_publications_query


class WebScraperStep(BasePipelineStep):
    """Fetch professor info via dual Exa queries: background + publications."""

    def __init__(self):
        super().__init__(step_name="web_scraper")
        self.exa_client = ExaSearchClient()

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """Validate required fields from Step 1."""
        if not pipeline_data.search_terms:
            return "search_terms is empty (Step 1 must run first)"
        if not pipeline_data.template_type:
            return "template_type not set (Step 1 must run first)"
        if not pipeline_data.recipient_name:
            return "recipient_name is missing"
        return None

    def _build_queries(self, pipeline_data: PipelineData) -> tuple[str, str]:
        """Build background and publications queries."""
        background = build_background_query(
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest or "their research area"
        )
        publications = build_publications_query(
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest or "their research area",
            template_type=pipeline_data.template_type
        )
        return background, publications

    def _format_result(self, result: DualQueryResult) -> str:
        """Format combined answer with sources."""
        formatted = result.combined_answer

        if result.all_citations:
            sources = [f"- {c.title or 'Source'}: {c.url}" for c in result.all_citations]
            formatted += "\n\n**SOURCES:**\n" + "\n".join(sources)

        return formatted

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """Execute dual Exa queries and combine results."""
        background_query, publications_query = self._build_queries(pipeline_data)

        logfire.info(
            "Executing dual queries",
            recipient=pipeline_data.recipient_name,
            template_type=pipeline_data.template_type.value
        )

        try:
            result = await self.exa_client.dual_answer(
                background_query=background_query,
                publications_query=publications_query,
                timeout=45.0
            )

            # Handle empty results
            if not result.combined_answer or result.combined_answer == "No information found.":
                logfire.warning("Empty Exa result", recipient=pipeline_data.recipient_name)
                pipeline_data.scraped_content = "No information found for this professor."
                pipeline_data.scraped_urls = []
                pipeline_data.scraped_page_contents = {}
                pipeline_data.scraping_metadata = {
                    "source": "exa_dual",
                    "success": False,
                    "citation_count": 0
                }
                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    warnings=["No information found in Exa search"],
                    metadata={"citation_count": 0}
                )

            # Format and store results
            formatted = self._format_result(result)
            pipeline_data.scraped_content = formatted
            pipeline_data.scraped_urls = [c.url for c in result.all_citations]
            pipeline_data.scraped_page_contents = {
                c.url: c.text or "" for c in result.all_citations if c.text
            }
            pipeline_data.scraping_metadata = {
                "source": "exa_dual",
                "success": True,
                "citation_count": len(result.all_citations),
                "background_length": len(result.background.answer),
                "publications_length": len(result.publications.answer),
                "combined_length": len(result.combined_answer)
            }

            logfire.info(
                "Dual search complete",
                bg_len=len(result.background.answer),
                pub_len=len(result.publications.answer),
                citations=len(result.all_citations),
                background_summary=result.background.answer,
                publications_summary=result.publications.answer,
                combined_summary=result.combined_answer
            )

            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "citation_count": len(result.all_citations),
                    "urls": pipeline_data.scraped_urls,
                    "content_length": len(formatted)
                }
            )

        except TimeoutError as e:
            logfire.error("Exa timeout", error=str(e), recipient=pipeline_data.recipient_name)
            raise ExternalAPIError(f"Exa search timed out: {e}")
        except ConnectionError as e:
            logfire.error("Exa connection error", error=str(e), recipient=pipeline_data.recipient_name)
            raise ExternalAPIError(f"Failed to connect to Exa API: {e}")
        except Exception as e:
            logfire.error("Exa failed", error_type=type(e).__name__, error=str(e))
            raise ExternalAPIError(f"Exa search failed ({type(e).__name__}): {e}")
