"""
Pipeline factory function.

This module provides create_email_pipeline() which instantiates
all pipeline steps in the correct order.
"""

from pipeline.core.runner import PipelineRunner
from pipeline.steps.template_parser.main import TemplateParserStep
# TODO: change this later as the packages are implemented
# from pipeline.steps.web_scraper.main import WebScraperStep
# from pipeline.steps.arxiv_helper.main import ArxivHelperStep
# from pipeline.steps.email_composer.main import EmailComposerStep


def create_email_pipeline() -> PipelineRunner:
    """
    Factory function to create a fully configured email generation pipeline.

    Steps are registered in execution order:
    1. TemplateParser: Extract search terms from template
    2. WebScraper: Fetch web content using search terms
    3. ArxivHelper: Fetch academic papers (conditional on template_type)
    4. EmailComposer: Generate final email and write to database

    Returns:
        PipelineRunner with all steps registered and ready to execute

    Example:
        ```python
        from pipeline import create_email_pipeline
        from pipeline.models.core import PipelineData, TemplateType

        # Create pipeline
        runner = create_email_pipeline()

        # Create pipeline data
        pipeline_data = PipelineData(
            task_id="abc-123",
            user_id="user-456",
            email_template="Hey {{name}}, I loved your work on {{research}}!",
            recipient_name="Dr. Jane Smith",
            recipient_interest="machine learning",
            template_type=TemplateType.RESEARCH
        )

        # Run pipeline
        email_id = await runner.run(pipeline_data)
        print(f"Generated email: {email_id}")
        ```

    Note:
        Step implementations are defined in Phase 5+. If step classes
        are not yet implemented, imports will fail with ImportError.
    """
    runner = PipelineRunner()

    # Register steps in execution order
    # Each step inherits from BasePipelineStep and implements _execute_step()
    runner.register_step(TemplateParserStep())
    # TODO: change this later as the packages are implemented
    # runner.register_step(WebScraperStep())
    # runner.register_step(ArxivHelperStep())
    # runner.register_step(EmailComposerStep())

    return runner
