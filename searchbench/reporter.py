from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from searchbench.judge import GradedRun
from searchbench.runner import RunResult


@dataclass(frozen=True)
class ProviderSummary:
    name: str
    accuracy: float
    avg_latency_ms: int | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    latency_p99_ms: int | None
    total_cost_usd: float
    errors: int
    timeouts: int
    endpoint: str | None
    timeout_used: int | None
    evidence_pass_rate: float | None


@dataclass(frozen=True)
class ReportPaths:
    latest: Path
    dated: Path
    history: Path


def write_report(
    graded: GradedRun,
    query_set: str,
    judge_model: str,
    provider_meta: dict[str, dict[str, object]],
    output_dir: Path,
    summaries: list[ProviderSummary] | None = None,
    evidence_mode: str = "strict",
) -> ReportPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    summaries = summaries or build_provider_summaries(graded, provider_meta)
    history_path = output_dir / "history.json"
    history = _load_history(history_path)
    history.setdefault("runs", [])
    history.setdefault("timeout_events", [])
    history_entry, timeout_events = build_history_entry(
        graded, query_set, judge_model, summaries, evidence_mode
    )
    history["runs"].append(history_entry)
    history["timeout_events"].extend(timeout_events)
    history_path.write_text(json.dumps(history, indent=2))

    html_text = render_html(graded, query_set, judge_model, summaries, history["runs"], evidence_mode)
    latest_path = output_dir / "latest.html"
    dated_path = output_dir / f"{date_str}.html"
    latest_path.write_text(html_text)
    dated_path.write_text(html_text)

    return ReportPaths(latest=latest_path, dated=dated_path, history=history_path)


def build_provider_summaries(
    graded: GradedRun,
    provider_meta: dict[str, dict[str, object]],
) -> list[ProviderSummary]:
    run = graded.run
    totals: dict[str, int] = {name: 0 for name in run.providers}
    passes: dict[str, int] = {name: 0 for name in run.providers}
    evidence_totals: dict[str, int] = {name: 0 for name in run.providers}
    evidence_passes: dict[str, int] = {name: 0 for name in run.providers}
    for item in graded.graded_queries:
        for provider_name, judgment in item.judgments.items():
            totals[provider_name] += 1
            if judgment.passed:
                passes[provider_name] += 1
            if judgment.evidence_passed is not None:
                evidence_totals[provider_name] += 1
                if judgment.evidence_passed:
                    evidence_passes[provider_name] += 1

    summaries: list[ProviderSummary] = []
    for provider_name in run.providers:
        stats = run.provider_stats.get(provider_name)
        accuracy = passes[provider_name] / totals[provider_name] if totals[provider_name] else 0.0
        meta = provider_meta.get(provider_name, {})
        summaries.append(
            ProviderSummary(
                name=provider_name,
                accuracy=accuracy,
                avg_latency_ms=stats.avg_latency_ms if stats else None,
                latency_p50_ms=stats.latency_p50_ms if stats else None,
                latency_p95_ms=stats.latency_p95_ms if stats else None,
                latency_p99_ms=stats.latency_p99_ms if stats else None,
                total_cost_usd=stats.total_cost_usd if stats else 0.0,
                errors=stats.errors if stats else 0,
                timeouts=stats.timeouts if stats else 0,
                endpoint=str(meta.get("endpoint")) if meta.get("endpoint") else None,
                timeout_used=int(meta["timeout"]) if meta.get("timeout") else None,
                evidence_pass_rate=(
                    (evidence_passes[provider_name] / evidence_totals[provider_name])
                    if evidence_totals[provider_name]
                    else None
                ),
            )
        )
    return sorted(summaries, key=lambda s: s.accuracy, reverse=True)




def build_error_breakdown(run: RunResult) -> dict[str, list[dict]]:
    errors: dict[str, dict[str, int]] = {}
    for item in run.results:
        for provider_name, response in item.results.items():
            if not response.error:
                continue
            key = _normalize_error_message(str(response.error))
            errors.setdefault(provider_name, {})
            errors[provider_name][key] = errors[provider_name].get(key, 0) + 1

    breakdown: dict[str, list[dict]] = {}
    for provider_name, counts in errors.items():
        if not counts:
            continue
        sorted_items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        breakdown[provider_name] = [
            {"error": error, "count": count} for error, count in sorted_items[:3]
        ]
    return breakdown


