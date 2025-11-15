"""
Prompts for Web Scraper content summarization.
"""

from pipeline.models.core import TemplateType


SUMMARIZATION_SYSTEM_PROMPT = """You are an expert academic information extractor.

Your task is to analyze scraped web content about a professor and create a concise, accurate summary of their:
- Research publications and papers
- Current position and affiliation
- Research interests and areas of expertise
- Academic achievements and recognition

GUIDELINES:
- Be factual and precise
- Only include information explicitly stated in the source
- Prioritize recent and relevant information
- Extract specific publication titles when available
- Keep the summary focused and concise (max 5000 characters)

OUTPUT FORMAT:
Provide a structured summary with these sections:
1. KEY PUBLICATIONS: List specific paper/publication titles
2. RESEARCH AREAS: Main research interests and focus areas
3. ACADEMIC POSITION: Current role, department, institution
4. NOTABLE ACHIEVEMENTS: Awards, honors, recognition

If information for a section is not found, state "Not found in source."
"""


def create_summarization_prompt(
    scraped_content: str,
    recipient_name: str,
    recipient_interest: str,
    template_type: TemplateType
) -> str:
    """
    Create prompt for content summarization.

    Args:
        scraped_content: Combined scraped content
        recipient_name: Professor name
        recipient_interest: Research area
        template_type: Type of template (RESEARCH, BOOK, or GENERAL)

    Returns:
        Formatted prompt
    """
    emphasis = ""
    if template_type == TemplateType.RESEARCH:
        emphasis = f"""

CRITICAL: This template REQUIRES specific publication titles.
Make extra effort to identify and list actual paper/publication titles authored by {recipient_name}.
Verify authorship before listing - only include publications where {recipient_name} is explicitly mentioned as an author.
        """

    return f"""Analyze the following scraped web content about Professor {recipient_name}, who researches {recipient_interest}.

{emphasis}

SCRAPED CONTENT:
{scraped_content[:30000]}

Create a focused summary (max 5000 characters) highlighting:
1. Specific publication titles (with full names)
2. Research areas and interests
3. Current academic position
4. Notable achievements

Be concise but comprehensive. Prioritize information useful for a personalized cold email."""
