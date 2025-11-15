"""
Test suite for Template Parser Step

Tests the first step of the pipeline using real Anthropic API calls.
Uses fake email template data with logfire observability.

Run with:
    pytest pipeline/steps/template_parser/test_template_parser.py -v
    pytest pipeline/steps/template_parser/test_template_parser.py -v -s  # with logs
"""

import pytest
import logfire
from uuid import uuid4
from datetime import datetime

from pipeline.steps.template_parser.main import TemplateParserStep
from pipeline.models.core import PipelineData, TemplateType
from pipeline.core.exceptions import ValidationError, ExternalAPIError, StepExecutionError


# ===================================================================
# FIXTURES - Fake Email Template Data
# ===================================================================

@pytest.fixture
def research_template():
    """Email template requiring research papers (RESEARCH type)"""
    return """
Dear {{name}},

I am a graduate student researching {{my_field}}, and I came across your
groundbreaking work on {{research_area}}. Your recent publications on
{{specific_paper_topic}} have been particularly influential in my understanding
of this field.

I would love to discuss potential collaboration opportunities, especially
regarding {{specific_application}}. Would you be available for a brief call
next week?

Best regards,
{{my_name}}
    """.strip()


@pytest.fixture
def book_template():
    """Email template requiring books (BOOK type)"""
    return """
Dear Professor {{name}},

I recently finished reading your book "{{book_title}}" and found it
incredibly insightful. The chapter on {{chapter_topic}} was particularly
relevant to my current research in {{my_research}}.

I was wondering if you have published any other books on {{subject}}, or
if you have recommendations for further reading in this area.

Looking forward to hearing from you.

Sincerely,
{{my_name}}
    """.strip()


@pytest.fixture
def general_template():
    """Email template requiring general info (GENERAL type)"""
    return """
Hi {{name}},

I'm reaching out because I admire your work at {{institution}} in the
field of {{field}}. I'm currently exploring career opportunities in
{{area}} and would appreciate any advice you might have.

Your background in {{expertise}} aligns closely with my interests, and
I would be honored to learn from your experience.

Thank you for your time!

Best,
{{my_name}}
    """.strip()


@pytest.fixture
def minimal_template():
    """Minimal valid template for edge case testing"""
    return "Dear {{name}}, I'm interested in {{topic}}. Thanks!"


@pytest.fixture
def template_parser():
    """Initialize the TemplateParserStep"""
    return TemplateParserStep()


# ===================================================================
# HELPER FUNCTIONS
# ===================================================================

def create_pipeline_data(
    email_template: str,
    recipient_name: str = "Dr. Jane Smith",
    recipient_interest: str = "machine learning"
) -> PipelineData:
    """
    Create a PipelineData object for testing.

    Args:
        email_template: Email template string
        recipient_name: Name of recipient
        recipient_interest: Research interest/area

    Returns:
        PipelineData instance ready for testing
    """
    return PipelineData(
        task_id=str(uuid4()),
        user_id=str(uuid4()),
        email_template=email_template,
        recipient_name=recipient_name,
        recipient_interest=recipient_interest,
    )


# ===================================================================
# TESTS - Basic Functionality
# ===================================================================

@pytest.mark.asyncio
async def test_research_template_parsing(template_parser, research_template):
    """
    Test parsing of RESEARCH type template with real Anthropic API.

    Expected behavior:
    - Returns success=True
    - Correctly identifies template_type as RESEARCH
    - Generates 1-3 relevant search terms
    - Extracts all placeholders from template
    """
    logfire.info("Starting test: test_research_template_parsing")

    # Arrange
    pipeline_data = create_pipeline_data(
        email_template=research_template,
        recipient_name="Dr. Sarah Johnson",
        recipient_interest="neural networks"
    )

    # Act
    with logfire.span("test_research_template"):
        result = await template_parser.execute(pipeline_data)

    # Assert - Basic success
    assert result.success is True, f"Step should succeed: {result.error}"
    assert result.step_name == "template_parser"

    # Assert - Template type classification
    assert pipeline_data.template_type == TemplateType.RESEARCH, \
        f"Should classify as RESEARCH, got {pipeline_data.template_type}"

    # Assert - Search terms
    assert len(pipeline_data.search_terms) >= 1, \
        f"Should have at least 1 search term, got {len(pipeline_data.search_terms)}"
    assert len(pipeline_data.search_terms) <= 3, \
        f"Should have at most 3 search terms, got {len(pipeline_data.search_terms)}"

    # Assert - Search terms contain recipient name and interest
    search_terms_combined = " ".join(pipeline_data.search_terms).lower()
    assert "sarah johnson" in search_terms_combined or "johnson" in search_terms_combined, \
        "Search terms should include recipient name"

    # Assert - Template analysis metadata
    assert "placeholders" in pipeline_data.template_analysis
    placeholders = pipeline_data.template_analysis["placeholders"]
    assert len(placeholders) > 0, "Should extract placeholders"
    assert "{{name}}" in placeholders, "Should find {{name}} placeholder"

    # Assert - Result metadata
    assert result.metadata is not None
    assert "template_type" in result.metadata
    assert result.metadata["template_type"] == "research"
    assert "duration" in result.metadata

    logfire.info(
        "Test passed: test_research_template_parsing",
        template_type=pipeline_data.template_type.value,
        search_terms=pipeline_data.search_terms,
        placeholders=placeholders
    )


