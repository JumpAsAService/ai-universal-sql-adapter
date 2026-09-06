from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from pydantic_ai.common_tools.duckduckgo import (
    DDGS,
    DuckDuckGoResult,
    DuckDuckGoSearchTool,
)


def _is_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def make_search_site(
    allowed_domains: list[str], max_results: int = 10
) -> Callable[[str], Awaitable[list[DuckDuckGoResult]]]:
    """Build a DuckDuckGo search tool restricted to the given domains.

    The returned function exposes only `query` to the model; the allowed
    domains are fixed here and cannot be changed by the LLM.
    """
    if not allowed_domains:
        raise ValueError("No allowed domains set")

    sites = " OR ".join(f"site:{d}" for d in allowed_domains)
    ddg = DuckDuckGoSearchTool(client=DDGS(), max_results=max_results)

    async def search_site(query: str) -> list[DuckDuckGoResult]:
        """Search the web, restricted to the allowed domains.

        Args:
            query: text to search
        """
        results = await ddg(f"{query} ({sites})")
        return [r for r in results if _is_allowed(r["href"], allowed_domains)]

    return search_site
