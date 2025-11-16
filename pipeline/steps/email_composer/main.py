"""
Email Composer Step - Phase 5 Step 4

Final pipeline step - generates email and writes to database.

Responsibilities:
- Generate email using Anthropic Claude API
- Validate email quality
- Retry if validation fails
- Write to database
- Update PipelineData with final email
"""

import logfire
from typing import Optional

from config.settings import settings
from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from utils.llm_agent import create_agent

from .models import ComposedEmail
from .prompts import SYSTEM_PROMPT, create_composition_prompt
from .utils import validate_email, clean_email_formatting
from .db_utils import write_email_to_db, increment_user_generation_count


class EmailComposerStep(BasePipelineStep):
    """
    Step 4: Generate final email and write to database.

    Responsibilities:
    - Combine data from Steps 1-3
    - Generate email via Anthropic Claude API
    - Validate email quality
    - Retry if validation fails (max 2 attempts)
    - Write to database
    - Update PipelineData

    Updates PipelineData fields:
    - final_email: str (final composed email)
    - composition_metadata: dict (generation metadata)
    - metadata["email_id"]: UUID (CRITICAL for pipeline tracking)
    """

    def __init__(self):
        """Initialize email composer step."""
        super().__init__(step_name="email_composer")

        # Configuration
        self.model = "anthropic:claude-sonnet-4-5-20250929"
        self.temperature = 0.7  # Higher for creative writing
        self.max_tokens = 2000
        self.max_retries = 2  # Total attempts = 3 (initial + 2 retries)

        # Create pydantic-ai agent for email composition
        # Using Sonnet for high-quality, creative email writing
        self.composition_agent = create_agent(
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            retries=1  # Agent-level retries (validation retries handled separately)
        )

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """
        Validate prerequisites.

        Required:
        - email_template: Original template (from initialization)
        - recipient_name: Recipient name
        - recipient_interest: Research interest
        - template_analysis: Analysis from Step 1
        - scraped_content: Web data from Step 2
        - user_id: For database write

        Optional:
        - arxiv_papers: Papers from Step 3 (may be empty)
        """
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
        """
        Execute email generation and database write.

        Steps:
        1. Prepare composition prompt
        2. Generate email via Anthropic API
        3. Validate email quality
        4. Retry if validation fails (max 2 retries)
        5. Write to database
        6. Update PipelineData
        """
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

            # Step 2 & 3: Generate and validate (with retries)
            composed_email = await self._generate_with_validation(
                user_prompt=user_prompt,
                recipient_name=pipeline_data.recipient_name,
                template_type=pipeline_data.template_type
            )

            if not composed_email:
                # All retry attempts failed
                return StepResult(
                    success=False,
                    step_name=self.step_name,
                    error="Failed to generate valid email after all retry attempts"
                )

            # Step 4: Write to database
            email_id = await write_email_to_db(
                user_id=pipeline_data.user_id,
                recipient_name=pipeline_data.recipient_name,
                recipient_interest=pipeline_data.recipient_interest,
                email_content=composed_email.email_content
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
                word_count=composed_email.validation_result.word_count
            )

            # Step 5: Increment user generation count (non-critical)
            await increment_user_generation_count(user_id=pipeline_data.user_id)

            # Step 6: Update PipelineData
            pipeline_data.final_email = composed_email.email_content

            pipeline_data.composition_metadata = {
                "email_id": str(email_id),
                "word_count": composed_email.validation_result.word_count,
                "mentions_publications": composed_email.validation_result.mentions_publications,
                "validation_warnings": composed_email.validation_result.warnings,
                "model": self.model,
                "temperature": self.temperature,
                **composed_email.generation_metadata
            }

            # CRITICAL: Set email_id in metadata for PipelineRunner
            pipeline_data.metadata["email_id"] = email_id

            # Return success
            return StepResult(
                success=True,
                step_name=self.step_name,
                metadata={
                    "email_id": str(email_id),
                    "word_count": composed_email.validation_result.word_count,
                    "mentions_publications": composed_email.validation_result.mentions_publications,
                    "warnings": composed_email.validation_result.warnings
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

    async def _generate_with_validation(
        self,
        user_prompt: str,
        recipient_name: str,
        template_type: 'TemplateType'
    ) -> Optional[ComposedEmail]:
        """
        Generate email with validation and retry logic.

        Args:
            user_prompt: Formatted prompt for Claude
            recipient_name: Recipient name for validation
            template_type: Type of template (RESEARCH, BOOK, or GENERAL)

        Returns:
            ComposedEmail if successful, None if all retries failed
        """
        for attempt in range(self.max_retries + 1):
            try:
                logfire.info(
                    "Generating email attempt",
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1
                )

                # Call pydantic-ai agent for email generation
                # Agent automatically logs to Logfire (prompt, response, tokens, cost, latency)
                result = await self.composition_agent.run(user_prompt)
                raw_email = result.output.strip()

                # Clean formatting
                cleaned_email = clean_email_formatting(raw_email)

                logfire.info(
                    "Email generated",
                    attempt=attempt + 1,
                    word_count=len(cleaned_email.split()),
                    length=len(cleaned_email)
                )

                # Validate email
                validation_result = validate_email(
                    email_content=cleaned_email,
                    recipient_name=recipient_name,
                    template_type=template_type
                )

                # Check if valid
                if validation_result.is_valid:
                    logfire.info(
                        "Email validation passed",
                        attempt=attempt + 1,
                        warnings_count=len(validation_result.warnings)
                    )

                    # Build ComposedEmail
                    # Note: Token counts are automatically logged to Logfire by pydantic-ai
                    composed_email = ComposedEmail(
                        email_content=cleaned_email,
                        validation_result=validation_result,
                        generation_metadata={
                            "attempts": attempt + 1,
                            "model": self.model
                        }
                    )

                    return composed_email

                else:
                    # Validation failed
                    logfire.warning(
                        "Email validation failed",
                        attempt=attempt + 1,
                        issues=validation_result.issues,
                        warnings=validation_result.warnings
                    )

                    # Retry if attempts remain
                    if attempt < self.max_retries:
                        logfire.info(
                            "Retrying email generation",
                            remaining_attempts=self.max_retries - attempt
                        )
                        continue
                    else:
                        # No more retries - return last attempt anyway
                        logfire.error(
                            "All validation attempts failed - using last attempt",
                            issues=validation_result.issues
                        )

                        # Return despite validation failure
                        # Note: Token usage is already logged by pydantic-ai
                        composed_email = ComposedEmail(
                            email_content=cleaned_email,
                            validation_result=validation_result,
                            generation_metadata={
                                "attempts": attempt + 1,
                                "validation_failed": True
                            }
                        )

                        return composed_email

            except Exception as e:
                logfire.error(
                    "Error during email generation attempt",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__
                )

                # Retry if attempts remain
                if attempt < self.max_retries:
                    continue
                else:
                    # All attempts failed
                    return None

        # Should not reach here, but return None as fallback
        return None