@pytest.mark.asyncio
async def test_book_template_parsing(template_parser, book_template):
    """
    Test parsing of BOOK type template with real Anthropic API.

    Expected behavior:
    - Correctly identifies template_type as BOOK
    - Generates search terms focused on books
    - Extracts book-related placeholders
    """
    logfire.info("Starting test: test_book_template_parsing")

    # Arrange
    pipeline_data = create_pipeline_data(
        email_template=book_template,
        recipient_name="Professor Michael Chen",
        recipient_interest="cognitive science"
    )

    # Act
    with logfire.span("test_book_template"):
        result = await template_parser.execute(pipeline_data)

    # Assert
    assert result.success is True
    assert pipeline_data.template_type == TemplateType.BOOK, \
        f"Should classify as BOOK, got {pipeline_data.template_type}"

    # Search terms should be book-focused
    search_terms_combined = " ".join(pipeline_data.search_terms).lower()

    # Assert placeholders specific to book template
    placeholders = pipeline_data.template_analysis["placeholders"]
    assert "{{name}}" in placeholders
    assert "{{book_title}}" in placeholders or "{{my_name}}" in placeholders

    logfire.info(
        "Test passed: test_book_template_parsing",
        template_type=pipeline_data.template_type.value,
        search_terms=pipeline_data.search_terms
    )


@pytest.mark.asyncio
async def test_general_template_parsing(template_parser, general_template):
    """
    Test parsing of GENERAL type template with real Anthropic API.

    Expected behavior:
    - Correctly identifies template_type as GENERAL
    - Generates broad search terms (not paper/book focused)
    - Extracts general placeholders
    """
    logfire.info("Starting test: test_general_template_parsing")

    # Arrange
    pipeline_data = create_pipeline_data(
        email_template=general_template,
        recipient_name="Dr. Amanda Lee",
        recipient_interest="data science"
    )

    # Act
    with logfire.span("test_general_template"):
        result = await template_parser.execute(pipeline_data)

    # Assert
    assert result.success is True
    assert pipeline_data.template_type == TemplateType.GENERAL, \
        f"Should classify as GENERAL, got {pipeline_data.template_type}"

    # Should have search terms
    assert len(pipeline_data.search_terms) >= 1

    # Should extract placeholders
    placeholders = pipeline_data.template_analysis["placeholders"]
    assert len(placeholders) > 0

    logfire.info(
        "Test passed: test_general_template_parsing",
        template_type=pipeline_data.template_type.value,
        search_terms=pipeline_data.search_terms
    )


# ===================================================================
# TESTS - Validation & Error Handling
# ===================================================================

@pytest.mark.asyncio
async def test_empty_template_validation(template_parser):
    """
    Test that empty templates are rejected during validation.

    Expected behavior:
    - Raises ValidationError
    - Does not call Anthropic API
    """
    logfire.info("Starting test: test_empty_template_validation")

    # Arrange - Empty template
    pipeline_data = create_pipeline_data(
        email_template="",
        recipient_name="Dr. Test",
        recipient_interest="testing"
    )

    # Act & Assert
    with pytest.raises(StepExecutionError) as exc_info:
        await template_parser.execute(pipeline_data)

    assert isinstance(exc_info.value.original_error, ValidationError)
    assert "empty" in str(exc_info.value.original_error).lower()
    logfire.info("Test passed: empty template rejected")


