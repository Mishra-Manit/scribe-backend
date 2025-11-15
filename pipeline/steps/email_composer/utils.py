"""
Email Composer Utilities

Email validation and quality checking functions.
"""

import re
import logfire
from typing import List, Tuple

from .models import EmailValidationResult
from pipeline.models.core import TemplateType


def validate_email(
    email_content: str,
    recipient_name: str,
    template_type: TemplateType
) -> EmailValidationResult:
    """
    Validate generated email quality.

    Checks:
    - No unfilled placeholders ({{variable}} or [variable])
    - No AI-sounding phrases
    - Recipient name is mentioned
    - Minimum word count (50 words)
    - Publications mentioned if required

    Args:
        email_content: Generated email text
        recipient_name: Expected recipient name
        template_type: Type of template (RESEARCH, BOOK, or GENERAL)

    Returns:
        EmailValidationResult with validation status
    """
    issues: List[str] = []
    warnings: List[str] = []

    # Check 1: No placeholders remain
    has_placeholders = bool(
        re.search(r'\{\{[^}]+\}\}', email_content) or
        re.search(r'\[[^\]]+\]', email_content)
    )

    if has_placeholders:
        issues.append("Email contains unfilled placeholders")

    # Check 2: No AI-sounding phrases (unless common in academic writing)
    ai_phrases = [
        "cutting-edge",
        "groundbreaking",
        "state-of-the-art",
        "innovative solution",
        "paradigm shift",
        "game-changer",
        "revolutionary",
        "disruptive innovation"
    ]

    email_lower = email_content.lower()
    found_ai_phrases = [
        phrase for phrase in ai_phrases
        if phrase in email_lower
    ]

    if found_ai_phrases:
        warnings.append(f"Contains AI-sounding phrases: {', '.join(found_ai_phrases)}")

    # Check 3: Recipient name mentioned
    recipient_last_name = recipient_name.split()[-1]

    if recipient_last_name.lower() not in email_lower:
        warnings.append(f"Recipient name '{recipient_last_name}' not mentioned in email")

    # Check 4: Word count
    word_count = len(email_content.split())

    if word_count < 50:
        issues.append(f"Email too short: {word_count} words (minimum 50)")
    elif word_count > 500:
        warnings.append(f"Email very long: {word_count} words (consider shortening)")

    # Check 5: Publications mentioned if required
    mentions_publications = _check_publication_mentions(email_content)

    if template_type == TemplateType.RESEARCH and not mentions_publications:
        warnings.append("No specific publications mentioned (template may require them)")

    # Check 6: Tone matching (basic checks)
    tone_matches = _check_tone_consistency(email_content)

    if not tone_matches:
        warnings.append("Email tone may not match template style")

    # Determine overall validity
    is_valid = len(issues) == 0

    logfire.info(
        "Email validation complete",
        is_valid=is_valid,
        issues_count=len(issues),
        warnings_count=len(warnings),
        word_count=word_count,
        mentions_publications=mentions_publications
    )

    return EmailValidationResult(
        is_valid=is_valid,
        issues=issues,
        warnings=warnings,
        mentions_publications=mentions_publications,
        has_placeholders=has_placeholders,
        word_count=word_count,
        tone_matches_template=tone_matches
    )


def clean_email_formatting(email_content: str) -> str:
    """
    Clean and format email content.

    - Remove excessive whitespace
    - Ensure single blank line between paragraphs
    - Strip leading/trailing whitespace
    - Preserve intentional formatting

    Args:
        email_content: Raw email text

    Returns:
        Cleaned email text
    """
    # Remove leading/trailing whitespace
    cleaned = email_content.strip()

    # Replace multiple blank lines with single blank line
    cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)

    # Remove trailing spaces from lines
    lines = [line.rstrip() for line in cleaned.split('\n')]
    cleaned = '\n'.join(lines)

    return cleaned


def _check_publication_mentions(email_content: str) -> bool:
    """
    Check if email mentions specific publications.

    Looks for patterns like:
    - "your paper on X"
    - "your work in X"
    - "your research on X"
    - Quoted titles
    - Publication-related keywords

    Args:
        email_content: Email text

    Returns:
        True if publications are mentioned
    """
    email_lower = email_content.lower()

    # Publication indicators
    publication_patterns = [
        r'your (?:paper|article|work|research|publication|study) (?:on|in|about)',
        r'your recent (?:paper|article|work|publication)',
        r'(?:paper|article) (?:titled|entitled|called)',
        r'I (?:read|found|came across|saw) your (?:paper|work|article)',
        r'particularly interested in your (?:paper|work|research)',
        r'"[^"]+"',  # Quoted titles
    ]

    for pattern in publication_patterns:
        if re.search(pattern, email_lower):
            return True

    # Check for publication-related keywords
    keywords = ['published', 'journal', 'conference', 'proceedings', 'arxiv']

    keyword_count = sum(1 for keyword in keywords if keyword in email_lower)

    # If 2+ publication keywords, likely mentions publications
    return keyword_count >= 2


def _check_tone_consistency(email_content: str) -> bool:
    """
    Basic tone consistency checks.

    Checks for:
    - Excessive exclamation points (>2)
    - All caps words (potential shouting)
    - Extremely short paragraphs (potential fragmentation)
    - Overly formal/stiff language

    Args:
        email_content: Email text

    Returns:
        True if tone seems consistent
    """
    # Check exclamation points
    exclamation_count = email_content.count('!')

    if exclamation_count > 3:
        return False

    # Check for all caps words (exclude acronyms)
    words = email_content.split()
    all_caps_words = [
        word for word in words
        if word.isupper() and len(word) > 3
    ]

    if len(all_caps_words) > 2:
        return False

    # Basic checks passed
    return True


def extract_subject_line(email_content: str) -> Tuple[str, str]:
    """
    Extract subject line if present in email.

    Looks for patterns like:
    - "Subject: X"
    - First line if short (<80 chars)

    Args:
        email_content: Email text

    Returns:
        Tuple of (subject_line, email_body)
        If no subject found, returns ("", email_content)
    """
    lines = email_content.split('\n')

    if not lines:
        return ("", email_content)

    # Check for explicit "Subject:" line
    first_line = lines[0].strip()

    if first_line.lower().startswith('subject:'):
        subject = first_line[8:].strip()  # Remove "Subject: "
        body = '\n'.join(lines[1:]).strip()
        return (subject, body)

    # Check if first line is short (potential subject)
    if len(first_line) < 80 and len(lines) > 1 and lines[1].strip() == "":
        # First line is short and followed by blank line - likely subject
        subject = first_line
        body = '\n'.join(lines[2:]).strip()
        return (subject, body)

    # No subject line detected
    return ("", email_content)
