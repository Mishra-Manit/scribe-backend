import pytest
import logfire
from uuid import uuid4

from pipeline.steps.template_parser.main import TemplateParserStep
from pipeline.models.core import PipelineData

# Re-use the research_template fixture from the main test module
from .test_template_parser import research_template  # noqa: F401  (fixture import)


@pytest.mark.asyncio
async def test_logging_research_template(research_template):  # noqa: F811  (fixture override)
    """Execute TemplateParserStep on the research template and log everything."""

    parser = TemplateParserStep()

    # Construct minimal PipelineData object
    pipeline_data = PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template=research_template,
        recipient_name="Dr. Log Test",
        recipient_interest="machine learning",
    )

    # Run the step under a Logfire span so that all events are captured
    with logfire.span("test_logging_research_template"):
        result = await parser.execute(pipeline_data)
        logfire.info(
            "Logging research template test finished",
            success=result.success,
            template_type=pipeline_data.template_type.value if pipeline_data.template_type else None,
            search_terms=pipeline_data.search_terms,
            placeholders=pipeline_data.template_analysis.get("placeholders", []),
            metadata=result.metadata,
        )

    # Basic assertion to mark the test as failed if the step did not succeed
    assert result.success is True
