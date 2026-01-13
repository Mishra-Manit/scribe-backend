"""Final pipeline step to generate email with Claude and write to database."""

import json
import logfire
from typing import Optional

from config.settings import settings
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult, TemplateType
from utils.llm_agent import create_agent

from .models import ComposedEmail
from .prompts import SYSTEM_PROMPT, create_composition_prompt
from .db_utils import write_email_to_db, increment_user_generation_count


class EmailComposerStep(BasePipelineStep):
    """Generate final email with Claude and write to database."""

    def __init__(self):
        super().__init__(step_name="email_composer")

        # Configuration (hot-swappable via environment variable)
        self.model = settings.email_composer_model
        self.temperature = 0.7
        self.max_tokens = 2000

        # Create pydantic-ai agent for email composition
        # Using Sonnet for high-quality, creative email writing
        self.composition_agent = create_agent(
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            retries=3,  # Agent handles retries internally
            timeout=60.0
        )

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """Validate required fields from Steps 1-3 and user_id for database write."""
        if not pipeline_data.email_template:
            return "email_template is missing"

        if not pipeline_data.recipient_name:
            return "recipient_name is missing"

        if not pipeline_data.recipient_interest:
            return "recipient_interest is missing"

        if not pipeline_data.template_analysis:
            return "template_analysis is missing (Step 1 must run first)"

        if not pipeline_data.scraped_content:
            return "scraped_content is missing (Step 2 must run first)"

        if not pipeline_data.user_id:
            return "user_id is missing (required for database write)"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """Generate email with Claude, write to database, and update PipelineData."""
        try:
            # Step 1: Prepare prompt
            user_prompt = create_composition_prompt(
                email_template=pipeline_data.email_template,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                scraped_content=pipeline_data.scraped_content,
                arxiv_papers=pipeline_data.arxiv_papers or [],
                template_analysis=pipeline_data.template_analysis
            )

            logfire.info(
                "Generating email with Anthropic",
                model=self.model,
                temperature=self.temperature,
                recipient_name=pipeline_data.recipient_name
            )

            # Step 2: Generate email via LLM (agent handles retries internally)
            result = await self.composition_agent.run(user_prompt)
            response_text = result.output.strip()

            # Parse JSON response
            try:
                parsed = json.loads(response_text)
                email_text = parsed["email"]
                is_confident = parsed.get("is_confident", False)
            except (json.JSONDecodeError, KeyError) as e:
                logfire.warning(
                    "Failed to parse JSON response, falling back to plain text",
                    error=str(e),
                    response_preview=response_text[:200]
                )
                # Fallback: treat entire response as email text
                email_text = response_text
                is_confident = False

            logfire.info(
                "Email generated successfully",
                word_count=len(email_text.split()),
                length=len(email_text),
                is_confident=is_confident
            )

            # Step 3: Create composed email object
            composed_email = ComposedEmail(
                email_content=email_text,
                is_confident=is_confident,
                generation_metadata={
                    "model": self.model,
                },
            )

            # Step 4: Prepare metadata for database
            # Aggregate all pipeline metadata for JSONB storage
            database_metadata = {
                "search_terms": pipeline_data.search_terms,
                "template_type": pipeline_data.template_type.value,
                "scraped_urls": pipeline_data.scraped_urls,
                "scraping_metadata": pipeline_data.scraping_metadata,
                "arxiv_papers": [
                    {
                        "title": paper.get("title"),
                        "arxiv_url": paper.get("arxiv_url"),
                        "year": paper.get("year")
                    }
                    for paper in (pipeline_data.arxiv_papers or [])
                ],
                "step_timings": pipeline_data.step_timings,
                "generation_metadata": composed_email.generation_metadata,
                "model": self.model,
                "temperature": self.temperature
            }

            # Step 5: Write to database
            email_id = await write_email_to_db(
                user_id=pipeline_data.user_id,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                email_content=composed_email.email_content,
                template_type=pipeline_data.template_type,
                metadata=database_metadata,
                is_confident=composed_email.is_confident
            )

            if not email_id:
                return StepResult(
                    success=False,
                    step_name=self.step_name,
                    error="Failed to write email to database"
                )

            logfire.info(
                "Email written to database",
                email_id=str(email_id),
                word_count=len(composed_email.email_content.split())
            )

            # Step 6: Increment user generation count (non-critical)
            await increment_user_generation_count(user_id=pipeline_data.user_id)

            # Step 7: Update PipelineData
            pipeline_data.final_email = composed_email.email_content
            pipeline_data.is_confident = composed_email.is_confident

            pipeline_data.composition_metadata = {
                "email_id": str(email_id),
                "word_count": len(composed_email.email_content.split()),
                "model": self.model,
                "temperature": self.temperature,
                "is_confident": composed_email.is_confident,
                **composed_email.generation_metadata
            }

            pipeline_data.metadata["email_id"] = email_id

            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "email_id": str(email_id),
                    "word_count": len(composed_email.email_content.split()),
                }
            )

        except Exception as e:
            logfire.error(
                "Error in email composer",
                error=str(e),
                error_type=type(e).__name__
            )

            return StepResult(
                success=False,
                step_name=self.step_name,
                error=f"Email composer error: {str(e)}"
            )
