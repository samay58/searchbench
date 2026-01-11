import asyncio
import json
import random
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import click
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
    providers: str = typer.Option("all", help="Comma-separated: exa,parallel,brave,linkup,tavily", is_flag=False),
    queries: str = typer.Option("public", help="Query set: public, hard, private, or path", is_flag=False),
    output: str = typer.Option("results/", help="Output directory", is_flag=False),
    evidence: str = typer.Option("strict", help="Evidence mode: strict, min, off", is_flag=False),
) -> None:
    settings = load_settings()
    provider_names = _parse_providers(providers)
    evidence_mode = _normalize_evidence_mode(evidence)
    provider_instances = _init_providers(provider_names)
    query_list = load_queries(queries)

    judge = Judge()
    asyncio.run(judge.preflight())

    run_result = asyncio.run(run_benchmark(provider_instances, query_list, settings))
    graded = asyncio.run(grade_run(judge, run_result, evidence_mode=evidence_mode))

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
        evidence_mode=evidence_mode,
    )
    typer.echo(f"Report written to {report_paths.latest}")


@app.command()
def quick(
    providers: str = typer.Option("all", help="Comma-separated provider names", is_flag=False),
    queries: str = typer.Option("public", help="Query set: public, hard, private, or path", is_flag=False),
    output: str = typer.Option("results/", help="Output directory", is_flag=False),
    evidence: str = typer.Option("strict", help="Evidence mode: strict, min, off", is_flag=False),
) -> None:
    settings = load_settings()
    provider_names = _parse_providers(providers)
    evidence_mode = _normalize_evidence_mode(evidence)
    provider_instances = _init_providers(provider_names)
    query_list = sample_queries(load_queries(queries), 10)

    judge = Judge()
    asyncio.run(judge.preflight())
    run_result = asyncio.run(run_benchmark(provider_instances, query_list, settings))
    graded = asyncio.run(grade_run(judge, run_result, evidence_mode=evidence_mode))

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
        evidence_mode=evidence_mode,
    )
    typer.echo(f"Quick report written to {report_paths.latest}")


@app.command()
def history(last: int = typer.Option(10, help="Number of recent runs to show", is_flag=False)) -> None:
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
    category: str = typer.Option("custom", help="Category for the private query", is_flag=False),
    notes: str = typer.Option("", help="Optional notes for judging", is_flag=False),
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
def debug(
    provider: str = typer.Option("exa", help="Provider name", is_flag=False),
    queries: str = typer.Option("hard", help="Query set: public, hard, private, or path", is_flag=False),
    count: int = typer.Option(5, help="Number of queries to sample", is_flag=False),
    output: str = typer.Option("results/debug-exa.json", help="Output JSON path", is_flag=False),
    seed: int = typer.Option(7, help="Random seed for sampling", is_flag=False),
) -> None:
    provider_name = provider.strip().lower()
    if provider_name not in list_providers():
        raise typer.BadParameter(f"Unknown provider: {provider}")

    settings = load_settings()
    random.seed(seed)
    query_list = sample_queries(load_queries(queries), count)
    provider_instance = create_provider(provider_name)
    timeout = timeout_for(provider_instance.name, settings)

    async def run_debug():
        results = []
        for query in query_list:
            response = await provider_instance.search(query.text, timeout=timeout)
            evidence_passed = None
            evidence_notes = None
            citation_domains = []
            if query.evidence:
                evidence_passed, evidence_notes = Judge._check_evidence(response.citations, query.evidence)
                citation_domains = sorted(Judge._extract_domains(response.citations))
            results.append(
                {
                    "id": query.id,
                    "query": query.text,
                    "expected": query.expected,
                    "category": query.category,
                    "evidence": {
                        "min_citations": query.evidence.min_citations if query.evidence else 0,
                        "required_domains": list(query.evidence.required_domains) if query.evidence else [],
                        "required_sources": list(query.evidence.required_sources) if query.evidence else [],
                    }
                    if query.evidence
                    else None,
                    "answer": response.answer,
                    "citations": response.citations,
                    "citation_domains": citation_domains,
                    "evidence_passed": evidence_passed,
                    "evidence_notes": evidence_notes,
                    "latency_ms": response.latency_ms,
                    "cost_usd": response.cost_usd,
                    "error": response.error,
                    "timed_out": response.timed_out,
                    "raw_response": response.raw_response,
                }
            )
        return results

    results = asyncio.run(run_debug())
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider_name,
        "query_set": queries,
        "count": len(results),
        "seed": seed,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, indent=2))

    errors = sum(1 for item in results if item.get("error"))
    evidence_total = sum(1 for item in results if item.get("evidence_passed") is not None)
    evidence_pass = sum(1 for item in results if item.get("evidence_passed") is True)
    typer.echo(f"Debug results written to {output_path}")
    typer.echo(f"Errors: {errors} | Evidence passed: {evidence_pass}/{evidence_total}")


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



SUMMARY_HEADERS = ["Provider", "Accuracy", "Avg Latency", "Evidence", "Total Cost", "Errors", "Timeouts"]
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
                _format_pct_or_dash(summary.evidence_pass_rate),
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
                _format_pct_or_dash(stats.get("evidence_pass_rate")),
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


def _format_pct_or_dash(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_pct(value)


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



def _normalize_evidence_mode(raw: str) -> str:
    value = (raw or "strict").strip().lower()
    if value in {"off", "none", "false", "0"}:
        return "off"
    if value in {"min", "minimum", "citations"}:
        return "min"
    if value in {"strict", "full"}:
        return "strict"
    raise typer.BadParameter("Evidence mode must be one of: strict, min, off")


def _parse_providers(raw: str) -> list[str]:
    available = set(list_providers())
    if raw.strip().lower() == "all":
        return sorted(available)
    names = [p.strip() for p in raw.split(",") if p.strip()]
    unknown = [name for name in names if name not in available]
    if unknown:
        raise typer.BadParameter(f"Unknown providers: {', '.join(unknown)}")
    return names


def _fix_click_flags(command: click.Command) -> None:
    if isinstance(command, click.Group):
        for subcommand in command.commands.values():
            _fix_click_flags(subcommand)
    for param in command.params:
        if not isinstance(param, click.Option):
            continue
        if isinstance(param.type, click.types.BoolParamType):
            continue
        if param.is_flag:
            param.is_flag = False
            param.count = False
            param.flag_value = None


def _patch_click_metavar() -> None:
    if getattr(click.Parameter.make_metavar, "_searchbench_patched", False):
        return
    original = click.Parameter.make_metavar

    def make_metavar(self: click.Parameter, ctx: click.Context | None = None) -> str:
        if ctx is None:
            ctx = click.Context(click.Command("searchbench"))
        return original(self, ctx)

    make_metavar._searchbench_patched = True  # type: ignore[attr-defined]
    click.Parameter.make_metavar = make_metavar  # type: ignore[assignment]


def _init_providers(names: Iterable[str]):
    providers = []
    for name in names:
        providers.append(create_provider(name))
    return providers


def main() -> None:
    _patch_click_metavar()
    command = typer.main.get_command(app)
    _fix_click_flags(command)
    command()


if __name__ == "__main__":
    main()
