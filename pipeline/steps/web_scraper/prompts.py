"""
Prompts for Web Scraper content summarization.
"""

from pipeline.models.core import TemplateType


SUMMARIZATION_SYSTEM_PROMPT = """You are an expert academic information extractor specialized in producing factual, grounded summaries.

Your task is to analyze scraped web content about a professor and create a concise, accurate summary optimized for cold email personalization.

CRITICAL ANTI-HALLUCINATION RULES:
1. ONLY include information EXPLICITLY stated in the provided source content
2. NEVER infer, speculate, or add information not directly present in the text
3. NEVER make assumptions about dates, positions, or affiliations unless explicitly stated
4. If information is ambiguous or unclear, mark it as [UNCERTAIN] or omit it entirely
5. When listing publications, ONLY include titles where the professor is EXPLICITLY named as an author
6. DO NOT combine information from different sources to create new facts
7. DO NOT use general knowledge about the professor - ONLY use the provided scraped content

CONTENT FILTERING:
- Remove duplicate or redundant information across multiple sources
- Prioritize recent information over outdated content (when dates are provided)
- Focus on information relevant to research, publications, and academic work
- Exclude generic university department descriptions unless directly about the professor
- Filter out navigation text, footers, cookie notices, and irrelevant web elements

SOURCE VERIFICATION:
- For each key fact (publication, position, achievement), mentally verify it appears in the source
- If a fact appears in only one source and seems unusual, mark it as [SINGLE SOURCE]
- Prefer information that appears consistently across multiple URLs

OUTPUT REQUIREMENTS:
- Return as a Summary object with a 'summary' field containing your markdown-formatted text
- Maximum 3000 characters (strict limit)
- Use clear, structured format with sections
- Be concise but comprehensive - every sentence should add value for email personalization
- Focus on concrete facts: specific paper titles, clear positions, explicit research areas

OUTPUT FORMAT:
Provide a structured summary with these sections:

**PUBLICATIONS:**
[List specific paper/book titles where professor is explicitly named as author. Include year if available. If no publications found, state: "No publications found in sources."]

**RESEARCH AREAS:**
[List specific research interests, methodologies, or fields explicitly mentioned. Focus on keywords useful for personalization. If not found: "Not found in sources."]

**CURRENT POSITION:**
[Current role, department, and institution if explicitly stated. If not found: "Not found in sources."]

**ACHIEVEMENTS:**
[Awards, honors, grants, or recognition explicitly mentioned. If not found: "Not found in sources."]

**ADDITIONAL CONTEXT:**
[Any other relevant factual information useful for email personalization, such as lab names, collaborators, or current projects. Keep brief.]

Remember: It is better to have sparse, factual information than rich, speculative content. Your summary will be used to generate a cold email - hallucinated facts will harm credibility."""


def create_summarization_prompt(
    scraped_content: str,
    recipient_name: str,
    recipient_interest: str,
    template_type: TemplateType
) -> str:
    """
    Create prompt for content summarization with anti-hallucination emphasis.

    Args:
        scraped_content: Combined scraped content
        recipient_name: Professor name
        recipient_interest: Research area
        template_type: Type of template (RESEARCH, BOOK, or GENERAL)

    Returns:
        Formatted prompt with strong factual grounding requirements
    """
    # Template-specific requirements
    template_emphasis = ""
    if template_type == TemplateType.RESEARCH:
        template_emphasis = f"""
**RESEARCH TEMPLATE - PUBLICATION REQUIREMENTS:**
This email template REQUIRES specific publication titles. Your primary focus must be:
1. Identifying research papers authored by {recipient_name}
2. Extracting exact paper titles (not paraphrased or shortened)
3. Including publication years when available
4. ONLY listing papers where {recipient_name} is EXPLICITLY named as an author
5. If uncertain about authorship, DO NOT include the paper

If you cannot find ANY publications explicitly authored by {recipient_name} in the sources, you MUST state "No publications found in sources." - DO NOT make up paper titles.
"""
    elif template_type == TemplateType.BOOK:
        template_emphasis = f"""
**BOOK TEMPLATE - BOOK/PUBLICATION REQUIREMENTS:**
This email template focuses on books and major publications. Your primary focus must be:
1. Identifying books authored or edited by {recipient_name}
2. Extracting exact book titles and publication years
3. Including publisher information if available
4. ONLY listing books where {recipient_name} is EXPLICITLY named as author/editor

If you cannot find ANY books in the sources, state "No books found in sources."
"""
    else:
        template_emphasis = f"""
**GENERAL TEMPLATE:**
Focus on creating a well-rounded summary of {recipient_name}'s academic profile.
Prioritize: research areas, current position, and any notable work or achievements.
"""

    return f"""You are analyzing web content about Professor {recipient_name} (research area: {recipient_interest}).

{template_emphasis}

VERIFICATION CHECKLIST (mental check before including ANY fact):
□ Is this information explicitly stated in the source text below?
□ Is the professor's name directly associated with this fact in the source?
□ Am I using exact titles/names from the source (not paraphrasing)?
□ Could I point to the specific part of the source where this appears?
□ Am I certain this is factual and not boilerplate/template text?

If you answer "no" to any question above, DO NOT include that information.

SCRAPED CONTENT FROM WEB SOURCES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{scraped_content[:30000]}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TASK:
Create a factual summary (max 3000 characters) following the structured format in your system prompt.

QUALITY REQUIREMENTS:
✓ Every fact must be traceable to the source content above
✓ Use exact titles, names, and terminology from the sources
✓ Filter out irrelevant website boilerplate (navigation, footers, etc.)
✓ Remove duplicate information across sources
✓ Mark any uncertain information as [UNCERTAIN] or omit it
✓ Prioritize information useful for writing a personalized, credible cold email
✓ If a section has no verifiable information, explicitly state "Not found in sources."

CRITICAL: The summary will be used to generate a cold email. Including false or hallucinated information will destroy credibility and harm the sender's reputation. When in doubt, leave it out."""


