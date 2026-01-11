from __future__ import annotations

import asyncio
import os
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from searchbench.config import Settings, timeout_for
from searchbench.providers.base import Provider, SearchResult
from searchbench.queries import Query


DEFAULT_QUERY_CONCURRENCY = int(os.getenv("QUERY_CONCURRENCY", "2"))


@dataclass(frozen=True)
class QueryResult:
    query: Query
    results: dict[str, SearchResult]


@dataclass(frozen=True)
class ProviderStats:
    avg_latency_ms: int | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    latency_p99_ms: int | None
    total_cost_usd: float
    errors: int
    timeouts: int


@dataclass(frozen=True)
class RunResult:
    started_at: str
    duration_s: float
    query_count: int
    providers: list[str]
    results: list[QueryResult]
    provider_stats: dict[str, ProviderStats]


async def run_benchmark(
    providers: Iterable[Provider],
    queries: Iterable[Query],
    settings: Settings,
) -> RunResult:
    providers_list = list(providers)
    queries_list = list(queries)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()

    semaphore = asyncio.Semaphore(max(1, DEFAULT_QUERY_CONCURRENCY))

    async def run_query(query: Query) -> QueryResult:
        async with semaphore:
            tasks = []
            for provider in providers_list:
                timeout = timeout_for(provider.name, settings)
                tasks.append(_run_provider(provider, query, timeout))
            provider_results = await asyncio.gather(*tasks)
            return QueryResult(
                query=query,
                results={res_key: res for res_key, res in provider_results},
            )

    results = list(await asyncio.gather(*(run_query(query) for query in queries_list)))

    duration_s = time.perf_counter() - started
    provider_stats = _summarize_provider_stats(results, providers_list)
    return RunResult(
        started_at=started_at,
        duration_s=duration_s,
        query_count=len(queries_list),
        providers=[p.name for p in providers_list],
        results=results,
        provider_stats=provider_stats,
    )


async def _run_provider(
    provider: Provider,
    query: Query,
    timeout: int,
) -> tuple[str, SearchResult]:
    try:
        result = await provider.search(query.text, timeout=timeout)
    except Exception as exc:  # Defensive: provider should capture errors internally.
        result = SearchResult(
            answer="",
            citations=[],
            latency_ms=0,
            cost_usd=0.0,
            raw_response={"error": str(exc)},
            error=str(exc),
            timed_out=False,
        )
    return provider.name, result


def _summarize_provider_stats(
    results: Iterable[QueryResult],
    providers: Iterable[Provider],
) -> dict[str, ProviderStats]:
    stats: dict[str, ProviderStats] = {}
    providers_list = list(providers)
    for provider in providers_list:
        latencies = []
        errors = 0
        timeouts = 0
        total_cost = 0.0
        for item in results:
            res = item.results.get(provider.name)
            if not res:
                continue
            if res.error:
                errors += 1
            if res.timed_out:
                timeouts += 1
            if res.error is None:
                latencies.append(res.latency_ms)
            total_cost += res.cost_usd
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else None
        stats[provider.name] = ProviderStats(
            avg_latency_ms=avg_latency,
            latency_p50_ms=_percentile(latencies, 50),
            latency_p95_ms=_percentile(latencies, 95),
            latency_p99_ms=_percentile(latencies, 99),
            total_cost_usd=round(total_cost, 6),
            errors=errors,
            timeouts=timeouts,
        )
    return stats


def _percentile(values: list[int], percentile: int) -> int | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (percentile / 100)
    lower = sorted_vals[int(math.floor(k))]
    upper = sorted_vals[int(math.ceil(k))]
    if lower == upper:
        return lower
    return int(lower + (upper - lower) * (k - math.floor(k)))