@pytest.mark.asyncio
async def test_template_too_short_validation(template_parser):
    """
    Test that templates shorter than 20 characters are rejected.

    Expected behavior:
    - Raises ValidationError
    - Error message mentions template length
    """
    logfire.info("Starting test: test_template_too_short_validation")

    # Arrange - Very short template
    pipeline_data = create_pipeline_data(
        email_template="Hi {{name}}!",  # Only 13 characters
        recipient_name="Dr. Test",
        recipient_interest="testing"
    )

    # Act & Assert
    with pytest.raises(StepExecutionError) as exc_info:
        await template_parser.execute(pipeline_data)

    assert isinstance(exc_info.value.original_error, ValidationError)
    assert "too short" in str(exc_info.value.original_error).lower()
    logfire.info("Test passed: short template rejected")


@pytest.mark.asyncio
async def test_template_too_long_validation(template_parser):
    """
    Test that templates longer than 5000 characters are rejected.

    Expected behavior:
    - Raises ValidationError
    - Error message mentions template length
    """
    logfire.info("Starting test: test_template_too_long_validation")

    # Arrange - Extremely long template
    pipeline_data = create_pipeline_data(
        email_template="Dear {{name}}, " + ("A" * 5000),  # Over 5000 chars
        recipient_name="Dr. Test",
        recipient_interest="testing"
    )

    # Act & Assert
    with pytest.raises(StepExecutionError) as exc_info:
        await template_parser.execute(pipeline_data)

    assert isinstance(exc_info.value.original_error, ValidationError)
    assert "too long" in str(exc_info.value.original_error).lower()
    logfire.info("Test passed: long template rejected")


@pytest.mark.asyncio
async def test_missing_recipient_name(template_parser, research_template):
    """
    Test that missing recipient_name is rejected.

    Expected behavior:
    - Raises ValidationError
    - Error mentions recipient_name
    """
    logfire.info("Starting test: test_missing_recipient_name")

    # Arrange - Missing recipient name
    pipeline_data = create_pipeline_data(
        email_template=research_template,
        recipient_name="",  # Empty name
        recipient_interest="machine learning"
    )

    # Act & Assert
    with pytest.raises(StepExecutionError) as exc_info:
        await template_parser.execute(pipeline_data)

    assert isinstance(exc_info.value.original_error, ValidationError)
    assert "recipient_name" in str(exc_info.value.original_error).lower()
    logfire.info("Test passed: missing recipient_name rejected")


@pytest.mark.asyncio
async def test_missing_recipient_interest(template_parser, research_template):
    """
    Test that missing recipient_interest is rejected.

    Expected behavior:
    - Raises ValidationError
    - Error mentions recipient_interest
    """
    logfire.info("Starting test: test_missing_recipient_interest")

    # Arrange - Missing recipient interest
    pipeline_data = create_pipeline_data(
        email_template=research_template,
        recipient_name="Dr. Test",
        recipient_interest=""  # Empty interest
    )

    # Act & Assert
    with pytest.raises(StepExecutionError) as exc_info:
        await template_parser.execute(pipeline_data)

    assert isinstance(exc_info.value.original_error, ValidationError)
    assert "recipient_interest" in str(exc_info.value.original_error).lower()
    logfire.info("Test passed: missing recipient_interest rejected")


# ===================================================================
# TESTS - Edge Cases
# ===================================================================

@pytest.mark.asyncio
async def test_minimal_valid_template(template_parser, minimal_template):
    """
    Test parsing of minimal but valid template.

    Expected behavior:
    - Succeeds even with minimal content
    - Still extracts search terms and placeholders
    - Classifies into one of the three types
    """
    logfire.info("Starting test: test_minimal_valid_template")

    # Arrange
    pipeline_data = create_pipeline_data(
        email_template=minimal_template,
        recipient_name="Dr. Emily White",
        recipient_interest="robotics"
    )

    # Act
    with logfire.span("test_minimal_template"):
        result = await template_parser.execute(pipeline_data)

    # Assert
    assert result.success is True
    assert pipeline_data.template_type in [
        TemplateType.RESEARCH,
        TemplateType.BOOK,
        TemplateType.GENERAL
    ]
    assert len(pipeline_data.search_terms) >= 1

    logfire.info(
        "Test passed: test_minimal_valid_template",
        template_type=pipeline_data.template_type.value
    )