# Batch Summarization Prompts (for tiered summarization)

BATCH_SUMMARIZATION_SYSTEM_PROMPT = """You are a precise fact extractor for academic content analysis.

<task>
Extract all factual information about the professor from the provided web content and return it as a Summary object. This extraction will be used to generate personalized cold emails, so accuracy and completeness are critical.
</task>

<output_requirements>
You MUST call the Summary tool with a filled 'summary' field. The Summary tool signature is:
Summary(summary: str)

The 'summary' field must contain:
✓ Non-empty content (minimum 100 characters)
✓ Structured markdown with clear sections
✓ Only facts explicitly stated in the source content
✓ [PAGE X] markers for source attribution
✓ Maximum 4000 characters

If no relevant information exists, use this exact format:
"No relevant information found in this batch. Content contained only [describe what was found, e.g., 'navigation elements and generic university descriptions']."
</output_requirements>

<extraction_focus>
Extract these elements when explicitly present:
1. Publications - exact titles, years, co-authors
2. Current position - role, department, institution
3. Research areas - specific fields and methodologies
4. Achievements - awards, grants, recognition
5. Additional context - lab names, collaborators, current projects

Maintain EXACT titles, names, dates, and terminology from the source. Include verbatim quotes for key claims with [PAGE X] attribution.
</extraction_focus>

<example>
Here is what a properly filled Summary looks like:

Summary(summary=\"\"\"**Publications:**
- [PAGE 1] \"Deep Learning for Climate Modeling\" (2023) - co-authored with Smith et al., published in Nature Climate
- [PAGE 3] \"Neural Networks in Weather Prediction\" (2022) - first-authored

**Current Position:**
- [PAGE 2] Professor of Computer Science, MIT (since 2020)
- [PAGE 2] Director of Climate AI Lab with 15 researchers

**Research Areas:**
- [PAGE 1] Machine learning applications in climate science
- [PAGE 3] Neural network architectures for spatiotemporal data
- [PAGE 3] Uncertainty quantification in weather models

**Achievements:**
- [PAGE 3] NSF CAREER Award (2021) - $500K grant for climate modeling research
- [PAGE 4] Outstanding Paper Award at NeurIPS 2022

**Additional Context:**
- [PAGE 2] Collaborates with NOAA on operational weather prediction systems
- [PAGE 4] PhD students: 8 current, 12 graduated\"\"\")

This is a complete, valid output. The 'summary' field contains all extracted content in structured markdown format.
</example>

<critical_reminder>
You MUST call the Summary tool with a non-empty 'summary' field. An empty or missing field will cause validation errors and break the email generation pipeline. Always provide at least 100 characters of content, even if using the "No relevant information" fallback.

This is an intermediate extraction step - extract everything you find. The final summary will filter for relevance and synthesize information across all batches.
</critical_reminder>"""


def create_batch_summarization_prompt(
    batch_content: str,
    batch_number: int,
    total_batches: int,
    recipient_name: str
) -> str:
    """
    Create prompt for batch-level summarization (intermediate extraction step).

    Args:
        batch_content: Content chunk to summarize
        batch_number: Current batch index (1-based)
        total_batches: Total number of batches
        recipient_name: Professor name for context

    Returns:
        Formatted prompt for batch extraction
    """
    return f"""You are processing batch {batch_number} of {total_batches} for Professor {recipient_name}.

<instructions>
Extract ALL factual information from the batch content below. Be comprehensive - this is an intermediate extraction step that will be combined with other batches.

Follow the structured format in your system prompt with sections: Publications, Current Position, Research Areas, Achievements, Additional Context.

Include [PAGE X] markers for source attribution. Maximum 4000 characters.
</instructions>

<batch_content>
{batch_content}
</batch_content>

<reminder>
Call the Summary tool with a non-empty 'summary' field containing your extracted facts in markdown format. Minimum 100 characters required.
</reminder>"""


