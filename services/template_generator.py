"""Template generation service using AI."""

import re
import logfire
from pathlib import Path
from config.settings import settings
from utils.llm_agent import run_agent
from utils.pdf_parser import extract_text_from_url

# Load system prompt from markdown file
PROMPT_PATH = Path(__file__).parent / "prompts" / "template_generation.md"


async def generate_template_from_resume(
    pdf_url: str,
    user_instructions: str,
) -> str:
    """Generate email template from resume PDF using AI with user instructions."""
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

**CRITICAL STYLE REQUIREMENTS:**
- Use ONLY commas, periods, and occasional colons for punctuation
- Write exactly how a college student would speak to a professor in person
- Start directly. For example: "Hi Professor [Name], I'm a [year] at [school]..."
- Use contractions naturally (I'm, I'd, I've)
- Keep sentences straightforward and conversational

Generate a cold email template following all guidelines above."""

            # Generate template using AI
            with logfire.span("template_generation.llm_call"):
                logfire.info("Generating template with AI", model=model)
                template_text = await run_agent(
                    prompt=user_prompt,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=0.6,
                    max_tokens=1500,
                    retries=3,
                    timeout=45.0
                )
                logfire.info("Template generated", length=len(template_text))

            # Post-process: Remove em dashes
            with logfire.span("template_generation.post_process"):
                if '—' in template_text:
                    logfire.warn(
                        "Em dash detected in template, applying post-processing",
                        has_em_dash=True
                    )
                    # Replace em dashes with commas
                    template_text = re.sub(r'\s*—\s*', ', ', template_text)
                    logfire.info("Em dashes removed via post-processing")

            return template_text

        except ValueError as e:
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