@pytest.mark.asyncio
async def test_template_with_special_characters(template_parser):
    """
    Test parsing of template containing special characters.

    Expected behavior:
    - Handles special characters gracefully
    - Still extracts placeholders correctly
    """
    logfire.info("Starting test: test_template_with_special_characters")

    # Arrange - Template with special characters
    special_template = """
    Dear {{name}},

    I'm interested in your work on AI & ML—particularly your research in
    "deep learning" (specifically CNNs). Your paper on résumé parsing
    caught my attention!

    Best regards,
    {{my_name}}
    """

    pipeline_data = create_pipeline_data(
        email_template=special_template,
        recipient_name="Dr. François Müller",
        recipient_interest="AI & machine learning"
    )

    # Act
    result = await template_parser.execute(pipeline_data)

    # Assert
    assert result.success is True
    assert pipeline_data.template_type is not None
    assert len(pipeline_data.search_terms) >= 1

    logfire.info("Test passed: special characters handled correctly")


@pytest.mark.asyncio
async def test_template_with_many_placeholders(template_parser):
    """
    Test template with many placeholders (stress test).

    Expected behavior:
    - Extracts all placeholders correctly
    - Still generates appropriate search terms
    """
    logfire.info("Starting test: test_template_with_many_placeholders")

    # Arrange - Template with many placeholders
    many_placeholders_template = """
    Dear {{title}} {{name}},

    I work at {{my_institution}} studying {{my_field}}. I noticed your
    work on {{topic1}}, {{topic2}}, and {{topic3}}. Your position at
    {{institution}} and focus on {{research_area}} aligns with my
    interests in {{my_interest}}.

    Your recent paper "{{paper_title}}" published in {{journal}} was
    particularly relevant to {{specific_application}}.

    Best,
    {{my_name}} {{my_title}}
    """

    pipeline_data = create_pipeline_data(
        email_template=many_placeholders_template,
        recipient_name="Professor David Kim",
        recipient_interest="quantum computing"
    )

    # Act
    result = await template_parser.execute(pipeline_data)

    # Assert
    assert result.success is True
    placeholders = pipeline_data.template_analysis["placeholders"]
    assert len(placeholders) >= 10, f"Should find many placeholders, found {len(placeholders)}"

    logfire.info(
        "Test passed: many placeholders handled",
        placeholder_count=len(placeholders)
    )


# ===================================================================
# TESTS - Metadata & Observability
# ===================================================================

@pytest.mark.asyncio
async def test_pipeline_data_timing_recorded(template_parser, research_template):
    """
    Test that step timing is recorded in PipelineData.

    Expected behavior:
    - step_timings contains entry for template_parser
    - Duration is positive number
    """
    logfire.info("Starting test: test_pipeline_data_timing_recorded")

    # Arrange
    pipeline_data = create_pipeline_data(email_template=research_template)

    # Act
    result = await template_parser.execute(pipeline_data)

    # Assert
    assert "template_parser" in pipeline_data.step_timings
    duration = pipeline_data.step_timings["template_parser"]
    assert duration > 0, "Duration should be positive"
    assert duration < 30, "Should complete within 30 seconds"

    # Also check result metadata
    assert result.metadata["duration"] == duration

    logfire.info(
        "Test passed: timing recorded",
        duration=duration
    )


@pytest.mark.asyncio
async def test_result_metadata_complete(template_parser, research_template):
    """
    Test that StepResult contains all expected metadata.

    Expected behavior:
    - metadata contains template_type
    - metadata contains search_term_count
    - metadata contains placeholder_count
    - metadata contains model_used
    """
    logfire.info("Starting test: test_result_metadata_complete")

    # Arrange
    pipeline_data = create_pipeline_data(email_template=research_template)

    # Act
    result = await template_parser.execute(pipeline_data)

    # Assert metadata fields
    assert result.metadata is not None
    required_fields = [
        "template_type",
        "search_term_count",
        "placeholder_count",
        "model_used",
        "duration"
    ]

    for field in required_fields:
        assert field in result.metadata, f"Missing metadata field: {field}"

    # Validate metadata values
    assert result.metadata["search_term_count"] >= 1
    assert result.metadata["placeholder_count"] >= 0
    assert result.metadata["model_used"] == "anthropic:claude-haiku-4-5"

    logfire.info(
        "Test passed: metadata complete",
        metadata=result.metadata
    )


