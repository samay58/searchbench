from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchResult:
    answer: str
    citations: list[str]
    latency_ms: int
    cost_usd: float
    raw_response: dict
    error: Optional[str] = None
    timed_out: bool = False


class Provider(ABC):
    name: str
    cost_per_query: float

    @abstractmethod
    async def search(self, query: str, timeout: int) -> SearchResult:
        """Execute search with the given timeout and return a structured result."""
        raise NotImplementedError
