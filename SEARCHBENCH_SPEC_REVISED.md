# SearchBench: Agentic Search API Benchmarking

## Transformation Spec: browse-comp-v2 → searchbench

**Author:** Samay Dhawan
**Revised by:** Claude (with web research verification)
**Date:** January 2025
**Status:** Ready for Review

---

## Revision Summary

This document is a revised version of the original spec. Key changes from the original:

| Section | Change | Rationale |
|---------|--------|-----------|
| Pricing | Updated all provider costs with verified 2025 data | Original estimates were outdated |
| Providers | Added Linkup, removed Perplexity from default set | Linkup is a serious contender; Perplexity is a different product category |
| Query Set | Increased from 30 to 50 questions | More statistical significance |
| Judge | Added bias mitigation recommendations | Research-backed best practices |
| Timeouts | **Adaptive system** with config.toml + calibrate command | User feedback: should be data-driven, not hardcoded guesses |
| Open Questions | Resolved with concrete decisions | Spec was ambiguous |

---

## Executive Summary

This document specifies the transformation of `browse-comp-v2` into `searchbench` — a lean, opinionated benchmarking tool for agentic search APIs. The goal is to answer one question definitively: **Which search API should I use for real-world research tasks?**

The original project over-engineered for generality. This revision optimizes for:
1. **Personal utility** — a tool that integrates into my workflow
2. **Honest comparison** — no fallbacks, no escalation, one mode per provider
3. **Temporal tracking** — performance over time, not just snapshots
4. **Publishable results** — clean enough to share on GitHub

---

## Part 1: What's Changing

### Identity

| Aspect | Old (browse-comp-v2) | New (searchbench) |
|--------|---------------------|-------------------|
| Name | browse-comp-v2 | searchbench |
| Repo | github.com/samay58/browse-comp-v2 | github.com/samay58/searchbench |
| Directory | ~/browse-comp-v2 | ~/searchbench |
| Tagline | "BrowseComp V2 benchmarking framework" | "Honest benchmarks for agentic search APIs" |
| Audience | Generic developers | Me, and anyone evaluating search APIs |

### Philosophy

**Old philosophy:** Build a generalizable evaluation harness with rich visualization, multiple query sets, and flexible provider configurations.

**New philosophy:** Build the simplest thing that answers "which API is best right now?" with enough rigor to trust the answer.

### What's Being Cut

| Component | Reason for Removal |
|-----------|-------------------|
| BrowseComp dataset download + XOR decryption | Replaced with curated query sets |
| "basic" query set (2+2) | Adds nothing; preflight check validates pipeline |
| Exa `/answer` → `/research` auto-escalation | Conflates two products; benchmark one mode |
| Parallel → Tavily silent fallback | Dishonest benchmarking; strict mode only |
| Rich terminal visualizer | Replaced with HTML report |
| Topic breakdown | Dashboard theater; not actionable |
| Confidence calibration | Academic; doesn't inform decisions |
| Use-case recommendation matrix | Over-engineered; one summary suffices |
| Compact session mode | Simplify to full logs or summary only |
| **Perplexity API** | Different product category (chat model with search, not search API); token-based pricing incomparable to per-query APIs |

### What's Being Added

| Component | Purpose |
|-----------|---------|
| Brave Search provider | Real contender, currently missing |
| **Linkup provider** | Strong AI-native search API, competitive with Tavily/Exa |
| Curated query sets (public + private) | Reproducible, hard, relevant |
| HTML report generator | Shareable, visual, professional |
| History tracking (append-only JSON) | Trend analysis over time |
| CLI with subcommands | Clean interface for different modes |
| **Bias mitigation in judge** | Research-backed accuracy improvements |

---

