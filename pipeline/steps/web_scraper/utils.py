"""
Web Scraper Utilities

Web scraping functions migrated from api/legacy/app.py with improvements:
- Async implementation
- Better HTML cleaning
- Timeout handling
- Content validation
"""

import re
import httpx
import logfire
from bs4 import BeautifulSoup
from typing import Optional, Tuple


async def scrape_url(
    url: str,
    timeout: float = 10.0,
    max_content_length: int = 500000  # 500KB limit
) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape text content from a URL.

    Args:
        url: URL to scrape
        timeout: Request timeout in seconds
        max_content_length: Max response size in bytes

    Returns:
        Tuple of (title, content) or (None, None) if failed

    Note:
        Returns None for both on failure (no exceptions raised)
    """
    # Skip non-HTML files
    if url.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx')):
        logfire.info("Skipping non-HTML URL", url=url)
        return None, None

    # Skip video/media platforms (not useful for text scraping)
    blocked_domains = [
        'youtube.com',
        'youtu.be',
        'vimeo.com',
    ]
    url_lower = url.lower()
    if any(domain in url_lower for domain in blocked_domains):
        logfire.info("Skipping blocked domain (video/media platform)", url=url)
        return None, None

    try:
        # User agent to avoid bot blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10)
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'html' not in content_type:
                logfire.info("Non-HTML content type, skipping", url=url, content_type=content_type)
                return None, None

            # Check size
            if len(response.content) > max_content_length:
                logfire.warning("Response too large, skipping", url=url, size=len(response.content))
                return None, None

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract title
            title = None
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()

            # Remove script and style elements
            for script in soup(["script", "style", "meta", "link", "noscript"]):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean text
            cleaned = clean_text(text)

            if not cleaned or len(cleaned) < 100:
                logfire.info("Insufficient content after cleaning", url=url)
                return None, None

            logfire.info(
                "Successfully scraped URL",
                url=url,
                content_length=len(cleaned),
                word_count=len(cleaned.split())
            )

            return title, cleaned

    except httpx.HTTPStatusError as e:
        logfire.warning("HTTP error scraping URL", url=url, status=e.response.status_code)
        return None, None
    except httpx.TimeoutException:
        logfire.warning("Timeout scraping URL", url=url)
        return None, None
    except Exception as e:
        logfire.warning("Error scraping URL", url=url, error=str(e))
        return None, None


def clean_text(text: str) -> str:
    """
    Clean scraped HTML text.

    Migrated from legacy cleanText() function.

    Args:
        text: Raw text from HTML

    Returns:
        Cleaned text
    """
    # Split into lines
    lines = text.splitlines()

    # Filter English lines (has letters and spaces)
    cleaned_lines = [
        line.strip()
        for line in lines
    ]

    # Join lines
    cleaned_text = '\n'.join(cleaned_lines)

    # Remove non-ASCII characters
    cleaned_text = re.sub(r'[^\x00-\x7F]+', '', cleaned_text)

    # Collapse multiple spaces
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)

    # Collapse multiple newlines
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

    return cleaned_text.strip()