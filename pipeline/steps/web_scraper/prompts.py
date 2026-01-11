"""Query templates for Exa Search API.

Dual-query strategy:
1. Background: General professor info (position, institution, career)
2. Publications: Deep dive into recent publications and works
"""

from pipeline.models.core import TemplateType


# Background query (shared across all template types)
BACKGROUND_QUERY = """
Find general background information about Professor {recipient_name} in {recipient_interest}.

Focus on: current position and institution, career history, research expertise,
awards and recognition, professional affiliations. Give a comprehensive, in-depth 
overview of the professor's career and what they are currently working on.

DO NOT include publications, papers, or books.
"""

# Publications queries by template type
PUBLICATIONS_QUERIES = {
    TemplateType.RESEARCH: """
Find ONLY recent research publications by Professor {recipient_name} in {recipient_interest}.

Focus on: recent papers (last 3-5 years), specific titles and venues, key findings,
collaborators, research methodologies.

DO NOT include biographical information.
""",
    TemplateType.BOOK: """
Find ONLY books and major publications by Professor {recipient_name} in {recipient_interest}.

Focus on: books authored or edited, specific titles and publishers, textbooks,
book chapters, key themes.

DO NOT include biographical information.
""",
    TemplateType.GENERAL: """
Find notable publications by Professor {recipient_name} in {recipient_interest}.

Focus on: most cited publications, recent papers/books (last 3-5 years),
specific titles and venues, key contributions.

DO NOT include biographical information.
"""
}


def build_background_query(recipient_name: str, recipient_interest: str) -> str:
    """Build query for general professor background."""
    return BACKGROUND_QUERY.format(
        recipient_name=recipient_name,
        recipient_interest=recipient_interest
    ).strip()


def build_publications_query(
    recipient_name: str,
    recipient_interest: str,
    template_type: TemplateType
) -> str:
    """Build query for publications research based on template type."""
    template = PUBLICATIONS_QUERIES.get(template_type, PUBLICATIONS_QUERIES[TemplateType.GENERAL])
    return template.format(
        recipient_name=recipient_name,
        recipient_interest=recipient_interest
    ).strip()
