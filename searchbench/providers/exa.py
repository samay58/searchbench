from __future__ import annotations

import os
import time

import httpx

from searchbench.providers import register
from searchbench.providers.base import Provider, SearchResult


def _normalize_citations(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(c) for c in raw if c]
    if isinstance(raw, dict):
        flattened: list[str] = []
        for value in raw.values():
            if isinstance(value, list):
                flattened.extend(str(c["url"]) if isinstance(c, dict) and "url" in c else str(c) for c in value if c)
        return [c for c in flattened if c]
    return []


@register
class ExaProvider(Provider):
    name = "exa"
    cost_per_query = 0.01

    def __init__(self, api_key: str | None = None, endpoint: str | None = None) -> None:
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        if not self.api_key:
            raise ValueError("EXA_API_KEY not set")
        self.endpoint = endpoint or "https://api.exa.ai/answer"

    async def search(self, query: str, timeout: int) -> SearchResult:
        start = time.perf_counter()
        headers = {"x-api-key": self.api_key}
        payload = {"query": query, "text": True}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError as exc:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    return SearchResult(
                        answer="",
                        citations=[],
                        latency_ms=latency_ms,
                        cost_usd=0.0,
                        raw_response={"error": "invalid_json", "response_text": response.text},
                        error=str(exc),
                        timed_out=False,
                    )
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
        if isinstance(answer, dict):
            answer = str(answer)
        citations = _normalize_citations(data.get("citations") if isinstance(data, dict) else None)
        latency_ms = int((time.perf_counter() - start) * 1000)

        return SearchResult(
            answer=answer or "",
            citations=citations,
            latency_ms=latency_ms,
            cost_usd=self.cost_per_query,
            raw_response=data if isinstance(data, dict) else {"raw": data},
            error=None,
            timed_out=False,
        )