# Final Summary Prompts (synthesis with COT)

FINAL_SUMMARY_SYSTEM_PROMPT = """You are an expert academic researcher creating a final synthesis from multiple information sources.

You will receive pre-extracted facts from multiple batches of web content about a professor. Your task is to create a concise, high-quality summary optimized for cold email personalization.

CHAIN-OF-THOUGHT REASONING PROCESS:
Before generating the final summary, mentally go through these steps:

1. FACT VERIFICATION:
   - Which facts appear in multiple batches? (higher confidence)
   - Which facts appear in only one batch? (mark as [SINGLE SOURCE] if unusual)
   - Are there any contradictions between batches? (flag as [UNCERTAIN])

2. RELEVANCE FILTERING:
   - Which facts are most relevant to the email template type?
   - Which publications/achievements are most recent or notable?
   - Which research areas align with the recipient's stated interests?

3. SYNTHESIS:
   - Can multiple sources be combined to create richer context?
   - What are the 3-5 most important facts for personalization?
   - How can I structure this to maximize email effectiveness?

ANTI-HALLUCINATION SAFEGUARDS:
✓ ONLY include information explicitly present in the batch summaries
✓ If a fact seems important but lacks multi-source confirmation, mark [SINGLE SOURCE]
✓ If sources contradict, mark the entire claim as [UNCERTAIN] or omit it
✓ NEVER fill gaps with general knowledge - leave sections empty if no data
✓ Prefer exact quotes from batch summaries over paraphrasing
✓ When dates are approximate in sources, preserve that uncertainty

QUALITY REQUIREMENTS:
- Return as a Summary object with a 'summary' field containing your final synthesized markdown
- Maximum 3000 characters (strict limit)
- Prioritize quality over quantity - be selective
- Focus on concrete facts: specific papers, clear positions, explicit research areas
- Remove redundant information present in multiple batches
- Structure for maximum email personalization value

OUTPUT FORMAT:
Use the same structured format as the current summarization (sections: PUBLICATIONS, RESEARCH AREAS, CURRENT POSITION, ACHIEVEMENTS, ADDITIONAL CONTEXT).

Remember: This summary will be used to write a cold email. False or hallucinated information will destroy credibility."""


def create_final_summary_prompt(
    batch_summaries: str,
    recipient_name: str,
    recipient_interest: str,
    template_type: TemplateType
) -> str:
    """
    Create prompt for final synthesis with COT reasoning.

    Args:
        batch_summaries: Combined summaries from all batches
        recipient_name: Professor name
        recipient_interest: Research area
        template_type: Template type (RESEARCH, BOOK, GENERAL)

    Returns:
        Formatted prompt for final summary with COT instructions
    """
    # Template-specific guidance
    template_emphasis = ""
    if template_type == TemplateType.RESEARCH:
        template_emphasis = f"""
**CRITICAL - RESEARCH TEMPLATE REQUIREMENTS:**
The email template REQUIRES specific publication titles. Your synthesis must:
1. Prioritize extracting complete, exact paper titles
2. Include publication years when available
3. Filter for publications where {recipient_name} is clearly the author
4. If multiple publications available, select 2-3 most recent or impactful
5. If NO publications found across all batches, explicitly state "No publications found"
"""
    elif template_type == TemplateType.BOOK:
        template_emphasis = f"""
**CRITICAL - BOOK TEMPLATE REQUIREMENTS:**
The email template focuses on books. Your synthesis must:
1. Prioritize book titles (full titles, not abbreviations)
2. Include publisher and year when available
3. Only include books where {recipient_name} is author/editor
4. If NO books found, explicitly state "No books found"
"""
    else:
        template_emphasis = """
**GENERAL TEMPLATE:**
Create balanced summary covering: research areas, current position, notable work.
"""

    return f"""You are creating the final summary for Professor {recipient_name} (research area: {recipient_interest}).

{template_emphasis}

CHAIN-OF-THOUGHT INSTRUCTIONS:
1. Read all batch summaries below
2. Identify facts with multi-source confirmation (highest confidence)
3. Note facts from single sources (mark [SINGLE SOURCE] if unusual/important)
4. Check for contradictions (mark [UNCERTAIN] or omit)
5. Filter for relevance to the template type above
6. Synthesize into structured, concise summary (max 3000 chars)

BATCH SUMMARIES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{batch_summaries}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Think through the 6-step COT process above, then generate the final structured summary.
Focus on quality and verifiability - this will be used for a cold email."""
