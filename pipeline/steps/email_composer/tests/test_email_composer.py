"""
Test suite for Email Composer Step (Final Pipeline Step)

Tests the final step of the email generation pipeline using:
- Realistic fake data from previous steps (template_parser, web_scraper, arxiv_helper)
- Real Anthropic API calls for email composition
- Real database writes to test full integration
- Extensive logfire observability

Run with:
    pytest pipeline/steps/email_composer/tests/test_email_composer.py -v
    pytest pipeline/steps/email_composer/tests/test_email_composer.py -v -s  # with logs
"""

import pytest
import logfire
from uuid import uuid4, UUID
from datetime import datetime

from pipeline.steps.email_composer.main import EmailComposerStep
from pipeline.models.core import PipelineData, TemplateType
from models.user import User
from database.base import SessionLocal


# ===================================================================
# FIXTURES - Test User Setup
# ===================================================================

@pytest.fixture(scope="function")
async def test_user():
    """
    Create a test user in the database for testing email writes.

    This user will be used to test the full email composition pipeline
    including database writes.

    Cleanup: User and associated emails will be cleaned up after test.
    """
    logfire.info("Creating test user for email composer testing")

    db = SessionLocal()
    test_user_id = uuid4()

    try:
        # Create test user
        user = User(
            id=test_user_id,
            email=f"test-{test_user_id}@example.com",
            display_name="Test User for Email Composer",
            generation_count=0
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        logfire.info(
            "Test user created successfully",
            user_id=str(user.id),
            email=user.email
        )

        # Yield user for test
        yield user

    finally:
        # Cleanup: Delete test user (cascade will delete emails)
        logfire.info("Cleaning up test user", user_id=str(test_user_id))

        try:
            user_to_delete = db.query(User).filter(User.id == test_user_id).first()
            if user_to_delete:
                db.delete(user_to_delete)
                db.commit()
                logfire.info("Test user deleted successfully")
        except Exception as e:
            logfire.error("Error deleting test user", error=str(e))
            db.rollback()
        finally:
            db.close()


@pytest.fixture
def email_composer():
    """Initialize the EmailComposerStep"""
    logfire.info("Initializing EmailComposerStep for testing")
    return EmailComposerStep()


# ===================================================================
# FIXTURES - Realistic Email Template Data
# ===================================================================

@pytest.fixture
def research_email_template():
    """
    Realistic RESEARCH email template with multiple placeholders.

    This template requires:
    - Research papers from ArXiv
    - Web scraping for professor information
    - Template parsing for placeholder extraction
    """
    template = """Dear {{name}},

I am a PhD student at Stanford researching {{my_field}}, and I came across your
groundbreaking work on {{research_area}}. Your recent paper on {{specific_paper_topic}}
has been particularly influential in shaping my understanding of this field.

I was especially intrigued by your approach to {{methodology}}, which aligns closely
with my current research on {{my_specific_topic}}. I believe there could be exciting
opportunities for collaboration, particularly in exploring {{potential_application}}.

I noticed from your lab's website that you're actively working on {{current_project}}.
I would love to discuss how my background in {{my_expertise}} might complement your team's work.

Would you be available for a brief 15-minute call in the coming weeks? I'd be grateful
for any insights you might share about {{specific_question}}.

Thank you for your time and consideration.

Best regards,
{{my_name}}
PhD Candidate, Computer Science
Stanford University"""

    logfire.info(
        "Created research email template",
        placeholder_count=template.count("{{"),
        template_length=len(template)
    )

    return template.strip()


# ===================================================================
# HELPER FUNCTIONS - Fake Data Generation
# ===================================================================

def create_realistic_pipeline_data_research(
    user_id: UUID,
    email_template: str,
    recipient_name: str = "Dr. Sarah Johnson",
    recipient_interest: str = "deep learning and neural architectures"
) -> PipelineData:
    """
    Create a complete PipelineData object simulating successful completion
    of Steps 1-3 (TemplateParser, WebScraper, ArxivHelper).

    This generates realistic fake data that would be produced by:
    - Step 1: Template analysis, type classification, search term extraction
    - Step 2: Web scraping with summarized content and metadata
    - Step 3: ArXiv paper enrichment with relevant publications

    Args:
        user_id: Test user UUID
        email_template: Email template string
        recipient_name: Professor name
        recipient_interest: Research interest/area

    Returns:
        PipelineData ready for EmailComposerStep execution
    """
    task_id = str(uuid4())

    logfire.info(
        "Creating realistic RESEARCH pipeline data",
        task_id=task_id,
        user_id=str(user_id),
        recipient_name=recipient_name
    )

    # Initialize PipelineData with input data
    pipeline_data = PipelineData(
        task_id=task_id,
        user_id=str(user_id),
        email_template=email_template,
        recipient_name=recipient_name,
        recipient_interest=recipient_interest,
        started_at=datetime.utcnow()
    )

    # ===================================================================
    # SIMULATE STEP 1: TemplateParser Output
    # ===================================================================

    logfire.info("Simulating Step 1 (TemplateParser) output")

    pipeline_data.template_type = TemplateType.RESEARCH

    pipeline_data.search_terms = [
        f"{recipient_name} {recipient_interest}",
        f"{recipient_name} publications machine learning",
        f"{recipient_name.split()[-1]} neural networks research"
    ]

    pipeline_data.template_analysis = {
        "placeholders": [
            "{{name}}", "{{my_field}}", "{{research_area}}",
            "{{specific_paper_topic}}", "{{methodology}}",
            "{{my_specific_topic}}", "{{potential_application}}",
            "{{current_project}}", "{{my_expertise}}",
            "{{specific_question}}", "{{my_name}}"
        ],
        "local_placeholders": [
            "{{name}}", "{{my_field}}", "{{research_area}}",
            "{{specific_paper_topic}}", "{{methodology}}"
        ],
        "tone": "academic_professional",
        "formality": "formal",
        "key_topics": [
            "research collaboration",
            "PhD student outreach",
            "neural networks",
            "machine learning methodology"
        ],
        "estimated_replacements": 11
    }

    logfire.info(
        "Step 1 data simulated",
        template_type=pipeline_data.template_type.value,
        search_terms_count=len(pipeline_data.search_terms),
        placeholders_count=len(pipeline_data.template_analysis["placeholders"])
    )

    # ===================================================================
    # SIMULATE STEP 2: WebScraper Output
    # ===================================================================

    logfire.info("Simulating Step 2 (WebScraper) output")

    # Realistic scraped content (summarized from web pages)
    pipeline_data.scraped_content = f"""
Dr. Sarah Johnson is a leading researcher in deep learning and neural network architectures
at the University of Toronto. She holds a faculty position in the Department of Computer
Science and leads the Neural Computing Lab.

RESEARCH FOCUS:
Her primary research interests include transformer architectures, attention mechanisms,
optimization techniques for large language models, and efficient neural network training
methodologies. Dr. Johnson has published extensively in top-tier venues including NeurIPS,
ICML, ICLR, and CVPR.

CURRENT PROJECTS:
The Neural Computing Lab is currently working on several cutting-edge projects:
- Scalable training methods for billion-parameter models
- Novel attention mechanisms that reduce computational complexity
- Theoretical foundations of deep learning optimization
- Applications of neural networks to scientific computing

RECENT ACHIEVEMENTS:
In 2023, Dr. Johnson received the NSERC Discovery Grant for her work on efficient
transformer architectures. Her research group has developed several open-source tools
that are widely used in the machine learning community.

ACADEMIC BACKGROUND:
- PhD in Computer Science, MIT (2018)
- Postdoctoral Fellow, Stanford University (2018-2020)
- Assistant Professor, University of Toronto (2020-present)

TEACHING:
Dr. Johnson teaches graduate-level courses on deep learning, neural networks, and
optimization. She is known for her mentorship of PhD students and has supervised
12 graduate students to completion.

LAB CULTURE:
The Neural Computing Lab emphasizes collaborative research, reproducibility, and
open science. The lab regularly hosts reading groups and workshops on the latest
developments in deep learning.
    """.strip()

    pipeline_data.scraped_urls = [
        "https://www.cs.toronto.edu/~sjohnson/",
        "https://scholar.google.com/citations?user=abc123",
        "https://neural-lab.cs.toronto.edu/",
        "https://www.cs.toronto.edu/~sjohnson/publications.html",
        "https://neural-lab.cs.toronto.edu/people/"
    ]

    # Simulated page contents (raw data before summarization)
    pipeline_data.scraped_page_contents = {
        "https://www.cs.toronto.edu/~sjohnson/": "[Full professor homepage HTML/text content...]",
        "https://scholar.google.com/citations?user=abc123": "[Google Scholar profile content...]",
        "https://neural-lab.cs.toronto.edu/": "[Lab website content with project descriptions...]",
        "https://www.cs.toronto.edu/~sjohnson/publications.html": "[Publication list page content...]",
        "https://neural-lab.cs.toronto.edu/people/": "[Lab members page content...]"
    }

    pipeline_data.scraping_metadata = {
        "total_attempts": 6,
        "successful_scrapes": 5,
        "failed_urls": ["https://www.cs.toronto.edu/~sjohnson/blog/"],
        "success_rate": 0.833,
        "total_content_length": 47500,
        "final_content_length": 1685,
        "was_summarized": True,
        "summarization_method": "playwright + llm",
        "has_uncertainty_markers": False,
        "scraping_duration_seconds": 12.5
    }

    logfire.info(
        "Step 2 data simulated",
        scraped_content_length=len(pipeline_data.scraped_content),
        successful_urls=len(pipeline_data.scraped_urls),
        success_rate=pipeline_data.scraping_metadata["success_rate"]
    )

    # ===================================================================
    # SIMULATE STEP 3: ArxivHelper Output
    # ===================================================================

    logfire.info("Simulating Step 3 (ArxivHelper) output")

    # Realistic ArXiv papers (only for RESEARCH template type)
    pipeline_data.arxiv_papers = [
        {
            "title": "Efficient Attention Mechanisms for Transformer Models: A Comprehensive Study",
            "abstract": "We present a systematic analysis of attention mechanisms in transformer architectures, "
                       "focusing on computational efficiency and scalability. Our work introduces novel sparse "
                       "attention patterns that reduce the quadratic complexity of standard attention to near-linear "
                       "time while maintaining model performance. We demonstrate improvements of up to 3x in training "
                       "speed for models with over 1 billion parameters. Extensive experiments on language modeling, "
                       "machine translation, and image classification tasks validate our approach.",
            "authors": ["Sarah Johnson", "Michael Chen", "Emily Rodriguez"],
            "published_date": "2023-09-15T00:00:00",
            "year": 2023,
            "arxiv_id": "2309.07845",
            "arxiv_url": "https://arxiv.org/abs/2309.07845",
            "pdf_url": "https://arxiv.org/pdf/2309.07845.pdf",
            "primary_category": "cs.LG"
        },
        {
            "title": "Scaling Laws for Neural Language Models: Theory and Practice",
            "abstract": "This paper investigates the relationship between model size, dataset size, and performance "
                       "in neural language models. We derive theoretical scaling laws and validate them empirically "
                       "across models ranging from 100M to 10B parameters. Our findings provide practical guidance "
                       "for allocating computational resources during training and suggest optimal model configurations "
                       "for different compute budgets.",
            "authors": ["Sarah Johnson", "David Park", "Lisa Wang", "James Thompson"],
            "published_date": "2023-06-22T00:00:00",
            "year": 2023,
            "arxiv_id": "2306.11234",
            "arxiv_url": "https://arxiv.org/abs/2306.11234",
            "pdf_url": "https://arxiv.org/pdf/2306.11234.pdf",
            "primary_category": "cs.LG"
        },
        {
            "title": "Gradient Flow Dynamics in Deep Neural Networks: A Theoretical Framework",
            "abstract": "We develop a mathematical framework for analyzing gradient flow in deep neural networks, "
                       "providing insights into training dynamics and convergence properties. Our analysis reveals "
                       "fundamental connections between network depth, initialization schemes, and optimization "
                       "landscapes. We prove convergence guarantees for several popular architectures and propose "
                       "improved initialization methods based on our theoretical findings.",
            "authors": ["Sarah Johnson", "Robert Martinez"],
            "published_date": "2023-03-10T00:00:00",
            "year": 2023,
            "arxiv_id": "2303.05678",
            "arxiv_url": "https://arxiv.org/abs/2303.05678",
            "pdf_url": "https://arxiv.org/pdf/2303.05678.pdf",
            "primary_category": "cs.LG"
        },
        {
            "title": "Memory-Efficient Training of Large Language Models via Gradient Checkpointing",
            "abstract": "Training large language models requires substantial GPU memory, limiting the scale of models "
                       "that can be trained on available hardware. We present an improved gradient checkpointing strategy "
                       "that reduces memory consumption by up to 60% while incurring only a 15% increase in training time. "
                       "Our method is compatible with existing training frameworks and has been successfully applied to "
                       "models with over 100 billion parameters.",
            "authors": ["Michael Chen", "Sarah Johnson", "Alexandra Kim"],
            "published_date": "2022-11-28T00:00:00",
            "year": 2022,
            "arxiv_id": "2211.14567",
            "arxiv_url": "https://arxiv.org/abs/2211.14567",
            "pdf_url": "https://arxiv.org/pdf/2211.14567.pdf",
            "primary_category": "cs.LG"
        }
    ]

    pipeline_data.enrichment_metadata = {
        "papers_found": 4,
        "search_query": "Sarah Johnson",
        "total_papers_retrieved": 7,
        "papers_after_filtering": 4,
        "skipped": False,
        "enrichment_duration_seconds": 3.2,
        "source": "arxiv_api"
    }

    logfire.info(
        "Step 3 data simulated",
        papers_found=len(pipeline_data.arxiv_papers),
        most_recent_paper_year=pipeline_data.arxiv_papers[0]["year"]
    )

    # ===================================================================
    # ADD SIMULATED STEP TIMINGS
    # ===================================================================

    pipeline_data.step_timings = {
        "template_parser": 2.3,
        "web_scraper": 12.5,
        "arxiv_helper": 3.2
    }

    logfire.info(
        "Realistic RESEARCH pipeline data created successfully",
        total_steps_simulated=3,
        total_time_so_far=sum(pipeline_data.step_timings.values()),
        ready_for_email_composer=True
    )

    return pipeline_data


# ===================================================================
# TESTS - Email Composer Integration
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_email_composer_research_template_full_pipeline(
    email_composer,
    research_email_template,
    test_user
):
    """
    Full integration test for EmailComposer step with RESEARCH template.

    This test simulates the complete pipeline by:
    1. Creating realistic fake data from Steps 1-3 (TemplateParser, WebScraper, ArxivHelper)
    2. Running the actual EmailComposer step with real Anthropic API calls
    3. Verifying database writes and user generation count updates
    4. Validating the final composed email meets quality standards

    Expected behavior:
    - Returns success=True
    - Generates a complete, personalized email
    - Writes email to database successfully
    - Sets email_id in metadata
    - Updates user generation count
    - Includes all required metadata

    This test makes REAL API calls and REAL database writes.
    """
    with logfire.span("test_email_composer_research_full_pipeline"):

        logfire.info(
            "Starting full integration test for EmailComposer",
            test_user_id=str(test_user.id),
            test_user_email=test_user.email
        )

        # ===================================================================
        # ARRANGE: Create realistic pipeline data
        # ===================================================================

        logfire.info("📋 ARRANGE: Creating realistic pipeline data from Steps 1-3")

        pipeline_data = create_realistic_pipeline_data_research(
            user_id=test_user.id,
            email_template=research_email_template,
            recipient_name="Dr. Sarah Johnson",
            recipient_interest="deep learning and neural architectures"
        )

        # Log the complete pipeline state before email composition
        logfire.info(
            "Pipeline data ready for EmailComposer",
            template_type=pipeline_data.template_type.value,
            search_terms=pipeline_data.search_terms,
            scraped_content_length=len(pipeline_data.scraped_content),
            arxiv_papers_count=len(pipeline_data.arxiv_papers),
            placeholders_count=len(pipeline_data.template_analysis["placeholders"]),
            elapsed_time_seconds=sum(pipeline_data.step_timings.values())
        )

        # ===================================================================
        # ACT: Execute EmailComposer step (REAL API CALL)
        # ===================================================================

        logfire.info("🚀 ACT: Executing EmailComposer step with REAL Anthropic API call")

        with logfire.span("email_composer_execution"):
            result = await email_composer.execute(pipeline_data)

        logfire.info(
            "EmailComposer execution completed",
            success=result.success,
            error=result.error,
            step_name=result.step_name
        )

        # ===================================================================
        # ASSERT: Validate step execution results
        # ===================================================================

        logfire.info("✅ ASSERT: Validating EmailComposer output")

        # Basic success validation
        assert result.success is True, f"EmailComposer should succeed: {result.error}"
        assert result.step_name == "email_composer"
        assert result.error is None

        logfire.info("✓ Step execution successful")

        # Validate final email was generated
        assert pipeline_data.final_email, "final_email should be populated"
        assert len(pipeline_data.final_email) > 100, "Email should be substantial (>100 chars)"

        email_word_count = len(pipeline_data.final_email.split())
        assert email_word_count > 50, f"Email should have >50 words, got {email_word_count}"

        logfire.info(
            "✓ Final email generated successfully",
            email_length=len(pipeline_data.final_email),
            word_count=email_word_count,
            line_count=pipeline_data.final_email.count('\n')
        )

        # Validate composition metadata
        assert pipeline_data.composition_metadata, "composition_metadata should be populated"
        assert "email_id" in pipeline_data.composition_metadata
        assert "word_count" in pipeline_data.composition_metadata
        assert "model" in pipeline_data.composition_metadata
        assert "temperature" in pipeline_data.composition_metadata

        logfire.info(
            "✓ Composition metadata validated",
            metadata=pipeline_data.composition_metadata
        )

        # Validate email_id in metadata (CRITICAL for PipelineRunner)
        assert "email_id" in pipeline_data.metadata, "email_id must be in metadata"
        email_id = pipeline_data.metadata["email_id"]
        assert email_id is not None

        logfire.info(
            "✓ Email ID set in metadata (critical for pipeline tracking)",
            email_id=str(email_id)
        )

        # Validate result metadata
        assert result.metadata is not None
        assert "email_id" in result.metadata
        assert "word_count" in result.metadata

        logfire.info(
            "✓ Result metadata validated",
            result_metadata=result.metadata
        )

        # ===================================================================
        # ASSERT: Validate database writes
        # ===================================================================

        logfire.info("🗄️ Validating database writes")

        # Query database to verify email was written
        from models.email import Email
        db = SessionLocal()

        try:
            email_record = db.query(Email).filter(Email.id == email_id).first()

            assert email_record is not None, "Email should be in database"
            assert str(email_record.user_id) == str(test_user.id)
            assert email_record.recipient_name == "Dr. Sarah Johnson"
            assert email_record.recipient_interest == "deep learning and neural architectures"
            assert email_record.email_message == pipeline_data.final_email
            assert email_record.template_type == TemplateType.RESEARCH

            logfire.info(
                "✓ Email written to database successfully",
                email_id=str(email_record.id),
                user_id=str(email_record.user_id),
                recipient_name=email_record.recipient_name,
                created_at=email_record.created_at.isoformat()
            )

            # Validate user generation count was incremented
            db.refresh(test_user)
            assert test_user.generation_count >= 1, "User generation count should be incremented"

            logfire.info(
                "✓ User generation count incremented",
                user_id=str(test_user.id),
                generation_count=test_user.generation_count
            )

        finally:
            db.close()
        # ===================================================================
        # LOG FINAL EMAIL FOR MANUAL INSPECTION
        # ===================================================================

        logfire.info(
            "📬 FINAL COMPOSED EMAIL",
            email_content=pipeline_data.final_email,
            recipient="Dr. Sarah Johnson",
            template_type="RESEARCH",
            total_pipeline_duration=sum(pipeline_data.step_timings.values())
        )

        logfire.info(
            "✅ TEST PASSED: EmailComposer full integration test successful",
            email_id=str(email_id),
            word_count=email_word_count,
            database_write_verified=True,
            user_count_updated=True
        )
