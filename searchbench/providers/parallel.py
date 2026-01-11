from __future__ import annotations

import os
import time

import httpx

from searchbench.providers import register
from searchbench.providers.base import Provider, SearchResult


def _synthesize_answer(data: dict) -> tuple[str, list[str]]:
    answer = ""
    if "answer" in data and data["answer"]:
        answer = str(data["answer"])
    elif "summary" in data and data["summary"]:
        answer = str(data["summary"])

    citations: list[str] = []
    snippets: list[str] = []
    for result in data.get("results", [])[:3]:
        if isinstance(result, dict):
            url = result.get("url")
            if url:
                citations.append(str(url))
            for key in ("excerpts", "content", "snippet", "description"):
                value = result.get(key)
                if not value:
                    continue
                if key == "excerpts" and isinstance(value, list):
                    for excerpt in value:
                        if excerpt:
                            snippets.append(" ".join(str(excerpt).split()))
                else:
                    snippets.append(" ".join(str(value).split()))
                break
    if not answer:
        answer = " ".join(snippets[:2]).strip()
    return answer, citations


@register
class ParallelProvider(Provider):
    name = "parallel"
    cost_per_query = 0.005

    def __init__(self, api_key: str | None = None, endpoint: str | None = None) -> None:
        self.api_key = api_key or os.getenv("PARALLEL_API_KEY")
        if not self.api_key:
            raise ValueError("PARALLEL_API_KEY not set")
        self.endpoint = endpoint or "https://api.parallel.ai/v1beta/search"
        self.processor = "pro"
        self.max_results = 10
        self.max_chars_per_result = 1200

    async def search(self, query: str, timeout: int) -> SearchResult:
        start = time.perf_counter()
        headers = {
            "x-api-key": self.api_key,
            "parallel-beta": "search-extract-2025-10-10",
            "Content-Type": "application/json",
        }
        payload = {
            "processor": self.processor,
            "objective": query[:5000],
            "max_results": self.max_results,
            "max_chars_per_result": self.max_chars_per_result,
        }

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

        answer, citations = _synthesize_answer(data)
        latency_ms = int((time.perf_counter() - start) * 1000)

        return SearchResult(
            answer=answer,
            citations=citations,
            latency_ms=latency_ms,
            cost_usd=self.cost_per_query,
            raw_response=data,
            error=None,
            timed_out=False,
        )
