from __future__ import annotations

import os
import time

import httpx

from searchbench.providers import register
from searchbench.providers.base import Provider, SearchResult


def _extract_results(data: dict) -> list[dict]:
    for key in ("results", "data", "documents", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


@register
class LinkupProvider(Provider):
    name = "linkup"
    cost_per_query = 0.0055

    def __init__(self, api_key: str | None = None, endpoint: str | None = None) -> None:
        self.api_key = api_key or os.getenv("LINKUP_API_KEY")
        if not self.api_key:
            raise ValueError("LINKUP_API_KEY not set")
        self.endpoint = endpoint or "https://api.linkup.so/v1/search"
        self.mode = "standard"

    async def search(self, query: str, timeout: int) -> SearchResult:
        start = time.perf_counter()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"query": query, "mode": self.mode}

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

        answer = ""
        if isinstance(data, dict):
            answer = data.get("answer") or data.get("summary") or ""

        citations: list[str] = []
        snippets: list[str] = []
        for result in _extract_results(data if isinstance(data, dict) else {}):
            url = result.get("url") or result.get("link") or result.get("source")
            if url:
                citations.append(str(url))
            snippet = result.get("snippet") or result.get("summary") or result.get("description") or result.get("title")
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
