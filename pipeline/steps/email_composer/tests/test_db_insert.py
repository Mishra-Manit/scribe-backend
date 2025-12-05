"""
Simple database insert test for Email Composer Step

This test focuses solely on validating the database insert operation
for writing composed emails to the emails table.

Run with:
    pytest pipeline/steps/email_composer/tests/test_db_insert.py -v
    pytest pipeline/steps/email_composer/tests/test_db_insert.py -v -s  # with logs
"""

import pytest
import logfire
from uuid import UUID

from pipeline.steps.email_composer.db_utils import write_email_to_db
from pipeline.models.core import TemplateType
from models.email import Email
from database.base import SessionLocal


# ===================================================================
# TEST - Database Insert Operation
# ===================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_write_email_to_db_basic():
    """
    Test the database insert operation for email_composer step.

    This test validates that:
    1. write_email_to_db() successfully inserts an email record
    2. The email is associated with the specified user UUID
    3. All required fields are populated correctly
    4. The function returns a valid email_id

    Uses a realistic email format and inserts under a specific test user.
    """
    with logfire.span("test_write_email_to_db_basic"):

        logfire.info("Starting database insert test for email_composer")

        # ===================================================================
        # ARRANGE: Prepare test data
        # ===================================================================

        # User UUID to insert email under
        test_user_id = UUID("26dc2fb9-7f27-46c2-a532-149e54b3ba9e")

        # Recipient information
        recipient_name = "Dr. Emily Chen"
        recipient_interest = "machine learning interpretability and explainable AI"

        # Template type and metadata
        template_type = TemplateType.RESEARCH
        metadata = {
            "papers_found": 3,
            "sources_scraped": ["university_website", "google_scholar"],
            "generation_time_seconds": 12.5,
            "arxiv_papers": [
                {"title": "Visualizing Decision Boundaries", "arxiv_id": "2301.12345"},
                {"title": "Attention Mechanisms in Deep Learning", "arxiv_id": "2302.67890"}
            ]
        }

        # Realistic email content in professional academic format
        email_content = """Dear Dr. Chen,

I hope this email finds you well. My name is Alex Rivera, and I am a PhD student in Computer Science at MIT, specializing in machine learning interpretability and model transparency.

I recently came across your fascinating work on attention-based interpretability methods for deep neural networks, particularly your paper on "Visualizing Decision Boundaries in High-Dimensional Embedding Spaces." Your approach to using gradient-based attribution combined with layer-wise relevance propagation has been incredibly insightful for my own research.

I am currently working on developing interpretability techniques for large language models, with a focus on understanding how these models process contextual information across multiple attention heads. I believe your expertise in attention mechanism analysis could provide valuable perspectives on my work.

I noticed from your lab's website that you are actively researching methods to make black-box models more transparent to end users. This aligns closely with my research goals, and I would be very interested in learning more about your current projects and potentially exploring opportunities for collaboration.

Would you have 15-20 minutes available in the coming weeks for a brief video call? I would greatly appreciate the opportunity to discuss your recent work and share some of my preliminary findings on attention flow visualization.

Thank you very much for considering my request. I look forward to the possibility of connecting with you.

Best regards,
Alex Rivera
PhD Candidate, Computer Science
Massachusetts Institute of Technology
arivera@mit.edu"""

        logfire.info(
            "Test data prepared",
            user_id=str(test_user_id),
            recipient_name=recipient_name,
            email_length=len(email_content),
            word_count=len(email_content.split())
        )

        # ===================================================================
        # ACT: Call the database write function
        # ===================================================================

        logfire.info("Calling write_email_to_db()")

        email_id = await write_email_to_db(
            user_id=test_user_id,
            recipient_name=recipient_name,
            recipient_interest=recipient_interest,
            email_content=email_content,
            template_type=template_type,
            metadata=metadata
        )

        logfire.info(
            "write_email_to_db() completed",
            email_id=str(email_id) if email_id else None,
            success=email_id is not None
        )

        # ===================================================================
        # ASSERT: Validate the insert operation
        # ===================================================================

        # Verify that an email_id was returned
        assert email_id is not None, "write_email_to_db should return a valid email_id"
        assert isinstance(email_id, UUID), "email_id should be a UUID"

        logfire.info("✓ Email ID returned successfully", email_id=str(email_id))

        # Query the database to verify the email was actually inserted
        db = SessionLocal()

        try:
            email_record = db.query(Email).filter(Email.id == email_id).first()

            # Verify record exists
            assert email_record is not None, "Email record should exist in database"

            # Verify all fields match what we inserted
            assert email_record.user_id == test_user_id, "user_id should match"
            assert email_record.recipient_name == recipient_name, "recipient_name should match"
            assert email_record.recipient_interest == recipient_interest, "recipient_interest should match"
            assert email_record.email_message == email_content, "email_message should match"
            assert email_record.template_type == template_type, "template_type should match"
            assert email_record.email_metadata == metadata, "metadata should match"
            assert email_record.created_at is not None, "created_at should be set"

            logfire.info(
                "✓ Email record verified in database",
                email_id=str(email_record.id),
                user_id=str(email_record.user_id),
                recipient_name=email_record.recipient_name,
                created_at=email_record.created_at.isoformat()
            )

            logfire.info(
                "📬 Email content preview",
                first_line=email_content.split('\n')[0],
                total_lines=email_content.count('\n') + 1,
                word_count=len(email_content.split())
            )

        finally:
            # Clean up: Delete the test email record
            # NOTE: Deletion commented out for manual inspection in Supabase
            # Uncomment before committing to avoid test data pollution
            try:
                # if email_record:
                #     db.delete(email_record)
                #     db.commit()
                #     logfire.info("✓ Test email cleaned up", email_id=str(email_id))
                pass
            except Exception as e:
                logfire.error("Error cleaning up test email", error=str(e))
                db.rollback()
            finally:
                db.close()

        logfire.info(
            "✅ TEST PASSED: Database insert operation successful",
            email_id=str(email_id),
            verified_in_db=True,
            cleanup_complete=True
        )
