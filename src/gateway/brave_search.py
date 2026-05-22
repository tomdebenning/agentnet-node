"""Brave Search API client."""

from __future__ import annotations

from typing import Any

import httpx

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


async def brave_web_search(
    *,
    api_key: str,
    query: str,
    count: int = 5,
    timeout: float = 15.0,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Brave Search API key is not configured")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            BRAVE_WEB_SEARCH_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            params={"q": query, "count": count},
        )
        response.raise_for_status()
        return response.json()


def format_brave_results(payload: dict[str, Any]) -> str:
    web = payload.get("web") or {}
    results = web.get("results") or []
    if not results:
        return "No results found."

    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        title = item.get("title") or "(no title)"
        url = item.get("url") or ""
        desc = item.get("description") or ""
        lines.append(f"{index}. {title}\n   {url}\n   {desc}")
    return "\n\n".join(lines)