def _normalize_error_message(message: str, limit: int = 120) -> str:
    cleaned = " ".join(message.split())
    if "timeout" in cleaned.lower():
        return "timeout"
    if len(cleaned) > limit:
        return cleaned[: limit - 3].rstrip() + "..."
    return cleaned or "unknown error"

def build_history_entry(
    graded: GradedRun,
    query_set: str,
    judge_model: str,
    summaries: Iterable[ProviderSummary],
    evidence_mode: str,
) -> tuple[dict, list[dict]]:
    run = graded.run
    timeout_lookup = {summary.name: summary.timeout_used for summary in summaries}
    entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "query_set": query_set,
        "n_queries": run.query_count,
        "judge_model": judge_model,
        "evidence_mode": evidence_mode,
        "results": {},
    }
    for summary in summaries:
        entry["results"][summary.name] = {
            "accuracy": round(summary.accuracy, 4),
            "avg_latency_ms": summary.avg_latency_ms,
            "latency_p50_ms": summary.latency_p50_ms,
            "latency_p95_ms": summary.latency_p95_ms,
            "latency_p99_ms": summary.latency_p99_ms,
            "total_cost_usd": round(summary.total_cost_usd, 6),
            "errors": summary.errors,
            "timeouts": summary.timeouts,
            "endpoint": summary.endpoint or "",
            "timeout_used": summary.timeout_used,
            "evidence_pass_rate": (round(summary.evidence_pass_rate, 4)
                                     if summary.evidence_pass_rate is not None else None),
        }

    entry["error_breakdown"] = build_error_breakdown(run)

    timeout_events = []
    for item in graded.graded_queries:
        for provider_name, response in item.responses.items():
            if response.timed_out:
                timeout_events.append(
                    {
                        "date": entry["date"],
                        "provider": provider_name,
                        "query_id": item.query.id,
                        "timeout_used": timeout_lookup.get(provider_name),
                        "query_length": len(item.query.text),
                    }
                )
    return entry, timeout_events


