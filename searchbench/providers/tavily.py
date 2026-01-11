from __future__ import annotations

import os
import time

import httpx

from searchbench.providers import register
from searchbench.providers.base import Provider, SearchResult


def _resolve_cost() -> float:
    override = os.getenv("TAVILY_COST_PER_QUERY")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    paid = os.getenv("TAVILY_COST_MODE", "free").strip().lower()
    if paid == "paid":
        return 0.008
    return 0.0


@register
class TavilyProvider(Provider):
    name = "tavily"
    cost_per_query = 0.0

    def __init__(self, api_key: str | None = None, endpoint: str | None = None) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY not set")
        self.endpoint = endpoint or "https://api.tavily.com/search"

    async def search(self, query: str, timeout: int) -> SearchResult:
        start = time.perf_counter()
        payload = {
            "query": query,
            "search_depth": "basic",
            "include_answer": True,
            "include_raw_content": False,
            "max_results": 5,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return SearchResult(
                answer="",
                citations=[],
                latency_ms=latency_ms,
                cost_usd=0.0,
                raw_response={"error": str(exc)},
                error="timeout",
                timed_out=True,
            )
        except httpx.HTTPStatusError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return SearchResult(
                answer="",
                citations=[],
                latency_ms=latency_ms,
                cost_usd=0.0,
                raw_response={
                    "error": str(exc),
                    "status_code": exc.response.status_code,
                    "response_text": exc.response.text,
                    "payload": payload,
                },
                error=str(exc),
                timed_out=False,
            )
        except httpx.RequestError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return SearchResult(
                answer="",
                citations=[],
                latency_ms=latency_ms,
                cost_usd=0.0,
                raw_response={"error": str(exc)},
                error=str(exc),
                timed_out=False,
            )

        answer = data.get("answer", "") if isinstance(data, dict) else ""
        citations = [r.get("url", "") for r in data.get("results", []) if isinstance(r, dict)]
        latency_ms = int((time.perf_counter() - start) * 1000)

        return SearchResult(
            answer=answer or "",
            citations=[c for c in citations if c],
            latency_ms=latency_ms,
            cost_usd=_resolve_cost(),
            raw_response=data if isinstance(data, dict) else {"raw": data},
            error=None,
            timed_out=False,
        )
