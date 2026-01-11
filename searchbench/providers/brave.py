from __future__ import annotations

import os
import time

import httpx

from searchbench.providers import register
from searchbench.providers.base import Provider, SearchResult


def _extract_results(data: dict) -> list[dict]:
    if isinstance(data.get("web"), dict):
        results = data["web"].get("results", [])
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
    results = data.get("results", [])
    if isinstance(results, list):
        return [r for r in results if isinstance(r, dict)]
    return []


def _extract_summary(data: dict) -> tuple[str, list[str]]:
    sources: list[str] = []
    summary = ""

    if isinstance(data.get("summary"), str):
        summary = data.get("summary", "")
    if not summary and isinstance(data.get("summarizer"), dict):
        summarizer = data["summarizer"]
        summary = summarizer.get("summary") or summarizer.get("answer") or ""
        for source in summarizer.get("sources", []) or []:
            if isinstance(source, dict) and source.get("url"):
                sources.append(str(source["url"]))
            elif isinstance(source, str):
                sources.append(source)

    return summary, [s for s in sources if s]


@register
class BraveProvider(Provider):
    name = "brave"
    cost_per_query = 0.005

    def __init__(self, api_key: str | None = None, endpoint: str | None = None) -> None:
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not set")
        self.endpoint = endpoint or "https://api.search.brave.com/res/v1/web/search"
        self.count = 10

    async def search(self, query: str, timeout: int) -> SearchResult:
        start = time.perf_counter()
        params = {"q": query, "summary": 1, "count": self.count}
        headers = {"X-Subscription-Token": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.endpoint, headers=headers, params=params)
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
                    "params": params,
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

        summary, summary_sources = _extract_summary(data if isinstance(data, dict) else {})
        citations = list(summary_sources)
        answer = summary.strip()

        results = _extract_results(data if isinstance(data, dict) else {})
        snippets: list[str] = []
        for result in results[:3]:
            url = result.get("url")
            if url:
                citations.append(str(url))
            snippet = result.get("description") or result.get("snippet") or result.get("title")
            if snippet:
                snippets.append(" ".join(str(snippet).split()))

        if not answer:
            answer = " ".join(snippets[:2]).strip()

        latency_ms = int((time.perf_counter() - start) * 1000)
        return SearchResult(
            answer=answer,
            citations=[c for c in citations if c],
            latency_ms=latency_ms,
            cost_usd=self.cost_per_query,
            raw_response=data if isinstance(data, dict) else {"raw": data},
            error=None,
            timed_out=False,
        )