def render_html(
    graded: GradedRun,
    query_set: str,
    judge_model: str,
    summaries: list[ProviderSummary],
    history_runs: list[dict],
    evidence_mode: str,
) -> str:
    run = graded.run
    winner = summaries[0].name if summaries else None
    safe = html.escape

    show_evidence = any(summary.evidence_pass_rate is not None for summary in summaries)
    evidence_header = "<th>Evidence Pass</th>" if show_evidence else ""

    summary_rows = []
    for summary in summaries:
        cls = "winner" if summary.name == winner else ""
        evidence_cell = (
            f"<td>{_format_pct_or_dash(summary.evidence_pass_rate)}</td>"
            if show_evidence
            else ""
        )
        summary_rows.append(
            f"<tr class=\"{cls}\">"
            f"<td>{safe(summary.name.title())}</td>"
            f"<td>{_format_pct(summary.accuracy)}</td>"
            f"<td>{_format_latency(summary.avg_latency_ms)}</td>"
            + evidence_cell
            + f"<td>{_format_cost(summary.total_cost_usd)}</td>"
            f"<td>{summary.errors}</td>"
            f"</tr>"
        )

    trend_rows = []

    for summary in summaries:
        trend_rows.append(
            "<div class=\"trend\">"
            f"<div class=\"trend-name\">{safe(summary.name.title())}</div>"
            f"{_sparkline(_history_values(history_runs, summary.name))}"
            f"<div class=\"trend-score\">{_format_pct(summary.accuracy)}</div>"
            "</div>"
        )

    detail_cards = []
    for item in graded.graded_queries:
        provider_rows = []
        for provider_name in run.providers:
            response = item.responses.get(provider_name)
            judgment = item.judgments.get(provider_name)
            verdict = judgment.label if judgment else "unknown"
            verdict_class = "verdict-" + verdict
            answer = response.answer if response else ""
            provider_rows.append(
                "<div class=\"answer-row\">"
                f"<div class=\"provider\">{safe(provider_name.title())}</div>"
                f"<div class=\"verdict {verdict_class}\">{safe(verdict.upper())}</div>"
                f"<div class=\"answer\">{safe(_truncate(answer, 220))}</div>"
                "</div>"
            )
        evidence_text = _format_evidence(item.query.evidence)
        evidence_html = f"<div class=\"evidence\">{safe(evidence_text)}</div>" if evidence_text else ""
        detail_cards.append(
            "<div class=\"query-card\">"
            "<div class=\"query-meta\">"
            f"<span class=\"qid\">{safe(item.query.id)}</span>"
            f"<span class=\"category\">{safe(item.query.category)}</span>"
            "</div>"
            f"<div class=\"query-text\">{safe(item.query.text)}</div>"
            f"<div class=\"expected\">Expected: {safe('; '.join(item.query.expected or ['None']))}</div>"
            + evidence_html
            + "<div class=\"answers\">"
            + "".join(provider_rows)
            + "</div>"
            "</div>"
        )

    has_evidence = any(item.query.evidence for item in graded.graded_queries)
    methodology = (
        f"This benchmark ran {run.query_count} curated questions across {len(run.providers)} providers. "
        f"Answers were graded by {judge_model} using binary correct/incorrect scoring with semantic equivalence. "
        "Latency is measured from request initiation to response completion. Costs are calculated using published "
        "pricing as of the report date."
    )
    if has_evidence and evidence_mode != "off":
        methodology += f" Evidence mode: {evidence_mode}."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SearchBench Results - {safe(datetime.now(timezone.utc).strftime('%Y-%m-%d'))}</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --panel: #121826;
      --panel-2: #0f141f;
      --border: #273044;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #f97316;
      --success: #22c55e;
      --warning: #eab308;
      --error: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino", "Georgia", "Times New Roman", serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1b2436 0, transparent 60%),
                  linear-gradient(180deg, #0b0f14 0%, #0a0d12 100%);
      color: var(--text);
      line-height: 1.6;
    }}
    header {{
      padding: 3.5rem 1.5rem 2rem;
      text-align: center;
    }}
    header h1 {{
      font-family: "Gill Sans", "Trebuchet MS", "Verdana", sans-serif;
      letter-spacing: 0.04em;
      margin-bottom: 0.4rem;
      font-size: clamp(2rem, 3vw, 3rem);
    }}
    header p {{
      color: var(--muted);
      margin: 0;
    }}
    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 0 1.5rem 3rem;
    }}
    section {{
      margin-bottom: 2.5rem;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 1.5rem;
      box-shadow: 0 20px 40px rgba(0,0,0,0.25);
    }}
    h2 {{
      font-family: "Gill Sans", "Trebuchet MS", "Verdana", sans-serif;
      margin-top: 0;
      font-size: 1.4rem;
      letter-spacing: 0.02em;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      padding: 0.75rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.95rem;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
    tr.winner td:first-child {{
      color: var(--accent);
      font-weight: 700;
    }}
    .trends {{
      display: grid;
      gap: 1rem;
    }}
    .trend {{
      display: grid;
      grid-template-columns: 140px 1fr 80px;
      align-items: center;
      gap: 1rem;
      background: var(--panel-2);
      padding: 0.75rem 1rem;
      border-radius: 12px;
      border: 1px solid var(--border);
    }}
    .trend-name {{
      font-family: "Gill Sans", "Trebuchet MS", "Verdana", sans-serif;
      font-size: 0.95rem;
      letter-spacing: 0.03em;
    }}
    .trend-score {{
      text-align: right;
      font-weight: 600;
    }}
    .query-card {{
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1rem;
      margin-bottom: 1rem;
    }}
    .query-meta {{
      display: flex;
      gap: 0.75rem;
      font-size: 0.85rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 0.5rem;
    }}
    .query-text {{
      font-weight: 600;
      margin-bottom: 0.35rem;
    }}
    .expected {{
      font-size: 0.9rem;
      color: var(--muted);
      margin-bottom: 0.35rem;
    }}
    .evidence {{
      font-size: 0.85rem;
      color: var(--muted);
      margin-bottom: 0.75rem;
    }}
    .answers {{
      display: grid;
      gap: 0.5rem;
    }}
    .answer-row {{
      display: grid;
      grid-template-columns: 110px 110px 1fr;
      gap: 0.75rem;
      align-items: start;
      padding: 0.5rem 0.75rem;
      border-radius: 10px;
      background: rgba(15, 19, 32, 0.8);
      border: 1px solid transparent;
    }}
    .provider {{
      font-weight: 600;
    }}
    .verdict {{
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .verdict-correct, .verdict-plausible {{
      color: var(--success);
    }}
    .verdict-incorrect, .verdict-implausible {{
      color: var(--error);
    }}
    .verdict-unknown {{
      color: var(--warning);
    }}
    .answer {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    details summary {{
      cursor: pointer;
      font-weight: 600;
    }}
    footer {{
      text-align: center;
      color: var(--muted);
      padding-bottom: 2.5rem;
    }}
    @media (max-width: 720px) {{
      .trend {{
        grid-template-columns: 1fr;
        text-align: left;
      }}
      .trend-score {{
        text-align: left;
      }}
      .answer-row {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>SearchBench Results</h1>
    <p>{safe(datetime.now(timezone.utc).strftime('%Y-%m-%d'))} | {run.query_count} queries | {len(run.providers)} providers | {safe(query_set)}</p>
  </header>
  <main>
    <section>
      <h2>Summary</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Provider</th>
              <th>Accuracy</th>
              <th>Avg Latency</th>
              {evidence_header}
              <th>Total Cost</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody>
            {''.join(summary_rows)}
          </tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>Performance Over Time</h2>
      <div class="trends">
        {''.join(trend_rows) if trend_rows else '<p class="muted">No history yet.</p>'}
      </div>
    </section>
    <section>
      <h2>Methodology</h2>
      <p>{safe(methodology)}</p>
      <details>
        <summary>Provider configurations</summary>
        <ul>
          {''.join(_provider_config_items(summaries))}
        </ul>
      </details>
    </section>
    <section>
      <h2>Query Details</h2>
      <details>
        <summary>Show all {run.query_count} results</summary>
        {''.join(detail_cards)}
      </details>
    </section>
  </main>
  <footer>
    Generated by SearchBench
  </footer>
</body>
</html>
"""


def _load_history(path: Path) -> dict:
    if not path.exists():
        return {"runs": [], "timeout_events": []}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"runs": [], "timeout_events": []}


def _provider_config_items(summaries: Iterable[ProviderSummary]) -> list[str]:
    items = []
    for summary in summaries:
        endpoint = summary.endpoint or "unknown"
        timeout = f"{summary.timeout_used}s" if summary.timeout_used else "default"
        items.append(
            "<li><strong>"
            + html.escape(summary.name.title())
            + ":</strong> "
            + html.escape(endpoint)
            + ", "
            + html.escape(timeout)
            + "</li>"
        )
    return items




def _format_evidence(evidence) -> str:
    if not evidence:
        return ""
    parts = []
    if evidence.min_citations:
        parts.append(f"min {evidence.min_citations} citations")
    if evidence.required_domains:
        parts.append("domains: " + ", ".join(evidence.required_domains))
    if evidence.required_sources:
        parts.append("sources: " + ", ".join(evidence.required_sources))
    if not parts:
        return ""
    return "Evidence: " + "; ".join(parts)

def _format_pct_or_dash(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.0f}%"


def _format_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _format_latency(ms: int | None) -> str:
    if ms is None:
        return "-"
    return f"{ms / 1000:.1f}s"


def _format_cost(value: float) -> str:
    return f"${value:.2f}"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _history_values(history_runs: list[dict], provider_name: str) -> list[float]:
    values = []
    for run in history_runs:
        result = run.get("results", {}).get(provider_name)
        if result and isinstance(result.get("accuracy"), (float, int)):
            values.append(float(result["accuracy"]))
    return values


def _sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return "<div class=\"sparkline\">Not enough history</div>"
    width = 140
    height = 36
    min_val = min(values)
    max_val = max(values)
    span = max(max_val - min_val, 1e-6)
    points = []
    for idx, value in enumerate(values):
        x = idx * (width / (len(values) - 1))
        y = height - ((value - min_val) / span * (height - 6)) - 3
        points.append((x, y))
    path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f"<svg class=\"sparkline\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\" "
        "fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\">"
        f"<path d=\"{path}\" stroke=\"#f97316\" stroke-width=\"2\" fill=\"none\" />"
        "</svg>"
    )
