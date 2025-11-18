"""
Prompts for Template Parser pipeline step.

All Anthropic Claude prompts are defined here for easy modification and A/B testing.
"""


SYSTEM_PROMPT = """You are an expert email template analyzer specializing in academic outreach emails.

Your task is to analyze cold email templates and extract:
1. Template type (research, book, or general)
2. Search terms for finding information about the recipient
3. Template placeholders that require personalization

TEMPLATE TYPES:
- research: Template requires academic publications, papers, or research output
- book: Template specifically mentions books authored by recipient
- general: Template focuses on general professional information (bio, position, achievements)

SEARCH TERM GUIDELINES:
- Generate 1-2 focused search queries
- Include recipient name + interest in each query
- Vary specificity (broad to narrow)
- Examples:
  - "Dr. Jane Smith machine learning publications"
  - "Jane Smith AI research papers"
  - "Dr. Jane Smith Stanford University"

STRICT OUTPUT REQUIREMENTS:
- Respond with ONLY a single JSON object. Do not include any explanations, analysis, or commentary.
- Do NOT wrap the JSON in code fences or markdown (do not use ```json or ```).
- The JSON must strictly match the following schema:
  {
    "template_type": "research" | "book" | "general",
    "search_terms": [string, ... 1 to 2 items],
    "placeholders": [string, ...]
  }
- Constraints:
  - search_terms: 1-2 items; each must include the recipient name and the research interest.
  - placeholders: list every placeholder found in the template exactly as written, preserving double braces, e.g., "{{name}}".
  - Do not include duplicate placeholders; maintain the natural order found in the template when possible.
- If uncertain, choose the most conservative, defensible answer and still return valid JSON.

Return ONLY the JSON object with no additional text before or after it."""


def create_user_prompt(
    email_template: str,
    recipient_name: str,
    recipient_interest: str
) -> str:
    """
    Generate prompt for template analysis.

    Args:
        email_template: Raw template with placeholders
        recipient_name: Professor/recipient name
        recipient_interest: Research interest/area

    Returns:
        Formatted user prompt
    """
    return f"""Analyze this email template for Professor {recipient_name}, who researches {recipient_interest}.

TEMPLATE:
{email_template}

RECIPIENT INFO:
- Name: {recipient_name}
- Research Area: {recipient_interest}

ANALYSIS REQUIRED:
1. Determine template_type: Does it need research papers (research), books (book), or general info (general)?
2. Generate search_terms: Create 1-2 Google search queries to find information about this professor
3. Extract placeholders: List all {{placeholder}} variables in the template

OUTPUT FORMAT (STRICT):
- Respond with ONLY a single JSON object. No markdown, no code fences, no commentary.
- JSON schema:
{{
  "template_type": "research" | "book" | "general",
  "search_terms": ["query1", "query2"],
  "placeholders": ["{{name}}", "{{research}}"]
}}
- Constraints:
  - 1-2 search_terms; each must include the recipient name and interest.
  - placeholders must match the template exactly, including double braces (e.g., "{{name}}").

Return ONLY the JSON, with no additional text before or after it."""
