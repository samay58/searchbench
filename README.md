# SearchBench - Honest benchmarks for agentic search APIs

SearchBench is a lean, opinionated benchmark for evaluating search APIs with strict, comparable settings. It answers one question: **which provider performs best for real-world research today?**

## What it does
- **Strict provider modes** - no fallbacks, no escalation, one mode per API.
- **Curated queries** - 50 public questions + a private, gitignored set.
- **Bias-mitigated judging** - GPT-4o-mini with preflight and fallback grading.
- **Shareable reports** - static HTML output with history tracking.
- **Adaptive timeouts** - data-driven calibration from prior runs.

## Quickstart
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt

cp .env.example .env
# Add your API keys

./scripts/searchbench run
# Optional: install CLI entrypoint
# . .venv/bin/activate
# python3 -m pip install -e .
# searchbench run
```

## Core commands
```bash
./scripts/searchbench run
./scripts/searchbench quick
./scripts/searchbench history
./scripts/searchbench summary
./scripts/searchbench validate
./scripts/searchbench report
./scripts/searchbench calibrate
```

## Query sets
- `searchbench/queries/public.json` - 50 curated, verifiable questions.
- `searchbench/queries/private.json` - personal set (gitignored). Copy from `searchbench/queries/private.json.template`.

## Results
Reports and history are written to:
- `results/latest.html`
- `results/<YYYY-MM-DD>.html`
- `results/history.json`

## Pricing (January 2025)
| Provider | Cost/Query | Free Tier | Notes |
| --- | --- | --- | --- |
| Exa (/answer) | $0.01 | $10 credits | Search + answer |
| Parallel | $0.005 | 16,000 queries | Strict v1beta search |
| Brave | $0.005 | 2,000/month | AI summary enabled |
| Linkup | ~$0.0055 | Free tier | Standard mode |
| Tavily | $0.008 paid | 1,000/month | Basic search |

## Configuration
Timeouts live in `config.toml` and can be recalibrated from history:
```bash
./scripts/searchbench calibrate
./scripts/searchbench calibrate --apply
```

## Tests
```bash
./.venv/bin/python -m unittest discover -s tests
```
