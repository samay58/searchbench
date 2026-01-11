import asyncio
import json
import os
from pathlib import Path
from typing import Iterable

import typer

from searchbench.calibrate import load_history, suggest_timeouts, update_config_timeouts
from searchbench.config import load_settings, timeout_for, DEFAULT_CONFIG_PATH
from searchbench.judge import Judge, grade_run
from searchbench.providers import create_provider, list_providers
from searchbench.queries import load_queries, sample_queries
from searchbench.reporter import write_report, build_provider_summaries, build_error_breakdown
from searchbench.runner import run_benchmark


app = typer.Typer(help="Honest benchmarks for agentic search APIs")

PROVIDER_ENV = {
    "exa": "EXA_API_KEY",
    "parallel": "PARALLEL_API_KEY",
    "brave": "BRAVE_API_KEY",
    "linkup": "LINKUP_API_KEY",
    "tavily": "TAVILY_API_KEY",
}


@app.command()
def run(
    providers: str = typer.Option("all", help="Comma-separated: exa,parallel,brave,linkup,tavily"),
    queries: str = typer.Option("public", help="Query set: public, private, or path"),
    output: str = typer.Option("results/", help="Output directory"),
) -> None:
    settings = load_settings()
    provider_names = _parse_providers(providers)
    provider_instances = _init_providers(provider_names)
    query_list = load_queries(queries)

    judge = Judge()
    asyncio.run(judge.preflight())

    run_result = asyncio.run(run_benchmark(provider_instances, query_list, settings))
    graded = asyncio.run(grade_run(judge, run_result))

    provider_meta = {
        provider.name: {
            "endpoint": getattr(provider, "endpoint", None),
            "timeout": timeout_for(provider.name, settings),
        }
        for provider in provider_instances
    }
    summaries = build_provider_summaries(graded, provider_meta)
    _echo_summary_table(summaries)
    error_breakdown = build_error_breakdown(graded.run)
    _echo_error_table(_error_rows_from_summaries(summaries, error_breakdown))
    report_paths = write_report(
        graded=graded,
        query_set=queries,
        judge_model=judge.model,
        provider_meta=provider_meta,
        output_dir=Path(output),
        summaries=summaries,
    )
    typer.echo(f"Report written to {report_paths.latest}")


@app.command()
def quick(
    providers: str = typer.Option("all", help="Comma-separated provider names"),
    queries: str = typer.Option("public", help="Query set: public, private, or path"),
) -> None:
    settings = load_settings()
    provider_names = _parse_providers(providers)
    provider_instances = _init_providers(provider_names)
    query_list = sample_queries(load_queries(queries), 10)

    judge = Judge()
    asyncio.run(judge.preflight())
    run_result = asyncio.run(run_benchmark(provider_instances, query_list, settings))
    graded = asyncio.run(grade_run(judge, run_result))

    provider_meta = {
        provider.name: {
            "endpoint": getattr(provider, "endpoint", None),
            "timeout": timeout_for(provider.name, settings),
        }
        for provider in provider_instances
    }
    summaries = build_provider_summaries(graded, provider_meta)
    _echo_summary_table(summaries)
    error_breakdown = build_error_breakdown(graded.run)
    _echo_error_table(_error_rows_from_summaries(summaries, error_breakdown))
    report_paths = write_report(
        graded=graded,
        query_set=queries,
        judge_model=judge.model,
        provider_meta=provider_meta,
        output_dir=settings.results_dir,
        summaries=summaries,
    )
    typer.echo(f"Quick report written to {report_paths.latest}")


@app.command()
def history(last: int = typer.Option(10, help="Number of recent runs to show")) -> None:
    settings = load_settings()
    history_path = settings.results_dir / "history.json"
    data = load_history(history_path)
    runs = data.get("runs", [])[-last:]
    if not runs:
        typer.echo("No history yet.")
        raise typer.Exit()
    for run in runs:
        date = run.get("date", "unknown")
        n_queries = run.get("n_queries", "?")
        query_set = run.get("query_set", "?")
        providers = ", ".join(sorted(run.get("results", {}).keys()))
        typer.echo(f"{date} | {query_set} | {n_queries} queries | {providers}")



