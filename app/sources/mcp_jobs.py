from __future__ import annotations

import asyncio
import json
from typing import Any


def _content_to_payload(result: Any) -> Any:
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            return json.loads(text)
        except Exception:
            continue
    return {}


async def _call(url: str, tool: str, arguments: dict) -> Any:
    try:
        from mcp import Client
    except ImportError as exc:
        raise RuntimeError("MCP job sources require the 'mcp' package. Run: pip install -r requirements.txt") from exc
    async with Client(url) as client:
        result = await client.call_tool(tool, arguments)
        return _content_to_payload(result)


def call_tool(url: str, tool: str, arguments: dict) -> Any:
    """Synchronous bridge used by the existing discovery engine."""
    return asyncio.run(_call(url, tool, arguments))


def rows_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("jobs", "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            for inner in ("jobs", "results", "items"):
                rows = value.get(inner)
                if isinstance(rows, list):
                    return [x for x in rows if isinstance(x, dict)]
    return []