## Part 2: Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         searchbench                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Queries    │───▶│   Runners    │───▶│    Judge     │       │
│  │              │    │              │    │              │       │
│  │ • public.json│    │ • Concurrent │    │ • GPT-4o-mini│       │
│  │ • private.json│   │ • Timed      │    │ • Binary Y/N │       │
│  └──────────────┘    │ • Costed     │    │ • Preflight  │       │
│                      └──────────────┘    │ • Bias-aware │       │
│                             │            └──────────────┘       │
│                             ▼                    │               │
│                      ┌──────────────┐    ┌──────────────┐       │
│                      │  Providers   │    │   Reporter   │       │
│                      │              │    │              │       │
│                      │ • Exa        │    │ • HTML output│       │
│                      │ • Parallel   │    │ • History    │       │
│                      │ • Brave      │    │ • Trends     │       │
│                      │ • Linkup     │    │ • Methodology│       │
│                      │ • Tavily     │    │              │       │
│                      └──────────────┘    └──────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
searchbench/
├── README.md                 # Project overview, usage, results summary
├── pyproject.toml            # Dependencies and CLI entrypoint
├── .env.example              # Required API keys template
├── config.toml               # Timeout settings (auto-calibrates)
│
├── searchbench/
│   ├── __init__.py
│   ├── cli.py                # Typer CLI with subcommands
│   ├── config.py             # Settings loader (reads config.toml + .env)
│   │
│   ├── providers/
│   │   ├── __init__.py       # Provider registry
│   │   ├── base.py           # Abstract provider interface
│   │   ├── exa.py            # Exa /answer endpoint only
│   │   ├── parallel.py       # Parallel strict mode only
│   │   ├── brave.py          # Brave Search API
│   │   ├── linkup.py         # Linkup standard search
│   │   └── tavily.py         # Tavily as baseline
│   │
│   ├── queries/
│   │   ├── __init__.py       # Query loading utilities
│   │   ├── public.json       # 50 curated hard questions
│   │   └── private.json      # Personal VC research queries (gitignored)
│   │
│   ├── judge.py              # LLM grading with GPT-4o-mini
│   ├── runner.py             # Concurrent execution, timing, costing
│   └── reporter.py           # HTML generation, history tracking
│
├── results/
│   ├── history.json          # Append-only benchmark history
│   ├── latest.html           # Most recent report
│   └── 2025-01-10.html       # Dated report archive
│
└── tests/
    ├── test_providers.py     # Provider unit tests
    └── test_judge.py         # Judge validation
```

---

## Part 3: Provider Specifications

### Design Principles

1. **One mode per provider** — No fallbacks, no escalation, no retries that change behavior
2. **Adaptive timeouts** — Start with sensible defaults, tune based on observed performance
3. **Transparent costing** — Track actual API costs per query using verified 2025 pricing
4. **Clean interface** — Every provider implements the same abstract base

### Adaptive Timeout System

**Philosophy:** Don't guess timeouts — measure them. The system starts with conservative defaults and adjusts based on actual performance data.

**How it works:**

1. **Initial defaults** — Each provider starts with a conservative timeout (see below)
2. **Track latencies** — Every run records p50, p95, p99 latency per provider
3. **Track timeouts** — Record timeout failures with query context
4. **Auto-calibrate** — The `calibrate` command analyzes history and suggests/applies new timeouts
5. **Config override** — Manual overrides via `config.toml` always take precedence

**Default timeouts (starting point):**
```toml
# searchbench/config.toml
[timeouts]
default = 30          # Fallback for any provider
exa = 30              # Conservative start
parallel = 30
brave = 20
linkup = 25
tavily = 20
```

**Calibration logic:**
```python
def suggest_timeout(provider: str, history: list[Run]) -> int:
    """Suggest timeout based on historical p99 latency + 20% buffer."""
    latencies = [r.results[provider].latency_ms for r in history
                 if provider in r.results and r.results[provider].error is None]
    if len(latencies) < 10:
        return DEFAULTS[provider]  # Not enough data

    p99 = np.percentile(latencies, 99)
    suggested = int(p99 * 1.2 / 1000)  # Convert to seconds + 20% buffer
    return max(15, min(60, suggested))  # Clamp to 15-60s range
```

**Timeout failure tracking (in history.json):**
```json
{
  "timeout_events": [
    {
      "date": "2025-01-10T14:35:00Z",
      "provider": "exa",
      "query_id": "multi_hop_12",
      "timeout_used": 30,
      "query_length": 287
    }
  ]
}
```

### Provider Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class SearchResult:
    answer: str                    # The synthesized answer
    citations: list[str]           # Source URLs
    latency_ms: int               # Time to response
    cost_usd: float               # API cost for this query
    raw_response: dict            # Full API response for debugging
    error: Optional[str] = None   # Error message if failed
    timed_out: bool = False       # Did this query timeout?

class Provider(ABC):
    name: str
    cost_per_query: float  # Baseline cost estimate

    @abstractmethod
    async def search(self, query: str, timeout: int) -> SearchResult:
        """Execute search with given timeout and return structured result."""
        pass
```

