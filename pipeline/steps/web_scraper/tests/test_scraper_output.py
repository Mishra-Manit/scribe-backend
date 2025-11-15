"""
Independent Web Scraper Output Test

This test file is designed for manual testing and inspection of web scraper output.
Use this to test different URLs and see the complete cleaned content.

Usage:
    # From project root:
    pytest pipeline/steps/web_scraper/test_scraper_output.py -v -s

    # To run a specific test:
    pytest pipeline/steps/web_scraper/test_scraper_output.py::test_scrape_single_url -v -s
"""

import pytest
import logfire
from pipeline.steps.web_scraper.utils import scrape_url, clean_text


# =============================================================================
# Test URLs - Add your own URLs here for testing
# =============================================================================

# Example URLs for testing (replace with your own)
TEST_URLS = [
    "https://www.anthropic.com/research",
    "https://en.wikipedia.org/wiki/Machine_learning",
    "https://www.nature.com/articles/s41586-021-03819-2",  # Example research article
]


# =============================================================================
# Helper Functions
# =============================================================================

def print_separator(title: str = "", char: str = "="):
    """Print a visual separator with optional title."""
    width = 100
    if title:
        side_width = (width - len(title) - 2) // 2
        print(f"\n{char * side_width} {title} {char * side_width}")
    else:
        print(f"\n{char * width}")


def print_scrape_results(url: str, title: str, content: str):
    """Print formatted scrape results for easy inspection."""
    print_separator(f"SCRAPE RESULTS FOR: {url}", "=")

    print(f"\n📄 TITLE: {title if title else '(No title found)'}")
    print(f"📊 CONTENT LENGTH: {len(content)} characters")
    print(f"📝 WORD COUNT: {len(content.split())} words")

    print_separator("CLEANED CONTENT", "-")
    print(content)
    print_separator("END OF CONTENT", "-")


