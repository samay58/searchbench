from __future__ import annotations

import json
import math
from pathlib import Path

from searchbench.config import DEFAULT_TIMEOUTS


def load_history(history_path: Path) -> dict:
    if not history_path.exists():
        return {"runs": []}
    try:
        return json.loads(history_path.read_text())
    except Exception:
        return {"runs": []}


def suggest_timeouts(history: dict) -> dict[str, int]:
    suggestions: dict[str, int] = {}
    runs = history.get("runs", [])

    for provider, default in DEFAULT_TIMEOUTS.items():
        samples = []
        for run in runs:
            result = run.get("results", {}).get(provider)
            if not result:
                continue
            p99 = result.get("latency_p99_ms")
            if isinstance(p99, (int, float)) and p99 > 0:
                samples.append(float(p99))
        if len(samples) < 10:
            suggestions[provider] = default
            continue
        p99 = _percentile(samples, 99)
        suggested = int((p99 * 1.2) / 1000)
        suggestions[provider] = max(15, min(60, suggested))
    return suggestions


def update_config_timeouts(config_path: Path, updates: dict[str, int]) -> None:
    lines = config_path.read_text().splitlines() if config_path.exists() else []
    start = None
    end = None
    for idx, line in enumerate(lines):
        if line.strip() == "[timeouts]":
            start = idx
            continue
        if start is not None and line.strip().startswith("[") and line.strip().endswith("]"):
            end = idx
            break
    if start is None:
        lines.extend(["", "[timeouts]"])
        start = len(lines) - 1
        end = len(lines)
    if end is None:
        end = len(lines)

    ordered_keys = list(DEFAULT_TIMEOUTS.keys())
    ordered_keys += [k for k in updates.keys() if k not in ordered_keys]
    block = ["[timeouts]"] + [f"{key} = {int(updates[key])}" for key in ordered_keys if key in updates]
    lines = lines[:start] + block + lines[end:]
    config_path.write_text("\n".join(lines).rstrip() + "\n")


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (percentile / 100)
    lower = values[int(math.floor(k))]
    upper = values[int(math.ceil(k))]
    if lower == upper:
        return lower
    return lower + (upper - lower) * (k - math.floor(k))
