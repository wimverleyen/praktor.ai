import asyncio
from core.tool import ToolResult, register_tool
from settings import create_log

log = create_log()


class WebSearchTool:
    """
    Search the web using DuckDuckGo (no API key required).

    Input: plain-text search query string.
    Returns top-5 results formatted as markdown.
    """

    name = "web_search"
    description = (
        "Search the web for current information. "
        "Input: a plain-text search query. "
        "Returns top results with title and summary."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            results = await asyncio.to_thread(self._search, input)
            if not results:
                return ToolResult(
                    content="No results found.",
                    metadata={"query": input, "num_results": 0},
                )
            formatted = "\n\n".join(
                f"**{r.get('title', 'No title')}**\n{r.get('body', '')}"
                for r in results
            )
            return ToolResult(
                content=formatted,
                metadata={"query": input, "num_results": len(results)},
            )
        except Exception as e:
            log.error(f"WebSearchTool failed for query '{input}': {e}")
            return ToolResult(content="", error=str(e))

    def _search(self, query: str, max_results: int = 5) -> list[dict]:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))


# Auto-register at import time
register_tool(WebSearchTool())
