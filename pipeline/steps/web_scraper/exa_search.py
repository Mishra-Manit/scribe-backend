"""Exa Search API integration for unified search + synthesis."""

import asyncio
import logfire
from typing import List, Optional
from pydantic import BaseModel, Field
from exa_py import Exa
from config.settings import settings


class ExaCitation(BaseModel):
    """Citation from Exa answer response."""
    url: str
    title: Optional[str] = None
    text: Optional[str] = None


class ExaAnswerResult(BaseModel):
    """Result from Exa answer API."""
    answer: str
    citations: List[ExaCitation] = Field(default_factory=list)


class DualQueryResult(BaseModel):
    """Combined result from background + publications queries."""
    background: ExaAnswerResult
    publications: ExaAnswerResult
    combined_answer: str
    all_citations: List[ExaCitation] = Field(default_factory=list)


class ExaSearchClient:
    """Client for Exa Search API with answer synthesis."""

    def __init__(self):
        if not settings.exa_api_key:
            raise ValueError("EXA_API_KEY not set in environment")
        self.exa = Exa(api_key=settings.exa_api_key)

    async def answer(self, query: str, timeout: float = 30.0) -> ExaAnswerResult:
        """Get AI-synthesized answer for a query."""
        if not query.strip():
            raise ValueError("Query cannot be empty")

        logfire.info("Exa search", query=query[:100])

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.exa.answer, query=query, text=True),
                timeout=timeout
            )

            citations = [
                ExaCitation(
                    url=getattr(c, 'url', ''),
                    title=getattr(c, 'title', None),
                    text=getattr(c, 'text', None)
                )
                for c in (result.citations or [])
                if hasattr(result, 'citations')
            ] if hasattr(result, 'citations') and result.citations else []

            answer_text = result.answer if hasattr(result, 'answer') else str(result)

            logfire.info("Exa complete", answer_len=len(answer_text), citations=len(citations))
            return ExaAnswerResult(answer=answer_text, citations=citations)

        except asyncio.TimeoutError:
            logfire.error("Exa timeout", query=query[:100])
            raise TimeoutError(f"Exa API timed out after {timeout}s")
        except ConnectionError as e:
            logfire.error("Exa connection error", error=str(e))
            raise
        except Exception as e:
            logfire.error("Exa error", error_type=type(e).__name__, error=str(e)[:500])
            raise

    async def dual_answer(
        self,
        background_query: str,
        publications_query: str,
        timeout: float = 45.0
    ) -> DualQueryResult:
        """Execute background and publications queries in parallel."""
        logfire.info("Dual Exa queries starting")

        background_result, publications_result = await asyncio.gather(
            self.answer(background_query, timeout=timeout),
            self.answer(publications_query, timeout=timeout)
        )

        combined = self._combine_answers(background_result.answer, publications_result.answer)
        citations = self._deduplicate_citations(
            background_result.citations,
            publications_result.citations
        )

        logfire.info(
            "Dual queries complete",
            bg_len=len(background_result.answer),
            pub_len=len(publications_result.answer),
            citations=len(citations)
        )

        return DualQueryResult(
            background=background_result,
            publications=publications_result,
            combined_answer=combined,
            all_citations=citations
        )

    def _combine_answers(self, background: str, publications: str) -> str:
        """Merge background and publications into sectioned content."""
        sections = []
        if background and background.strip():
            sections.append(f"## BACKGROUND\n\n{background.strip()}")
        if publications and publications.strip():
            sections.append(f"## RECENT PUBLICATIONS & WORKS\n\n{publications.strip()}")
        return "\n\n".join(sections) if sections else "No information found."

    def _deduplicate_citations(
        self,
        background_citations: List[ExaCitation],
        publications_citations: List[ExaCitation]
    ) -> List[ExaCitation]:
        """Deduplicate by URL, prioritizing publications citations."""
        seen = set()
        result = []
        # Publications first (priority)
        for c in publications_citations:
            if c.url not in seen:
                seen.add(c.url)
                result.append(c)
        for c in background_citations:
            if c.url not in seen:
                seen.add(c.url)
                result.append(c)
        return result
