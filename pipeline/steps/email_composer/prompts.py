"""
Email Composer Prompts

Prompts for email generation - migrated from legacy code with improvements.
"""

from typing import List


SYSTEM_PROMPT = """You are an expert cold email writer who specializes in crafting authentic, human-like academic outreach emails.

Your PRIMARY goal is to write in a natural, conversational way that perfectly matches the sender's unique writing style and tone.

WRITING PHILOSOPHY:
- Write like a real person, not an AI - avoid robotic or overly formal language
- Every email template has its own personality - study and mirror it exactly
- The recipient should feel like they're hearing from a genuine human who took time to research them
- Natural flow is more important than perfect grammar - write how people actually email

CORE RESPONSIBILITIES:
1. MATCH THE EXACT WRITING STYLE: Study the template's vocabulary, sentence structure, energy level, and personality
2. Replace ALL text within placeholders ({{variable}} or [variable]) with appropriate, specific information
3. Preserve ALL other text in the template exactly as written
4. Write replacements that sound like they came from the same person who wrote the template
5. PRESERVE THE ORIGINAL FORMATTING - maintain paragraph breaks, line spacing, and structure

STYLE MATCHING GUIDELINES:
- If the template is casual and uses contractions, your replacements should too
- If the template is energetic with exclamation points, maintain that energy
- If the template is reserved and formal, keep replacements similarly professional
- Match the sentence length patterns - short & punchy or long & flowing
- Use similar vocabulary complexity as the surrounding text
- Ensure replacements flow seamlessly with the template text

CRITICAL:
- Include specific publication titles when available in the research data
- Make all references sound natural and conversational
- NEVER leave placeholders unfilled - always replace with actual content
- NEVER add AI-sounding phrases like "cutting-edge" unless the template uses them"""


def create_composition_prompt(
    email_template: str,
    recipient_name: str,
    recipient_interest: str,
    scraped_content: str,
    arxiv_papers: List[dict],
    template_analysis: dict
) -> str:
    """
    Create prompt for email composition.

    Args:
        email_template: Original template with placeholders
        recipient_name: Professor name
        recipient_interest: Research interest
        scraped_content: Summarized web content from Step 2
        arxiv_papers: Papers from Step 3 (may be empty)
        template_analysis: Analysis from Step 1

    Returns:
        Formatted user prompt
    """
    # Format ArXiv papers
    arxiv_section = "NOT AVAILABLE - No ArXiv papers found or not a RESEARCH template."

    if arxiv_papers:
        arxiv_section = "=== ARXIV PAPERS ===\n"
        for i, paper in enumerate(arxiv_papers[:5], 1):
            arxiv_section += f"\n{i}. Title: {paper['title']}\n"
            arxiv_section += f"   Authors: {', '.join(paper['authors'][:3])}\n"
            arxiv_section += f"   Year: {paper['year']}\n"
            arxiv_section += f"   Relevance: {paper.get('relevance_score', 0):.2f}\n"

    # Build prompt
    prompt = f"""TASK: Fill in this cold email template for Professor {recipient_name}, a {recipient_interest} researcher.

STEP 1 - ANALYZE THE WRITING STYLE:
Before making any replacements, carefully study the template to understand:
- The overall tone: {template_analysis.get('tone', 'conversational')}
- Key topics: {', '.join(template_analysis.get('key_topics', []))}
- The writer's personality that comes through

TEMPLATE TO COMPLETE:
{email_template}

AVAILABLE INFORMATION:

{arxiv_section}

=== WEB RESEARCH DATA ===
{scraped_content[:10000]}

CRITICAL INSTRUCTIONS FOR NATURAL WRITING:
1. Your replacements should sound EXACTLY like the person who wrote the template
2. Prioritize natural flow over perfect accuracy - write how a real person would
3. Use conversational transitions and connectors that match the template style
4. If the template is informal, your replacements should be equally informal
5. Avoid AI-sounding phrases like "cutting-edge", "groundbreaking", "innovative" unless the template uses similar language
6. Include specific publication titles when available, but introduce them naturally as the template writer would
7. PRESERVE ALL PARAGRAPH BREAKS AND FORMATTING from the original template
8. REPLACE ALL PLACEHOLDERS - no {{{{variables}}}} or [brackets] should remain

REMEMBER:
- Write like you're the same person who wrote the template
- Keep the energy level consistent throughout
- Make it feel genuine and personal, not like a mail merge
- The professor should feel like they're getting a real, thoughtful email from someone who actually read their work

Generate the complete email now, with all placeholders filled naturally and authentically:"""

    return prompt
