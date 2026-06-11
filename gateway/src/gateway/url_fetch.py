"""HTTP URL fetch helper."""

from __future__ import annotations

import httpx

MAX_FETCH_BYTES = 512 * 1024


async def fetch_url(url: str, *, timeout: float = 20.0) -> str:
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "agentnet-node/0.1"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text" not in content_type and "json" not in content_type and "xml" not in content_type:
            return f"Fetched {len(response.content)} bytes ({content_type or 'unknown type'}) — not text."
        data = response.content[:MAX_FETCH_BYTES]
        text = data.decode("utf-8", errors="replace")
        if len(response.content) > MAX_FETCH_BYTES:
            text += "\n\n[... truncated ...]"
        return text
