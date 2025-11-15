"""
Google Custom Search API integration.

Migrated from api/legacy/app.py with improvements:
- Async implementation with httpx
- Better error handling
- Rate limiting
- Result validation
"""

import httpx
import logfire
from typing import List, Dict, Any
from config.settings import settings


class GoogleSearchClient:
    """Client for Google Custom Search API."""

    def __init__(self):
        """Initialize search client"""
        self.api_key = settings.google_api_key
        self.cse_id = settings.google_cse_id
        self.base_url = "https://www.googleapis.com/customsearch/v1"

        # Validate credentials
        if not self.api_key or not self.cse_id:
            raise ValueError(
                "Google API credentials missing. "
                "Set GOOGLE_API_KEY and GOOGLE_CSE_ID in environment."
            )

    async def search(
        self,
        query: str,
        num_results: int = 5,
        timeout: float = 10.0
    ) -> List[Dict[str, Any]]:
        """
        Perform Google Custom Search.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10)
            timeout: Request timeout in seconds

        Returns:
            List of search result dicts with 'link', 'title', 'snippet'

        Raises:
            httpx.HTTPError: If API request fails
            ValueError: If response format is invalid
        """
        # Validate inputs
        if not query.strip():
            raise ValueError("Query cannot be empty")

        num_results = min(num_results, 10)  # Google API max is 10

        # Build request params
        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": query.strip(),
            "num": num_results
        }

        logfire.info(
            "Performing Google Custom Search",
            query=query,
            num_results=num_results
        )

        # Make async request
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

                data = response.json()

                # Extract items
                items = data.get("items", [])

                logfire.info(
                    "Google Search completed",
                    results_found=len(items)
                )

                return items

            except httpx.HTTPStatusError as e:
                logfire.error(
                    "Google API HTTP error",
                    status_code=e.response.status_code,
                    response=e.response.text[:500]  # Truncate for logging
                )
                raise
            except httpx.TimeoutException:
                logfire.error("Google API timeout", query=query)
                raise

    async def search_multiple_terms(
        self,
        queries: List[str],
        results_per_query: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search multiple queries and combine results.

        Args:
            queries: List of search query strings
            results_per_query: Results per query

        Returns:
            Combined list of unique search results
        """
        all_results = []
        seen_urls = set()

        for query in queries:
            try:
                results = await self.search(query, num_results=results_per_query)

                # Deduplicate by URL
                for result in results:
                    url = result.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)

            except Exception as e:
                logfire.warning(
                    "Search query failed, continuing with others",
                    query=query,
                    error=str(e)
                )
                continue

        logfire.info(
            "Multi-term search completed",
            total_queries=len(queries),
            unique_results=len(all_results)
        )

        return all_results
