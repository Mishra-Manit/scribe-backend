"""
End-to-end pipeline test that mimics the frontend request payload.

This test intentionally exercises every pipeline step (template parser,
web scraper, arxiv helper, email composer) using the same data that the
Next.js frontend would send to the FastAPI backend.

Because it requires real external services (Anthropic, Google Custom
Search, Playwright, Supabase/Postgres), it is skipped unless the
`RUN_PIPELINE_E2E_TESTS` environment variable is set to ``"1"``.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest

from database.session import create_session
from models.email import Email
from models.user import User
from pipeline import create_email_pipeline
from pipeline.models.core import PipelineData, TemplateType
from schemas.pipeline import GenerateEmailRequest


RUN_PIPELINE_E2E_TESTS = os.getenv("RUN_PIPELINE_E2E_TESTS") == "1"


def _create_test_user() -> UUID:
    """Insert a temporary user that mimics an authenticated Supabase user."""
    user_id = uuid4()
    session = create_session()
    try:
        session.add(
            User(
                id=user_id,
                email=f"pipeline-e2e+{user_id.hex}@example.com",
                display_name="Pipeline E2E Test User",
            )
        )
        session.commit()
    finally:
        session.close()
    return user_id


def _cleanup_records(user_id: UUID, email_id: UUID | None = None) -> None:
    """Remove any test data created during the run."""
    session = create_session()
    try:
        if email_id:
            session.query(Email).filter(Email.id == email_id).delete()
        if user_id:
            session.query(User).filter(User.id == user_id).delete()
        session.commit()
    finally:
        session.close()


def _request_to_pipeline_data(
    request_payload: GenerateEmailRequest,
    user_id: UUID,
) -> PipelineData:
    """Convert API request payload into PipelineData (mirrors API handler)."""
    return PipelineData(
        task_id=str(uuid4()),
        user_id=str(user_id),
        email_template=request_payload.email_template,
        recipient_name=request_payload.recipient_name,
        recipient_interest=request_payload.recipient_interest,
        template_type=request_payload.template_type,
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.skipif(
    not RUN_PIPELINE_E2E_TESTS,
    reason="Set RUN_PIPELINE_E2E_TESTS=1 to exercise the full pipeline.",
)
async def test_full_pipeline_round_trip_creates_email_record():
    """
    Simulate POST /api/email/generate and ensure the pipeline writes to the DB.
    """
    request_payload = GenerateEmailRequest(
        email_template="""
        Dear {{name}},

        I'm a graduate student focusing on reinforcement learning and your
        recent work on safe exploration caught my attention. I'd love to
        discuss how your techniques could extend to robotic manipulation.

        Best,
        Alex
        """.strip(),
        recipient_name="Dr. Alicia Gomez",
        recipient_interest="safe reinforcement learning and robotics",
        template_type=TemplateType.RESEARCH,
    )

    user_id = _create_test_user()
    pipeline_data = _request_to_pipeline_data(request_payload, user_id)
    runner = create_email_pipeline()

    email_id = None
    try:
        email_id = await runner.run(pipeline_data)

        # Pipeline level assertions
        assert email_id, "Pipeline should return the generated email UUID"
        assert pipeline_data.final_email.strip(), "Final email content should be populated"
        assert pipeline_data.template_analysis, "Template parser should populate analysis data"
        assert pipeline_data.scraped_content, "Web scraper should provide supporting context"
        assert pipeline_data.metadata.get("email_id") == email_id
        assert pipeline_data.composition_metadata.get("email_id") == str(email_id)

        # Database verification
        session = create_session()
        try:
            email_record = (
                session.query(Email)
                .filter(Email.id == email_id, Email.user_id == user_id)
                .first()
            )

            assert email_record is not None, "Email record must be persisted"
            assert email_record.recipient_name == request_payload.recipient_name
            assert (
                email_record.recipient_interest == request_payload.recipient_interest
            )
            assert email_record.email_message == pipeline_data.final_email
        finally:
            session.close()
    finally:
        _cleanup_records(user_id=user_id, email_id=email_id)