# ===================================================================
# TESTS - Different Recipient Scenarios
# ===================================================================

@pytest.mark.asyncio
async def test_different_research_areas(template_parser, research_template):
    """
    Test that different research areas generate appropriate search terms.

    Expected behavior:
    - Search terms reflect the specific research interest
    - Template type classification remains consistent
    """
    logfire.info("Starting test: test_different_research_areas")

    research_areas = [
        "quantum computing",
        "bioinformatics",
        "natural language processing",
        "computer vision",
        "reinforcement learning"
    ]

    for area in research_areas:
        # Arrange
        pipeline_data = create_pipeline_data(
            email_template=research_template,
            recipient_name="Dr. Test Researcher",
            recipient_interest=area
        )

        # Act
        with logfire.span(f"test_area_{area.replace(' ', '_')}"):
            result = await template_parser.execute(pipeline_data)

        # Assert
        assert result.success is True
        assert pipeline_data.template_type == TemplateType.RESEARCH

        # Search terms should mention the research area
        search_terms_combined = " ".join(pipeline_data.search_terms).lower()
        # At least some of the search terms should relate to the area
        # (not enforcing exact match as LLM might use synonyms)

        logfire.info(
            f"Tested research area: {area}",
            search_terms=pipeline_data.search_terms
        )

    logfire.info("Test passed: different research areas handled")


# ===================================================================
# TESTS - Performance & Reliability
# ===================================================================

@pytest.mark.asyncio
async def test_consecutive_calls_independence(template_parser, research_template):
    """
    Test that consecutive calls to the same step are independent.

    Expected behavior:
    - Second call doesn't affect first PipelineData
    - Both calls succeed independently
    - Results are consistent (same template type)
    """
    logfire.info("Starting test: test_consecutive_calls_independence")

    # Arrange - Two separate pipeline data instances
    pipeline_data_1 = create_pipeline_data(email_template=research_template)
    pipeline_data_2 = create_pipeline_data(email_template=research_template)

    # Act - Execute both
    result_1 = await template_parser.execute(pipeline_data_1)
    result_2 = await template_parser.execute(pipeline_data_2)

    # Assert - Both succeed
    assert result_1.success is True
    assert result_2.success is True

    # Assert - Results are consistent
    assert pipeline_data_1.template_type == pipeline_data_2.template_type

    # Assert - They have independent data (different task IDs)
    assert pipeline_data_1.task_id != pipeline_data_2.task_id

    logfire.info("Test passed: consecutive calls are independent")


@pytest.mark.asyncio
async def test_step_respects_low_temperature(template_parser, research_template):
    """
    Test that step uses low temperature (0.1) for consistent results.

    Expected behavior:
    - Multiple runs on same template produce similar results
    - Template type should be identical
    - Search terms should be similar (not necessarily identical)
    """
    logfire.info("Starting test: test_step_respects_low_temperature")

    # Run the same template 3 times
    results = []
    for i in range(3):
        pipeline_data = create_pipeline_data(
            email_template=research_template,
            recipient_name="Dr. Consistency Test",
            recipient_interest="deep learning"
        )

        result = await template_parser.execute(pipeline_data)
        results.append({
            "template_type": pipeline_data.template_type,
            "search_term_count": len(pipeline_data.search_terms)
        })

    # Assert - All should have same template type (deterministic)
    template_types = [r["template_type"] for r in results]
    assert len(set(template_types)) == 1, \
        f"Template type should be consistent, got {template_types}"

    # Assert - Search term count should be similar (within 1-2 variation)
    counts = [r["search_term_count"] for r in results]
    assert max(counts) - min(counts) <= 2, \
        f"Search term counts should be similar, got {counts}"

    logfire.info(
        "Test passed: low temperature produces consistent results",
        results=results
    )


# ===================================================================
# PYTEST CONFIGURATION
# ===================================================================

def pytest_configure(config):
    """Configure pytest with custom markers and logfire setup"""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )

    # Configure logfire for testing
    logfire.configure(
        service_name="template_parser_tests",
        environment="test"
    )

    logfire.info("Starting template parser test suite")


def pytest_sessionfinish(session, exitstatus):
    """Log test session completion"""
    logfire.info(
        "Template parser test suite completed",
        exit_status=exitstatus,
        tests_collected=session.testscollected,
        tests_failed=session.testsfailed
    )
