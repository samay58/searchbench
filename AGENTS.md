# Repository Guidelines

## Project Structure & Module Organization
`searchbench/cli.py` is the CLI entry point (installed as the `searchbench` command). Core logic lives in `searchbench/` (`providers/`, `runner.py`, `judge.py`, `queries/`, `reporter.py`). Reports and history are written to `results/`. Configuration templates live in `.env.example`, and timeouts in `config.toml`. Dependencies are pinned in `requirements.txt`.

## Build, Test, and Development Commands
- `./.venv/bin/python -m pip install -r requirements.txt` - install runtime dependencies.
- `./scripts/searchbench run` - full evaluation run using the public query set.
- `./scripts/searchbench run --queries hard` - run the hard, evidence-gated benchmark.
- `./scripts/searchbench quick` - 10-query smoke check.
- `./scripts/searchbench history` - list recent benchmark runs.
- `./scripts/searchbench summary` - show the latest run summary table.
- `./scripts/searchbench report` - open the latest HTML report.
- `./scripts/searchbench calibrate` - suggest timeouts from historical latency data.
- Optional: `python3 -m pip install -e .` to enable the `searchbench` CLI.

## Coding Style & Naming Conventions
Use 4-space indentation and standard Python naming: `snake_case` for functions and variables, `CapWords` for classes. Keep type hints where present and follow existing async patterns (`async def`, `await`). When adding providers, implement `Provider` from `searchbench/providers/base.py` and register via `@register`.

## Testing Guidelines
Run tests with `./.venv/bin/python -m unittest discover -s tests`. Validate changes with the CLI using `./scripts/searchbench quick` before running a full benchmark.

## Commit & Pull Request Guidelines
Commit messages are short and imperative; many use a lightweight scope prefix like `docs:` or `cli:`. For PRs, include a clear summary, commands run, and any new env vars added to `.env.example`. Attach a screenshot or pasted output for UI or visualization changes.

## Security & Configuration Tips
Store API keys in `.env` and never commit it. Keep `.env.example` and README up to date when adding new providers or settings. Use `config.toml` for timeout overrides.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
