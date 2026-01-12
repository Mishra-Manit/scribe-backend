"""Template parser step using Claude to extract search terms and classify template type."""

import logfire
from typing import Optional

from pipeline.core.runner import BasePipelineStep
from pipeline.models.core import PipelineData, StepResult
from pipeline.core.exceptions import ExternalAPIError, ValidationError
from config.settings import settings
from utils.llm_agent import create_agent

from .models import TemplateAnalysis
from .prompts import SYSTEM_PROMPT, create_user_prompt
from .utils import extract_placeholders


class TemplateParserStep(BasePipelineStep):
    """
    Parse template using Claude to extract search terms and classify type.

    Sets: search_terms, template_type, template_analysis
    """

    def __init__(self):
        super().__init__(step_name="template_parser")

        # Model configuration (hot-swappable via environment variable)
        self.model = settings.template_parser_model
        self.max_tokens = 2000
        self.temperature = 0.1  # Low temperature for consistent structured output

        # Template validation constants
        self.min_template_length = 20
        self.max_template_length = 5000

        # Create pydantic-ai agent for structured output
        # This agent automatically:
        # - Validates output against TemplateAnalysis schema
        # - Retries on validation failures
        # - Logs all inputs/outputs to Logfire
        self.agent = create_agent(
            model=self.model,
            output_type=TemplateAnalysis,
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            retries=2,
            timeout=30.0  # 30 second timeout for template parsing
        )

    async def _validate_input(self, pipeline_data: PipelineData) -> Optional[str]:
        """Validate required fields: email_template, recipient_name, recipient_interest."""
        if not (pipeline_data.email_template or '').strip():
            return "email_template is empty or missing"

        if not (pipeline_data.recipient_name or '').strip():
            return "recipient_name is empty or missing"

        if not (pipeline_data.recipient_interest or '').strip():
            return "recipient_interest is empty or missing"

        # Validate template has reasonable length
        if len(pipeline_data.email_template) < self.min_template_length:
            return f"email_template is too short (< {self.min_template_length} characters)"

        if len(pipeline_data.email_template) > self.max_template_length:
            return f"email_template is too long (> {self.max_template_length} characters)"

        return None

    async def _execute_step(self, pipeline_data: PipelineData) -> StepResult:
        """Parse template with Claude API and update PipelineData with search terms and type."""
        # Extract placeholders locally (for comparison)
        local_placeholders = extract_placeholders(pipeline_data.email_template)
        placeholder_count = len(local_placeholders)

        logfire.info(
            "Analyzing template",
            placeholder_count=placeholder_count,
            template_length=len(pipeline_data.email_template)
        )

        # Create prompt
        user_prompt = create_user_prompt(
            email_template=pipeline_data.email_template,
            recipient_name=pipeline_data.recipient_name,
            recipient_interest=pipeline_data.recipient_interest
        )

        # Call pydantic-ai agent for structured output
        # Agent automatically:
        # - Sends request to Anthropic API
        # - Validates response against TemplateAnalysis schema
        # - Retries on validation failures
        # - Logs everything to Logfire (inputs, outputs, tokens, cost, latency)
        logfire.info("Running pydantic-ai agent for template analysis")

        try:
            result = await self.agent.run(user_prompt)
            analysis = result.output  # Already validated TemplateAnalysis instance

            logfire.info(
                "Template analysis completed successfully",
                template_type=analysis.template_type.value,
                search_term_count=len(analysis.search_terms)
            )

        except Exception as e:
            # Catch all agent errors (API errors, validation errors, etc.)
            error_msg = f"Agent failed to analyze template: {str(e)}"
            logfire.error("Template analysis failed", error=error_msg)
            raise ExternalAPIError(error_msg)

        # Update PipelineData
        pipeline_data.search_terms = analysis.search_terms
        pipeline_data.template_type = analysis.template_type
        pipeline_data.template_analysis = {
            "placeholders": analysis.placeholders,
            "local_placeholders": local_placeholders,  # For debugging
        }

        # Log final state
        logfire.info(
            "PipelineData updated",
            search_terms=pipeline_data.search_terms,
            template_type=pipeline_data.template_type.value
        )

        # Return success
        return StepResult(
            success=True,
            step_name=self.step_name,
            metadata={
                "template_type": analysis.template_type.value,
                "search_term_count": len(analysis.search_terms),
                "placeholder_count": len(analysis.placeholders),
                "model_used": self.model
            }
        )