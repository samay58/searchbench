from __future__ import annotations

import os
import time

import httpx

from searchbench.providers import register
from searchbench.providers.base import Provider, SearchResult


def _extract_sources(data: dict) -> list[str]:
    sources: list[str] = []
    for key in ("sources", "citations", "references"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("link")
                    if url:
                        sources.append(str(url))
                elif isinstance(item, str):
                    sources.append(item)
    return [s for s in sources if s]


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
        self.depth = "standard"
        self.output_type = "sourcedAnswer"

    async def search(self, query: str, timeout: int) -> SearchResult:
        start = time.perf_counter()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"q": query, "depth": self.depth, "outputType": self.output_type}

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

        payload_data = data if isinstance(data, dict) else {}
        if isinstance(payload_data.get("data"), dict):
            payload_data = payload_data["data"]

        answer = ""
        if isinstance(payload_data, dict):
            answer = (
                payload_data.get("answer")
                or payload_data.get("summary")
                or payload_data.get("sourcedAnswer")
                or ""
            )

        citations: list[str] = _extract_sources(payload_data)
        snippets: list[str] = []
        for result in _extract_results(payload_data if isinstance(payload_data, dict) else {}):
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