@app.command()
def summary() -> None:
    settings = load_settings()
    history_path = settings.results_dir / "history.json"
    data = load_history(history_path)
    runs = data.get("runs", [])
    if not runs:
        typer.echo("No history yet.")
        raise typer.Exit()
    latest = runs[-1]
    results = latest.get("results", {})
    if not results:
        typer.echo("No provider results found.")
        raise typer.Exit()
    header = (
        f"{latest.get('date', 'unknown')} | {latest.get('query_set', '?')} | "
        f"{latest.get('n_queries', '?')} queries"
    )
    typer.echo(header)
    rows = _summary_rows_from_history(results)
    typer.echo(_render_table(SUMMARY_HEADERS, rows))
    error_breakdown = latest.get("error_breakdown", {})
    if isinstance(error_breakdown, dict) and error_breakdown:
        error_rows = _error_rows_from_history(results, error_breakdown)
        _echo_error_table(error_rows)


@app.command()
def validate() -> None:
    missing = []
    for provider, env_var in PROVIDER_ENV.items():
        if not os.getenv(env_var):
            missing.append(f"{provider}: {env_var}")
    if missing:
        typer.echo("Missing API keys:")
        for entry in missing:
            typer.echo(f"  - {entry}")
    else:
        typer.echo("All provider API keys present.")

    try:
        judge = Judge()
        asyncio.run(judge.preflight())
        typer.echo("Judge preflight: OK")
    except Exception as exc:
        typer.echo(f"Judge preflight: FAILED ({exc})")


@app.command()
def providers() -> None:
    for provider in list_providers():
        env_var = PROVIDER_ENV.get(provider, "UNKNOWN")
        status = "set" if os.getenv(env_var) else "missing"
        typer.echo(f"{provider} ({env_var}): {status}")


@app.command()
def report(
    no_open: bool = typer.Option(
        False, "--no-open", is_flag=True, help="Do not open latest report in browser"
    )
) -> None:
    settings = load_settings()
    latest = settings.results_dir / "latest.html"
    if not latest.exists():
        typer.echo("No report found. Run `searchbench run` first.")
        raise typer.Exit(code=1)
    typer.echo(f"Latest report: {latest}")
    if not no_open:
        import webbrowser

        webbrowser.open(latest.as_uri())


@app.command()
def add(
    query: str,
    category: str = typer.Option("custom", help="Category for the private query"),
    notes: str = typer.Option("", help="Optional notes for judging"),
) -> None:
    private_path = Path(__file__).parent / "queries" / "private.json"
    if private_path.exists():
        data = json.loads(private_path.read_text())
    else:
        data = {"queries": []}
    entries = data.get("queries", [])
    next_id = f"private_{len(entries) + 1:02d}"
    entries.append(
        {
            "id": next_id,
            "query": query,
            "expected": None,
            "category": category,
            "notes": notes or None,
        }
    )
    data["queries"] = entries
    private_path.write_text(json.dumps(data, indent=2))
    typer.echo(f"Added private query as {next_id}")


@app.command()
def calibrate(
    apply: bool = typer.Option(False, "--apply", is_flag=True, help="Apply suggested timeouts to config.toml")
) -> None:
    settings = load_settings()
    history_path = settings.results_dir / "history.json"
    history = load_history(history_path)
    suggestions = suggest_timeouts(history)

    if not suggestions:
        typer.echo("No timeout suggestions available.")
        raise typer.Exit()

    current = load_settings().timeouts
    changes = {k: v for k, v in suggestions.items() if current.get(k) != v}
    if not changes:
        typer.echo("All timeouts are well-calibrated.")
        raise typer.Exit()

    for provider, value in changes.items():
        typer.echo(f"{provider}: {current.get(provider)}s -> {value}s")
    if apply:
        update_config_timeouts(DEFAULT_CONFIG_PATH, {**current, **changes})
        typer.echo("config.toml updated.")
    else:
        typer.echo("Run with --apply to update config.toml.")



SUMMARY_HEADERS = ["Provider", "Accuracy", "Avg Latency", "Total Cost", "Errors", "Timeouts"]
ERROR_HEADERS = ["Provider", "Errors", "Timeouts", "Top Error"]