### Provider Details (Verified Pricing as of January 2025)

#### Exa

**Endpoint:** `/answer` only (not `/research/v1`)

**Rationale:** The `/research` endpoint is 2.5x more expensive and a different product. Benchmark them separately if needed, but default to `/answer`.

**Configuration:**
```python
endpoint = "https://api.exa.ai/answer"
cost_per_query = 0.01  # $0.005 search + $0.005 answer = $0.01 total
# timeout: loaded from config.toml, default 30s, auto-calibrates
```

**Verified Pricing (Source: [Exa Pricing](https://exa.ai/pricing)):**
- Search: $5 per 1,000 searches (1-25 results) = $0.005/search
- Answer: $5 per 1,000 calls = $0.005/call
- Combined: ~$0.01 per answered query

**What's removed:** Auto-escalation on "I'm sorry" disclaimers. If Exa can't answer, that's a data point.

---

#### Parallel AI

**Endpoint:** Search API v1beta, strict mode

**Rationale:** The Tavily fallback in the original code masked Parallel's true performance. We want to know what Parallel actually does.

**Configuration:**
```python
endpoint = "https://api.parallel.ai/v1beta/search"
headers = {"parallel-beta": "search-extract-2025-10-10"}  # Required header
cost_per_query = 0.005  # $0.005 per request
strict_mode = True  # No fallback
# timeout: loaded from config.toml, default 30s, auto-calibrates
```

**Verified Pricing (Source: [Parallel Pricing](https://parallel.ai/pricing)):**
- Search API: $0.005 per request (10 results)
- Optional: +$0.001 per page extracted

**What's removed:** Tavily fallback logic, query simplification retries.

---

#### Brave Search

**Endpoint:** Web Search API with AI summarization

**Rationale:** Missing from original benchmarks despite being a serious contender. Fast, cheap, privacy-focused. Now the only independent large-scale web search API since Bing API sunset.

**Configuration:**
```python
endpoint = "https://api.search.brave.com/res/v1/web/search"
cost_per_query = 0.005  # $5 per 1,000 queries (Base AI tier)
params = {"summary": 1}  # Enable AI summary
# timeout: loaded from config.toml, default 20s, auto-calibrates
```

**Verified Pricing (Source: [Brave API Pricing](https://api-dashboard.search.brave.com/app/plans)):**
- Free: 2,000 requests/month
- Base AI: $5 per 1,000 queries = $0.005/query
- Includes AI summarization, Infobox, FAQ, rich results

---

#### Linkup (NEW - Added based on research)

**Endpoint:** Standard search API

**Rationale:** Emerging as a strong Tavily/Exa competitor. Flat predictable pricing, built-in LangChain/LlamaIndex connectors, handles millions of queries/day.

**Configuration:**
```python
endpoint = "https://api.linkup.so/v1/search"
cost_per_query = 0.005  # €5 per 1,000 queries ≈ $0.0055 USD
mode = "standard"  # Not "deep" - keep it comparable
# timeout: loaded from config.toml, default 25s, auto-calibrates
```

**Verified Pricing (Source: [Linkup Pricing](https://www.linkup.so/pricing)):**
- Standard: €5 per 1,000 queries = €0.005/query (~$0.0055)
- Deep: €50 per 1,000 queries (not used in benchmark)

---

#### Tavily

**Endpoint:** `/search` with `include_answer=true`

**Rationale:** Free tier baseline. If Tavily performs comparably, that's valuable signal.

**Configuration:**
```python
endpoint = "https://api.tavily.com/search"
cost_per_query = 0.00  # Free tier (up to 1,000/month)
cost_per_query_paid = 0.008  # After free tier
search_depth = "basic"  # 1 credit; "advanced" = 2 credits
# timeout: loaded from config.toml, default 20s, auto-calibrates
```

**Verified Pricing (Source: [Tavily Credits](https://docs.tavily.com/documentation/api-credits)):**
- Free tier: 1,000 credits/month
- Pay-as-you-go: $0.008 per request
- Basic search: 1 credit, Advanced: 2 credits

**Note:** For benchmarking fairness, we use basic search. Track whether free tier is exhausted.

---

### Perplexity Decision: EXCLUDED

**Rationale:** After research, Perplexity is fundamentally different:

1. **Token-based pricing** — $1/M input, $1/M output tokens + $5/1K requests. This is incomparable to per-query APIs.
2. **Chat model architecture** — It's `/chat/completions`, not a search endpoint. The "search" is internal to the model.
3. **Variable costs** — A simple query might cost $0.002, a complex one $0.02. No predictable per-query cost.

**Recommendation:** If you want to benchmark Perplexity, create a separate "Chat-with-Search" category. Don't mix it with pure search APIs.

**Alternative:** Consider adding it as an optional `--include-chat-models` flag for curiosity, but don't include in the main comparison.

---

### You.com Decision: DEFERRED

**Rationale:**
- Serious contender with strong accuracy claims
- Opaque pricing (must contact sales or visit dashboard)
- Worth adding in v1.1 once pricing is verified

---

## Part 4: Query Sets

### Design Principles

1. **Hard questions** — Trivial queries don't differentiate providers
2. **Verifiable answers** — We need ground truth to grade
3. **Diverse domains** — Not all queries should be the same type
4. **Reproducible** — Public set is committed; private set is gitignored
5. **Sufficient sample size** — 50 questions minimum for statistical validity

### Public Query Set (50 questions)

**CHANGE FROM ORIGINAL:** Increased from 30 to 50 for better statistical significance. With 5 providers and 50 questions, we get 250 data points per run.

Curated for difficulty and verifiability. Categories:

**Factual Lookup (15)** — Answers exist but require synthesis
```json
{
  "query": "What was the exact founding date of Stripe and who were the co-founders?",
  "expected": "Stripe was founded in 2010 by Patrick Collison and John Collison",
  "category": "factual"
}
```

**Multi-hop Reasoning (15)** — Requires connecting multiple sources
```json
{
  "query": "Which company acquired the startup founded by the person who wrote 'Zero to One'?",
  "expected": "PayPal (Peter Thiel co-founded PayPal, which was acquired by eBay)",
  "category": "multi-hop"
}
```

**Current State (10)** — Tests recency of information
```json
{
  "query": "Who is the current CEO of OpenAI as of 2025?",
  "expected": "Sam Altman",
  "category": "current"
}
```

**Obscure/Niche (10)** — Tests depth of indexing
```json
{
  "query": "What is the name of the theorem that proves no consistent system can prove its own consistency?",
  "expected": "Gödel's second incompleteness theorem",
  "category": "obscure"
}
```

### Private Query Set (VC Research)

**Gitignored.** Template structure:

```json
{
  "queries": [
    {
      "query": "Who are the largest enterprise customers of [Company X]?",
      "expected": null,
      "category": "customer-intel",
      "notes": "Grade on plausibility and citation quality"
    },
    {
      "query": "What were the terms of [Startup Y]'s Series B?",
      "expected": null,
      "category": "deal-terms",
      "notes": "Often not public; test if API hallucinates"
    }
  ]
}
```

For queries without known answers, the judge uses a modified rubric (see Part 5).

---

## Part 5: Judge Specification

### Design Principles

1. **Binary grading** — Correct or incorrect. No partial credit.
2. **Equivalence handling** — "4" = "four" = "Four (4)"
3. **Preflight validation** — Test judge before running full benchmark
4. **Graceful fallback** — Fuzzy string matching if LLM fails
5. **Bias mitigation** — Research-backed techniques to improve accuracy

### Why GPT-4o-mini?

Research validates this choice (Source: [LLM-as-a-Judge research](https://arxiv.org/html/2512.01232)):
- **Best accuracy:** 6.07 MAAE in comparative studies
- **High reliability:** 96.6% ECR@1
- **Cost effective:** $1.01 per 1,000 evaluations (78x cheaper than GPT-4)
- **Consistent:** Shows strongest agreement with human ratings

### Bias Mitigation (NEW)

Research shows LLM judges have predictable biases. We address them:

| Bias | Impact | Mitigation |
|------|--------|------------|
| Position bias | ~40% of evaluations affected | N/A for single-answer grading |
| Verbosity bias | ~15% score inflation | Explicit "concise answers preferred" instruction |
| Self-enhancement | 5-7% boost for same-model | GPT-4o-mini judging non-OpenAI search APIs |

### Implementation

**Model:** GPT-4o-mini (validated as optimal for this task)

**Prompt (improved with chain-of-thought):**
```
You are grading a search API's answer to a factual question.

Question: {query}
Expected answer: {expected}
API's answer: {response}

Think step-by-step:
1. What are the key facts in the expected answer?
2. Does the API's answer contain those key facts?
3. Are there any factual errors in the API's answer?
4. Is the answer concise and direct? (Verbose padding does not add credit)

Consider semantic equivalence: "4" = "four", "NYC" = "New York City", etc.

Respond with exactly one line:
CORRECT: [one-sentence explanation]
or
INCORRECT: [one-sentence explanation]
```

**For queries without expected answers:**
```
You are evaluating a search API's answer for plausibility and quality.

Question: {query}
API's answer: {response}
Citations provided: {citations}

Evaluate step-by-step:
1. Does the answer directly and specifically address the question?
2. Are the citations from credible, authoritative sources?
3. Does the answer make claims without citation support?
4. Could this answer be verified by checking the citations?

Respond with exactly one line:
PLAUSIBLE: [one-sentence explanation]
or
IMPLAUSIBLE: [one-sentence explanation]
```

### Preflight Check

Before running any benchmark, validate the judge:

```python
async def preflight_judge():
    """Verify judge is responding correctly."""
    test_cases = [
        ("What is 1+1?", "2", "The answer is 2", True),
        ("What is 1+1?", "2", "The answer is 3", False),
        ("Capital of France?", "Paris", "Paris is the capital", True),
        ("Capital of France?", "Paris", "London is the capital", False),
        ("Who founded Microsoft?", "Bill Gates and Paul Allen", "Bill Gates", True),  # Partial credit test
    ]
    passed = 0
    for query, expected, response, should_pass in test_cases:
        result = await judge(query, expected, response)
        if result.correct == should_pass:
            passed += 1
        else:
            print(f"Judge preflight warning: {query} - expected {should_pass}, got {result.correct}")

    if passed < 4:  # Allow 1 marginal case
        raise RuntimeError(f"Judge preflight failed: {passed}/5 cases correct")
    return True
```

---

## Part 6: Reporter Specification

### Design Principles

1. **HTML output** — Shareable, professional, renders anywhere
2. **History tracking** — Append results, enable trend analysis
3. **Minimal dependencies** — No React, no build step, just templated HTML
4. **Mobile-friendly** — Works on phone for quick checks
5. **Methodology transparency** — Explain how results were generated

### HTML Report Structure

```html
<!DOCTYPE html>
<html>
<head>
  <title>SearchBench Results — {date}</title>
  <style>
    /* Embedded CSS, no external deps */
    :root {
      --bg: #0a0a0a;
      --card: #141414;
      --border: #2a2a2a;
      --text: #e5e5e5;
      --muted: #737373;
      --accent: #3b82f6;
      --success: #22c55e;
      --warning: #eab308;
      --error: #ef4444;
    }
    /* ... full styles ... */
  </style>
</head>
<body>
  <header>
    <h1>SearchBench Results</h1>
    <p class="date">{date} · {n_queries} queries · {n_providers} providers</p>
  </header>

  <section class="summary">
    <h2>Summary</h2>
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th>Accuracy</th>
          <th>Avg Latency</th>
          <th>Total Cost</th>
          <th>Errors</th>
        </tr>
      </thead>
      <tbody>
        <!-- Sorted by accuracy descending -->
        <tr class="winner">
          <td>🥇 Exa</td>
          <td>73%</td>
          <td>8.2s</td>
          <td>$0.50</td>
          <td>0</td>
        </tr>
        <!-- ... -->
      </tbody>
    </table>
  </section>

  <section class="trends">
    <h2>Performance Over Time</h2>
    <div class="chart">
      <!-- SVG sparklines for each provider -->
    </div>
  </section>

  <section class="methodology">
    <h2>Methodology</h2>
    <p>This benchmark ran {n_queries} curated questions across {n_providers} search APIs.
       Answers were graded by GPT-4o-mini using binary correct/incorrect scoring with
       semantic equivalence. Latency measured from request initiation to full response.
       Costs calculated using published API pricing as of {date}.</p>
    <details>
      <summary>Provider configurations</summary>
      <ul>
        <li><strong>Exa:</strong> /answer endpoint, 45s timeout</li>
        <li><strong>Parallel:</strong> v1beta search, strict mode, 30s timeout</li>
        <!-- ... -->
      </ul>
    </details>
  </section>

  <section class="details">
    <h2>Query Details</h2>
    <details>
      <summary>Show all {n_queries} results</summary>
      <table>
        <!-- Per-query breakdown -->
      </table>
    </details>
  </section>

  <footer>
    <p>Generated by <a href="https://github.com/samay58/searchbench">searchbench</a></p>
  </footer>
</body>
</html>
```

### History Format

`results/history.json`:

```json
{
  "runs": [
    {
      "date": "2025-01-10T14:30:00Z",
      "query_set": "public",
      "n_queries": 50,
      "judge_model": "gpt-4o-mini",
      "results": {
        "exa": {
          "accuracy": 0.73,
          "avg_latency_ms": 8200,
          "latency_p50_ms": 6800,
          "latency_p95_ms": 14200,
          "latency_p99_ms": 18500,
          "total_cost_usd": 0.50,
          "errors": 0,
          "timeouts": 0,
          "endpoint": "/answer",
          "timeout_used": 30
        },
        "parallel": {
          "accuracy": 0.67,
          "avg_latency_ms": 6100,
          "latency_p50_ms": 5200,
          "latency_p95_ms": 11000,
          "latency_p99_ms": 14800,
          "total_cost_usd": 0.25,
          "errors": 2,
          "timeouts": 1,
          "endpoint": "v1beta/search",
          "timeout_used": 30
        },
        "brave": {
          "accuracy": 0.62,
          "avg_latency_ms": 2100,
          "latency_p50_ms": 1800,
          "latency_p95_ms": 3200,
          "latency_p99_ms": 4100,
          "total_cost_usd": 0.25,
          "errors": 0,
          "timeouts": 0,
          "endpoint": "web/search",
          "timeout_used": 20
        },
        "linkup": {
          "accuracy": 0.70,
          "avg_latency_ms": 4500,
          "latency_p50_ms": 3800,
          "latency_p95_ms": 7200,
          "latency_p99_ms": 9100,
          "total_cost_usd": 0.28,
          "errors": 1,
          "timeouts": 0,
          "endpoint": "v1/search",
          "timeout_used": 25
        },
        "tavily": {
          "accuracy": 0.58,
          "avg_latency_ms": 3200,
          "latency_p50_ms": 2800,
          "latency_p95_ms": 5100,
          "latency_p99_ms": 6800,
          "total_cost_usd": 0.00,
          "errors": 0,
          "timeouts": 0,
          "endpoint": "/search",
          "timeout_used": 20
        }
      }
    }
  ],
  "timeout_events": [
    {
      "date": "2025-01-10T14:35:22Z",
      "provider": "parallel",
      "query_id": "multi_hop_12",
      "timeout_used": 30,
      "query_length": 287
    }
  ]
}
```

---

## Part 7: CLI Specification

### Commands

```bash
# Run full benchmark with all providers on public queries
searchbench run

# Run with specific providers
searchbench run --providers exa,parallel,brave

# Run with private query set
searchbench run --queries private

# Quick check (10 random queries) - CHANGED from 5 to 10
searchbench quick

# Show historical trends
searchbench history

# Add a query to private set
searchbench add "What is the revenue of [Company X]?"

# List configured providers and their status
searchbench providers

# Open latest report in browser
searchbench report

# Validate setup (API keys, judge, etc.)
searchbench validate

# Calibrate timeouts based on historical performance
searchbench calibrate

# Calibrate and auto-apply suggestions
searchbench calibrate --apply
```

### Implementation

Using Typer for clean CLI:

```python
import typer
from rich.console import Console

app = typer.Typer(help="Honest benchmarks for agentic search APIs")
console = Console()

@app.command()
def run(
    providers: str = typer.Option("all", help="Comma-separated: exa,parallel,brave,linkup,tavily"),
    queries: str = typer.Option("public", help="Query set: public, private, or path"),
    output: str = typer.Option("results/", help="Output directory"),
):
    """Run full benchmark."""
    # ...

@app.command()
def quick(
    providers: str = typer.Option("all", help="Comma-separated provider names"),
):
    """Quick check with 10 random queries."""
    # ...

@app.command()
def history(
    last: int = typer.Option(10, help="Number of recent runs to show"),
):
    """Show performance trends over time."""
    # ...

@app.command()
def validate():
    """Validate API keys and judge configuration."""
    # Check each API key
    # Run judge preflight
    # Report status
    # ...

@app.command()
def calibrate(
    apply: bool = typer.Option(False, help="Auto-apply suggested timeouts to config"),
):
    """Analyze historical latencies and suggest/apply timeout adjustments."""
    history = load_history()
    suggestions = {}

    for provider in PROVIDERS:
        current = get_timeout(provider)
        suggested = suggest_timeout(provider, history)
        if suggested != current:
            suggestions[provider] = {"current": current, "suggested": suggested}

    if not suggestions:
        console.print("[green]All timeouts are well-calibrated.[/green]")
        return

    # Display suggestions
    for provider, data in suggestions.items():
        console.print(f"{provider}: {data['current']}s → {data['suggested']}s")

    if apply:
        update_config(suggestions)
        console.print("[green]Config updated.[/green]")
    else:
        console.print("\nRun with --apply to update config.toml")

if __name__ == "__main__":
    app()
```

---

## Part 8: Implementation Plan

### Phase 1: Foundation (Day 1)

1. **Rename and restructure**
   ```bash
   mv ~/browse-comp-v2 ~/searchbench
   cd ~/searchbench
   rm -rf .git && git init
   ```

2. **Create directory structure** per spec

3. **Implement provider base class and interface**

4. **Port Exa provider** (simplify: remove escalation, update pricing)

5. **Port Tavily provider** (minimal changes, update pricing)

6. **Implement judge** (port from existing, add bias mitigation)

### Phase 2: Providers (Day 1-2)

1. **Implement Brave provider**

2. **Implement Linkup provider** (NEW)

3. **Port Parallel provider** (remove fallback, update headers)

4. **Write provider tests**

5. **Implement `validate` command**

### Phase 3: Query Sets (Day 2)

1. **Curate public query set** (50 questions with expected answers)

2. **Create private query set template**

3. **Implement query loading utilities**

### Phase 4: Runner & Reporter (Day 2-3)

1. **Implement concurrent runner** with timing/costing

2. **Implement HTML reporter** with methodology section

3. **Implement history tracking**

4. **Create CLI with Typer**

### Phase 5: Polish (Day 3)

1. **Write README**

2. **Add .env.example**

3. **Test end-to-end**

4. **Run initial benchmark**

5. **Push to GitHub**

---

## Part 9: Success Criteria

### Functional

- [ ] All 5 providers return results or clean errors
- [ ] Judge correctly grades 95%+ of test cases
- [ ] HTML report renders correctly in Chrome, Safari, Firefox
- [ ] History appends correctly across runs
- [ ] CLI subcommands all work
- [ ] `validate` command confirms setup

### Quality

- [ ] Full benchmark completes in < 15 minutes (adjusted for 50 queries)
- [ ] No silent fallbacks or mode switches
- [ ] Costs are tracked accurately per verified pricing
- [ ] Results are reproducible (same queries → same provider behavior)

### Usability

- [ ] `searchbench run` works out of the box with just API keys
- [ ] Report is understandable at a glance
- [ ] README explains what this is in 30 seconds
- [ ] Methodology section explains how to interpret results

---

## Part 10: Resolved Open Questions

### 1. Should Perplexity be included?

**DECISION: No, excluded from default set.**

It's a chat model with search, not a search API. Token-based pricing is incomparable. If curious, add as `--include-chat-models` flag, but don't include in main comparison.

### 2. What about You.com?

**DECISION: Deferred to v1.1.**

Promising but opaque pricing. Add once we can verify costs.

### 3. How often to run?

**DECISION: On-demand for personal use.**

Weekly GitHub Action if publishing results publicly. Add cron job in v1.1.

### 4. Should results be public?

**DECISION: Yes, with caveats.**

Publish to GitHub Pages for credibility. Include clear methodology section. Update monthly at minimum.

### 5. What about timeouts?

**DECISION: Adaptive, data-driven timeouts.**

Hardcoding timeouts based on guesswork is fragile. Instead:

1. **Start conservative** — All providers begin with sensible defaults (20-30s)
2. **Track everything** — Record p50/p95/p99 latencies and timeout events per provider
3. **Auto-calibrate** — `searchbench calibrate` analyzes history and suggests adjustments
4. **Config override** — Manual settings in `config.toml` always take precedence
5. **Iterative tuning** — The AI building this (Claude/Codex) should run benchmarks, observe failures, and adjust

**Default starting points (in config.toml):**
- Exa: 30s
- Parallel: 30s
- Brave: 20s
- Linkup: 25s
- Tavily: 20s

These will be tuned based on actual performance data during development and ongoing use.

---

## Appendix A: Migration Checklist

```
[ ] Rename repo: browse-comp-v2 → searchbench
[ ] Update all internal references
[ ] Delete: queries.py BrowseComp download code
[ ] Delete: visualizer.py terminal dashboard
[ ] Delete: session persistence compact mode
[ ] Simplify: providers.py Exa escalation
[ ] Simplify: providers.py Parallel fallback
[ ] Add: Brave provider
[ ] Add: Linkup provider (NEW)
[ ] Add: HTML reporter with methodology section
[ ] Add: history.json tracking with latency percentiles
[ ] Add: CLI with Typer
[ ] Add: validate command
[ ] Add: calibrate command (NEW - timeout tuning)
[ ] Add: config.toml with adaptive timeout system (NEW)
[ ] Create: public.json query set (50 questions)
[ ] Create: private.json template
[ ] Update: All pricing to verified 2025 numbers
[ ] Add: Bias mitigation to judge
[ ] Write: README.md
[ ] Write: .env.example
[ ] Test: end-to-end
[ ] Run: initial benchmark, observe timeouts, run calibrate
[ ] Push: to GitHub
```

---

## Appendix B: API Key Requirements

```bash
# .env.example

# Required for benchmark
EXA_API_KEY=           # https://exa.ai - $10 free credits
PARALLEL_API_KEY=      # https://parallel.ai - 16,000 free searches
BRAVE_API_KEY=         # https://brave.com/search/api - 2,000 free/month
LINKUP_API_KEY=        # https://linkup.so - Free tier available
TAVILY_API_KEY=        # https://tavily.com - 1,000 free/month

# Required for judging
OPENAI_API_KEY=        # For GPT-4o-mini judge (~$0.05 per 50-query run)
```

---

## Appendix C: Verified Pricing Summary (January 2025)

| Provider | Cost/Query | Free Tier | Source |
|----------|------------|-----------|--------|
| Exa (/answer) | $0.01 | $10 credits | [exa.ai/pricing](https://exa.ai/pricing) |
| Parallel | $0.005 | 16,000 queries | [parallel.ai/pricing](https://parallel.ai/pricing) |
| Brave | $0.005 | 2,000/month | [Brave API Dashboard](https://api-dashboard.search.brave.com/app/plans) |
| Linkup | ~$0.0055 | Free tier | [linkup.so/pricing](https://www.linkup.so/pricing) |
| Tavily | $0.008 (paid) | 1,000/month | [Tavily Docs](https://docs.tavily.com/documentation/api-credits) |
| GPT-4o-mini (judge) | ~$0.001/query | N/A | OpenAI pricing |

**Estimated cost per 50-query benchmark:** ~$0.75-1.00 (all providers + judging)

---

## Appendix D: Research Sources

This revised spec was informed by web research conducted January 2025:

- [Exa AI Pricing](https://exa.ai/pricing) - Answer endpoint costs
- [Parallel AI Pricing](https://parallel.ai/pricing) - Search API v1beta
- [Brave Search API](https://brave.com/search/api/) - AI summarization tier
- [Linkup Pricing](https://www.linkup.so/pricing) - Standard vs Deep search
- [Tavily Documentation](https://docs.tavily.com/documentation/api-credits) - Credit system
- [Perplexity Pricing](https://docs.perplexity.ai/getting-started/pricing) - Token-based model
- [LLM-as-a-Judge Research](https://arxiv.org/html/2512.01232) - GPT-4o-mini validation
- [JudgeBench (ICLR 2025)](https://arxiv.org/pdf/2410.12784) - Bias mitigation
- [Firecrawl Web Search Guide](https://www.firecrawl.dev/blog/top_web_search_api_2025) - Market overview

---

*End of revised spec.*
