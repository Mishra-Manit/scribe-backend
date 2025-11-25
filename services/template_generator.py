"""Template generation service using AI."""

import logfire
from pathlib import Path
from utils.llm_agent import run_agent
from utils.pdf_parser import extract_text_from_url

# Load system prompt from file (co-located with this service)
PROMPT_PATH = Path(__file__).parent / "prompts" / "template_generation.md"


async def generate_template_from_resume(
    pdf_url: str,
    user_instructions: str,
    model: str = "anthropic:claude-haiku-4-5"
) -> str:
    """
    Generate email template from resume PDF and user instructions.

    Args:
        pdf_url: Public URL to resume PDF in Supabase Storage
        user_instructions: User guidance for template generation (tone, style, focus)
        model: AI model identifier (default: Claude Haiku 4.5)

    Returns:
        Generated template text (150-250 words with placeholders)

    Raises:
        ValueError: If PDF parsing fails or text extraction insufficient
        Exception: If LLM generation fails after retries
    """
    with logfire.span("template_generation.generate", pdf_url=pdf_url):
        try:
            # Extract resume text from PDF
            with logfire.span("template_generation.extract_resume"):
                logfire.info("Extracting text from PDF", pdf_url=pdf_url)
                resume_text = await extract_text_from_url(pdf_url)
                logfire.info("PDF text extracted", length=len(resume_text))

            # Load system prompt
            system_prompt = PROMPT_PATH.read_text()

            # Create user prompt with resume and instructions
            user_prompt = f"""**RESUME:**
{resume_text}

**USER INSTRUCTIONS:**
{user_instructions}

Generate a cold email template following the guidelines."""

            # Generate template using AI
            with logfire.span("template_generation.llm_call"):
                logfire.info("Generating template with AI", model=model)
                template_text = await run_agent(
                    prompt=user_prompt,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=0.8,  # Creative writing
                    max_tokens=1500,
                    retries=3,
                    timeout=45.0
                )
                logfire.info("Template generated", length=len(template_text))

            return template_text

        except ValueError as e:
            # PDF parsing errors - propagate as-is
            logfire.error(
                "Template generation failed due to PDF error",
                pdf_url=pdf_url,
                error=str(e),
                exc_info=True
            )
            raise
        except Exception as e:
            # LLM or other errors
            logfire.error(
                "Template generation failed",
                pdf_url=pdf_url,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise
