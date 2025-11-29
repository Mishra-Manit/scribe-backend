"""
ArXiv Helper Step - Phase 5 Step 3

Conditionally fetches academic papers from ArXiv API:
- Only runs if template_type == RESEARCH
- Searches for papers by recipient
- Updates PipelineData with paper information
"""

import logfire
from typing import Optional

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult, TemplateType

from .utils import search_arxiv


class ArxivHelperStep(BasePipelineStep):
    """
    Step 3: Fetch academic papers from ArXiv (conditional).

    Responsibilities:
    - Check if template_type == RESEARCH
    - Search ArXiv for papers by recipient
    - Update PipelineData with paper info (title, authors, abstract, published_date, arxiv_url)

    Updates PipelineData fields:
    - arxiv_papers: List[Dict[str, Any]]
    - enrichment_metadata: Dict[str, Any]
    """

    def __init__(self):
        """Initialize ArXiv helper step."""
        super().__init__(step_name="arxiv_helper")

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate prerequisites.

        Required:
        - template_type: Must be set (from Step 1)
        - recipient_name: Required for author search
        - recipient_interest: Required for pipeline context
        """
        if not pipeline_data.template_type:
            return "template_type not set (Step 1 must run first)"

        if not pipeline_data.recipient_name:
            return "recipient_name is missing"

        if not pipeline_data.recipient_interest:
            return "recipient_interest is missing"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """
        Execute ArXiv paper fetching.

        Steps:
        1. Check if template_type == RESEARCH (skip if not)
        2. Search ArXiv for papers by recipient
        3. Update PipelineData with paper info
        """
        try:
            # Step 1: Check template type
            if pipeline_data.template_type != TemplateType.RESEARCH:
                logfire.info(
                    "Skipping ArXiv search - not RESEARCH template",
                    template_type=pipeline_data.template_type.value
                )

                # Set empty results
                pipeline_data.arxiv_papers = []
                pipeline_data.enrichment_metadata = {
                    "skipped": True,
                    "reason": f"template_type is {pipeline_data.template_type.value}, not RESEARCH"
                }

                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    metadata={
                        "skipped": True,
                        "template_type": pipeline_data.template_type.value
                    }
                )

            # Step 2: Search ArXiv
            logfire.info(
                "Searching ArXiv for papers",
                recipient_name=pipeline_data.recipient_name
            )

            papers = await search_arxiv(
                author_name=pipeline_data.recipient_name
            )

            if not papers:
                logfire.warning(
                    "No papers found on ArXiv",
                    recipient_name=pipeline_data.recipient_name
                )

                pipeline_data.arxiv_papers = []
                pipeline_data.enrichment_metadata = {
                    "papers_found": 0,
                    "search_query": pipeline_data.recipient_name
                }

                return StepResult(
                    success=True,
                    step_name=self.step_name,
                    warnings=["No papers found on ArXiv"],
                    metadata={"papers_found": 0}
                )

            # Step 3: Update PipelineData with papers
            logfire.info(
                "ArXiv papers found",
                total_papers=len(papers),
                paper_titles=[p.title for p in papers[:3]]
            )

            pipeline_data.arxiv_papers = [
                paper.to_dict() for paper in papers
            ]

            pipeline_data.enrichment_metadata = {
                "papers_found": len(papers),
                "search_query": pipeline_data.recipient_name,
                "skipped": False
            }

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "papers_found": len(papers),
                    "paper_titles": [p.title for p in papers[:3]]
                }
            )

        except Exception as e:
            logfire.error(
                "Error in ArXiv helper",
                error=str(e),
                error_type=type(e).__name__
            )

            # ArXiv errors are not fatal - continue pipeline with empty results
            pipeline_data.arxiv_papers = []
            pipeline_data.enrichment_metadata = {
                "error": str(e),
                "papers_found": 0
            }

            return StepResult(
                success=True,
                step_name=self.step_name,
                warnings=[f"ArXiv search failed: {str(e)}"],
                metadata={"error": str(e)}
            )