def _echo_error_table(rows: list[list[str]]) -> None:
    if not rows:
        return
    typer.echo("Errors")
    typer.echo(_render_table(ERROR_HEADERS, rows))


def _echo_summary_table(summaries) -> None:
    table = _format_summary_table(summaries)
    if not table:
        return
    typer.echo("Summary")
    typer.echo(table)


def _format_summary_table(summaries) -> str:
    rows = _summary_rows_from_summaries(summaries)
    return _render_table(SUMMARY_HEADERS, rows)


def _summary_rows_from_summaries(summaries) -> list[list[str]]:
    rows = []
    for summary in summaries:
        rows.append(
            [
                summary.name.title(),
                _format_pct(summary.accuracy),
                _format_latency(summary.avg_latency_ms),
                _format_cost(summary.total_cost_usd),
                str(summary.errors),
                str(summary.timeouts),
            ]
        )
    return rows


def _error_rows_from_summaries(summaries, error_breakdown: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    for summary in summaries:
        if summary.errors == 0 and summary.timeouts == 0:
            continue
        top = _format_top_error(error_breakdown.get(summary.name, []))
        rows.append([summary.name.title(), str(summary.errors), str(summary.timeouts), top])
    return rows


def _error_rows_from_history(results: dict, error_breakdown: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    for provider, stats in results.items():
        if not isinstance(stats, dict):
            continue
        errors = int(stats.get("errors", 0))
        timeouts = int(stats.get("timeouts", 0))
        if errors == 0 and timeouts == 0:
            continue
        top = _format_top_error(error_breakdown.get(provider, []))
        rows.append([provider.title(), str(errors), str(timeouts), top])
    return rows


def _format_top_error(samples: list[dict]) -> str:
    if not samples:
        return "-"
    top = samples[0]
    message = str(top.get("error", "-"))
    count = top.get("count")
    if isinstance(count, int):
        return f"{_truncate_cell(message)} ({count})"
    return _truncate_cell(message)


def _truncate_cell(text: str, limit: int = 60) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."



def _summary_rows_from_history(results: dict) -> list[list[str]]:
    items = sorted(
        results.items(),
        key=lambda item: item[1].get("accuracy", 0) if isinstance(item[1], dict) else 0,
        reverse=True,
    )
    rows = []
    for provider, stats in items:
        if not isinstance(stats, dict):
            continue
        rows.append(
            [
                provider.title(),
                _format_pct(stats.get("accuracy", 0.0)),
                _format_latency(stats.get("avg_latency_ms")),
                _format_cost(stats.get("total_cost_usd", 0.0)),
                str(stats.get("errors", 0)),
                str(stats.get("timeouts", 0)),
            ]
        )
    return rows


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def format_row(row: list[str], header: bool = False) -> str:
        cells = []
        for idx, cell in enumerate(row):
            if idx == 0 or header:
                cells.append(cell.ljust(widths[idx]))
            else:
                cells.append(cell.rjust(widths[idx]))
        return " | ".join(cells)

    lines = [format_row(headers, header=True), "-+-".join("-" * w for w in widths)]
    lines.extend(format_row(row) for row in rows)
    return "\n".join(lines)


def _format_pct(value: float | int) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "-"


def _format_latency(ms: int | float | None) -> str:
    if ms in (None, ""):
        return "-"
    try:
        return f"{float(ms) / 1000:.1f}s"
    except (TypeError, ValueError):
        return "-"


def _format_cost(value: float | int | None) -> str:
    if value in (None, ""):
        return "$0.00"
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return "$0.00"



def _parse_providers(raw: str) -> list[str]:
    available = set(list_providers())
    if raw.strip().lower() == "all":
        return sorted(available)
    names = [p.strip() for p in raw.split(",") if p.strip()]
    unknown = [name for name in names if name not in available]
    if unknown:
        raise typer.BadParameter(f"Unknown providers: {', '.join(unknown)}")
    return names


def _init_providers(names: Iterable[str]):
    providers = []
    for name in names:
        providers.append(create_provider(name))
    return providers


if __name__ == "__main__":
    app()
