"""PDF parsing utilities for resume text extraction."""

import httpx
import logfire
import re
from pypdf import PdfReader
from io import BytesIO


async def extract_text_from_url(pdf_url: str, timeout: int = 30) -> str:
    """
    Fetch PDF from URL and extract text content.

    Returns:
        Cleaned text content from PDF

    Raises:
        ValueError: If PDF is invalid, empty, scanned, or has insufficient text
    """
    with logfire.span("pdf_parser.extract_text_from_url", pdf_url=pdf_url):
        try:
            # Fetch PDF from URL
            logfire.info("Fetching PDF from URL", pdf_url=pdf_url)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(pdf_url)
                response.raise_for_status()

            logfire.info("PDF fetched successfully", size_bytes=len(response.content))

            # Parse PDF
            pdf_bytes = BytesIO(response.content)
            reader = PdfReader(pdf_bytes)

            # Validate PDF has pages
            if len(reader.pages) == 0:
                logfire.warning("PDF has no pages", pdf_url=pdf_url)
                raise ValueError("PDF has no pages")

            logfire.info("PDF parsed", page_count=len(reader.pages))

            # Extract text from all pages
            text = ""
            for page in reader.pages:
                text += page.extract_text()

            # Clean the extracted text
            text = clean_text(text)

            # Validate sufficient text extracted
            if len(text) < 50:
                logfire.warning(
                    "Insufficient text extracted from PDF",
                    pdf_url=pdf_url,
                    text_length=len(text)
                )
                raise ValueError(
                    "PDF appears to be scanned or contains too little text. "
                    "Please ensure your resume is a text-based PDF."
                )

            logfire.info("Text extracted successfully", text_length=len(text))
            return text

        except httpx.HTTPStatusError as e:
            logfire.error(
                "Failed to fetch PDF",
                pdf_url=pdf_url,
                status_code=e.response.status_code,
                exc_info=True
            )
            raise ValueError(f"Failed to fetch PDF: HTTP {e.response.status_code}")
        except Exception as e:
            logfire.error(
                "PDF parsing failed",
                pdf_url=pdf_url,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            # Re-raise ValueError as-is, wrap other exceptions
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"PDF parsing failed: {str(e)}")


def clean_text(raw_text: str) -> str:
    # Collapse multiple spaces into single space
    text = " ".join(raw_text.split())

    # Limit consecutive newlines to maximum of 2 (preserve paragraph structure)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip leading/trailing whitespace
    return text.strip()
