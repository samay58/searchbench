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
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp .env.example .env
# Add your API keys

searchbench run
```

## Core commands
```bash
searchbench run
searchbench quick
searchbench history
searchbench summary
searchbench validate
searchbench report
searchbench calibrate
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
searchbench calibrate
searchbench calibrate --apply
```

## Tests
```bash
python -m unittest
```