# =============================================================================
# Tests
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_scrape_single_url():
    """
    Test scraping a single URL and display full output.

    Modify the URL variable below to test different pages.
    """
    # 🔧 CHANGE THIS URL TO TEST DIFFERENT PAGES
    test_url = "https://www.anthropic.com/research"

    with logfire.span("test_scrape_single_url", url=test_url):
        title, content = await scrape_url(test_url, timeout=15.0)

        # Assertions
        assert title is not None, f"Failed to scrape URL: {test_url}"
        assert content is not None, f"No content extracted from: {test_url}"
        assert len(content) > 100, f"Content too short ({len(content)} chars)"

        # Display results
        print_scrape_results(test_url, title, content)

        logfire.info(
            "Single URL test completed",
            url=test_url,
            title=title,
            content_length=len(content)
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scrape_multiple_urls():
    """
    Test scraping multiple URLs from TEST_URLS list.

    Add URLs to the TEST_URLS list at the top of this file.
    """
    results = []

    with logfire.span("test_scrape_multiple_urls", total_urls=len(TEST_URLS)):
        for url in TEST_URLS:
            logfire.info(f"Scraping URL", url=url)

            title, content = await scrape_url(url, timeout=15.0)

            if content:
                results.append({
                    "url": url,
                    "title": title,
                    "content": content,
                    "success": True
                })
                print_scrape_results(url, title, content)
            else:
                results.append({
                    "url": url,
                    "success": False
                })
                print(f"\n❌ FAILED TO SCRAPE: {url}\n")

        # Summary
        successful = sum(1 for r in results if r["success"])
        print_separator("SUMMARY", "=")
        print(f"✅ Successful: {successful}/{len(TEST_URLS)}")
        print(f"❌ Failed: {len(TEST_URLS) - successful}/{len(TEST_URLS)}")
        print_separator()

        # Assert at least one succeeded
        assert successful > 0, "All URLs failed to scrape"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_clean_text_function():
    """
    Test the clean_text function with sample HTML text.

    This demonstrates how the cleaning function processes raw HTML text.
    """
    # Sample raw HTML text (with typical HTML artifacts)
    raw_text = """


        Welcome to the Website


        This is a sample paragraph with    multiple   spaces.




        This has many newlines above it.

        This line has unicode characters: café, naïve, résumé

        Tab    separated    content

    """

    with logfire.span("test_clean_text"):
        cleaned = clean_text(raw_text)

        print_separator("CLEAN TEXT TEST", "=")
        print("\n📄 ORIGINAL TEXT:")
        print(repr(raw_text))

        print("\n📝 CLEANED TEXT:")
        print(repr(cleaned))

        print("\n👁️  VISUAL OUTPUT:")
        print(cleaned)
        print_separator()

        # Assertions
        assert len(cleaned) > 0, "Cleaned text should not be empty"
        assert "multiple   spaces" not in cleaned, "Multiple spaces should be collapsed"
        assert "\n\n\n" not in cleaned, "Multiple newlines should be collapsed"

        logfire.info(
            "Clean text test completed",
            original_length=len(raw_text),
            cleaned_length=len(cleaned)
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scrape_with_custom_url(custom_url: str = None):
    """
    Test scraping with a custom URL passed as parameter.

    This test can be used programmatically by passing a URL.
    To use from command line, modify the custom_url default value.
    """
    # Default URL if none provided
    if custom_url is None:
        # 🔧 CHANGE THIS TO YOUR CUSTOM URL
        custom_url = "https://www.anthropic.com"

    with logfire.span("test_custom_url", url=custom_url):
        title, content = await scrape_url(custom_url, timeout=15.0)

        if content:
            print_scrape_results(custom_url, title, content)

            # Optional: Save to file for easier inspection
            output_file = "/tmp/scraper_output.txt"
            with open(output_file, "w") as f:
                f.write(f"URL: {custom_url}\n")
                f.write(f"TITLE: {title}\n")
                f.write(f"=" * 100 + "\n\n")
                f.write(content)

            print(f"\n💾 Full output saved to: {output_file}")

            assert len(content) > 0
        else:
            print(f"\n❌ FAILED TO SCRAPE: {custom_url}")
            print("Possible reasons:")
            print("  - URL blocked scraping")
            print("  - Timeout occurred")
            print("  - Non-HTML content")
            print("  - Insufficient text content")

            pytest.fail(f"Failed to scrape URL: {custom_url}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_compare_raw_vs_cleaned():
    """
    Test that shows both raw and cleaned output for comparison.
    Useful for understanding what the clean_text function does.
    """
    test_url = "https://en.wikipedia.org/wiki/Web_scraping"

    with logfire.span("test_compare_outputs", url=test_url):
        # Scrape URL (which applies cleaning)
        title, cleaned_content = await scrape_url(test_url, timeout=15.0)

        if not cleaned_content:
            pytest.skip(f"Could not scrape URL: {test_url}")

        print_separator("RAW VS CLEANED COMPARISON", "=")
        print(f"\n🌐 URL: {test_url}")
        print(f"📄 TITLE: {title}")

        # Show first 1000 chars of cleaned
        preview_length = 1000
        print_separator("CLEANED CONTENT (first 1000 chars)", "-")
        print(cleaned_content[:preview_length])
        if len(cleaned_content) > preview_length:
            print(f"\n... ({len(cleaned_content) - preview_length} more characters)")

        print_separator("STATISTICS", "-")
        print(f"Total length: {len(cleaned_content)} characters")
        print(f"Word count: {len(cleaned_content.split())} words")
        print(f"Line count: {len(cleaned_content.splitlines())} lines")
        print(f"Average word length: {len(cleaned_content) / max(len(cleaned_content.split()), 1):.1f} chars")
        print_separator()


# =============================================================================
# Quick Run Examples (uncomment to use)
# =============================================================================

if __name__ == "__main__":
    """
    Run tests directly with: python test_scraper_output.py

    Note: Better to use pytest for proper async handling:
        pytest test_scraper_output.py -v -s
    """
    import asyncio

    # Example: Test a single URL
    asyncio.run(test_scrape_single_url())

    # Example: Test multiple URLs
    # asyncio.run(test_scrape_multiple_urls())

    # Example: Test clean_text function
    # asyncio.run(test_clean_text_function())
