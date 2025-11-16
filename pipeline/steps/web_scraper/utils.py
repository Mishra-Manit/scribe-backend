"""
Web Scraper Utilities

Web scraping functions migrated from api/legacy/app.py with improvements:
- Async implementation
- Better HTML cleaning
- Timeout handling
- Content validation

Scraping implementations:
- scrape_url: Playwright-based (headless browser) - primary implementation
"""

import re
import logfire
from bs4 import BeautifulSoup, Comment
from playwright.async_api import Browser
from typing import Optional, Tuple

def clean_text(html: str) -> str:
    """Normalize HTML into readable plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Drop non-content elements
    for element in soup(["script", "style", "noscript", "template", "svg"]):
        element.decompose()

    # Remove inline comments to avoid boilerplate
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    text = soup.get_text(separator="\n")

    # Split into lines, trim whitespace, and discard empties
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_text = "\n".join(lines)

    # Remove non-ASCII characters
    cleaned_text = re.sub(r"[^\x00-\x7F]+", "", cleaned_text)

    # Collapse multiple spaces
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)

    # Collapse multiple newlines
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()


async def scrape_url(
    url: str,
    browser: Browser,
    timeout: float = 10.0,
    max_content_length: int = 500000  # 500KB limit
) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape text content from a URL using Playwright (headless browser).

    Args:
        url: URL to scrape
        browser: Playwright Browser instance (persistent across calls)
        timeout: Page load timeout in seconds
        max_content_length: Max content size (unused but kept for compatibility)

    Returns:
        Tuple of (title, content) or (None, None) if failed

    Note:
        Returns None for both on failure (no exceptions raised)
        Creates a new BrowserContext per URL for isolation
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

    context = None
    page = None

    try:
        # Create new browser context for isolation (cookies, storage, etc.)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        # Create page within context
        page = await context.new_page()

        # Navigate to URL with timeout
        response = await page.goto(
            url,
            wait_until='domcontentloaded',
            timeout=int(timeout * 1000)  # Convert to milliseconds
        )

        # Check response status
        if not response or response.status >= 400:
            logfire.warning("HTTP error scraping URL", url=url, status=response.status if response else "no response")
            return None, None

        # Wait for network to be idle (all content loaded)
        await page.wait_for_load_state('networkidle', timeout=int(timeout * 1000))

        # Extract title
        title = await page.title()
        if not title:
            title = None

        # Extract HTML and clean to normalized text
        html_content = await page.content()
        cleaned = clean_text(html_content)

        if max_content_length and len(cleaned) > max_content_length:
            logfire.info(
                "Truncating content due to max_content_length",
                url=url,
                original_length=len(cleaned),
                max_content_length=max_content_length
            )
            cleaned = cleaned[:max_content_length]

        if not cleaned or len(cleaned) < 100:
            logfire.info("Insufficient content after cleaning", url=url)
            return None, None

        logfire.info(
            "Successfully scraped URL with Playwright",
            url=url,
            content_length=len(cleaned),
            word_count=len(cleaned.split())
        )

        return title, cleaned

    except Exception as e:
        # Catch all errors: TimeoutError, network errors, etc.
        logfire.warning("Error scraping URL with Playwright", url=url, error=str(e))
        return None, None

    finally:
        # Always cleanup context (includes closing page)
        if context:
            await context.close()