from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


QUERY_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    expected: list[str] | None
    category: str
    notes: str | None = None


def load_queries(query_set: str | Path) -> list[Query]:
    path = _resolve_query_path(query_set)
    data = json.loads(path.read_text())
    raw_queries = data.get("queries", [])
    if not isinstance(raw_queries, list):
        raise ValueError(f"Invalid query file: {path} (queries must be a list)")

    queries: list[Query] = []
    for idx, item in enumerate(raw_queries, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid query entry at index {idx} in {path}")
        text = item.get("query")
        if not text:
            raise ValueError(f"Missing query text at index {idx} in {path}")
        expected = _normalize_expected(item.get("expected"))
        category = item.get("category", "general")
        query_id = item.get("id") or f"{category}_{idx:02d}"
        notes = item.get("notes")
        queries.append(
            Query(
                id=str(query_id),
                text=str(text),
                expected=expected,
                category=str(category),
                notes=str(notes) if notes else None,
            )
        )
    return queries


def sample_queries(queries: Iterable[Query], count: int) -> list[Query]:
    pool = list(queries)
    if count >= len(pool):
        return pool
    return random.sample(pool, count)


def _resolve_query_path(query_set: str | Path) -> Path:
    if isinstance(query_set, Path):
        path = query_set
    else:
        lowered = str(query_set).strip().lower()
        if lowered in {"public", "private"}:
            path = QUERY_DIR / f"{lowered}.json"
        else:
            path = Path(query_set)
    if not path.exists():
        hint = "Use 'public', 'private', or a JSON path."
        if str(path).endswith("private.json"):
            hint = "Create it from searchbench/queries/private.json.template."
        raise FileNotFoundError(f"Query set not found: {path}. {hint}")
    return path


def _normalize_expected(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        return [value]
    return [str(value)]
