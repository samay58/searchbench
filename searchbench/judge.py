from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import AsyncOpenAI

from searchbench.providers.base import SearchResult
from searchbench.queries import Query, EvidenceRequirement
from searchbench.runner import RunResult, QueryResult


load_dotenv()

DEFAULT_JUDGE_CONCURRENCY = int(os.getenv("JUDGE_CONCURRENCY", "6"))


@dataclass(frozen=True)
class JudgeResult:
    label: str
    passed: bool
    explanation: str
    raw: str | None = None
    model: str | None = None
    evidence_passed: bool | None = None
    evidence_notes: str | None = None


class Judge:
    def __init__(self, model: str | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url) if base_url else AsyncOpenAI(api_key=api_key)
        self.model = model or os.getenv("JUDGE_MODEL", "gpt-4o-mini")

    async def grade(self, query: Query, response: SearchResult) -> JudgeResult:
        answer = (response.answer or "").strip()
        citations = response.citations or []
        return await self.grade_text(query.text, query.expected, answer, citations, query.evidence)

    async def grade_text(
        self,
        question: str,
        expected: list[str] | None,
        answer: str,
        citations: Iterable[str] | None = None,
        evidence: EvidenceRequirement | None = None,
    ) -> JudgeResult:
        citations_list = [str(c) for c in (citations or []) if c]
        if not answer:
            result = JudgeResult(
                label="incorrect" if expected else "implausible",
                passed=False,
                explanation="No answer provided.",
            )
            return self._apply_evidence(result, citations_list, evidence, expected is not None)

        prompt = self._build_prompt(question, expected, answer, citations_list)
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise grader. Prefer concise, direct answers and ignore verbosity.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=200,
            )
            raw = response.choices[0].message.content.strip()
            parsed = self._parse_verdict(raw, expected is not None)
            if parsed:
                label, explanation = parsed
                result = JudgeResult(
                    label=label,
                    passed=label in {"correct", "plausible"},
                    explanation=explanation,
                    raw=raw,
                    model=self.model,
                )
                return self._apply_evidence(result, citations_list, evidence, expected is not None)
        except Exception as exc:
            fallback = self._fallback(expected, answer, citations_list, str(exc))
            return self._apply_evidence(fallback, citations_list, evidence, expected is not None)

        fallback = self._fallback(expected, answer, citations_list, "Unable to parse judge response.")
        return self._apply_evidence(fallback, citations_list, evidence, expected is not None)

    async def preflight(self) -> bool:
        cases = [
            ("What is 1+1?", ["2"], "The answer is 2", True),
            ("What is 1+1?", ["2"], "The answer is 3", False),
            ("Capital of France?", ["Paris"], "Paris is the capital", True),
            ("Capital of France?", ["Paris"], "London is the capital", False),
            ("Who founded Microsoft?", ["Bill Gates and Paul Allen"], "Bill Gates", True),
        ]
        passed = 0
        for question, expected, answer, should_pass in cases:
            result = await self.grade_text(question, expected, answer, [])
            if result.passed == should_pass:
                passed += 1
        if passed < 4:
            raise RuntimeError(f"Judge preflight failed: {passed}/5 correct")
        return True

    def _apply_evidence(
        self,
        result: JudgeResult,
        citations: list[str],
        evidence: EvidenceRequirement | None,
        has_expected: bool,
    ) -> JudgeResult:
        if evidence is None:
            return result
        passed, notes = self._check_evidence(citations, evidence)
        if passed:
            return JudgeResult(
                label=result.label,
                passed=result.passed,
                explanation=result.explanation,
                raw=result.raw,
                model=result.model,
                evidence_passed=True,
                evidence_notes=None,
            )

        label = "incorrect" if has_expected else "implausible"
        return JudgeResult(
            label=label,
            passed=False,
            explanation=f"Evidence check failed: {notes}",
            raw=result.raw,
            model=result.model,
            evidence_passed=False,
            evidence_notes=notes,
        )

    @staticmethod
    def _check_evidence(
        citations: Iterable[str],
        evidence: EvidenceRequirement,
    ) -> tuple[bool, str | None]:
        citations_list = [str(c) for c in citations if c]
        unique_count = len({c for c in citations_list})
        reasons = []

        if evidence.min_citations and unique_count < evidence.min_citations:
            reasons.append(f"only {unique_count} citation(s), need {evidence.min_citations}")

        domains = Judge._extract_domains(citations_list)
        missing_domains = []
        for required in evidence.required_domains:
            if not Judge._domain_present(domains, required):
                missing_domains.append(required)
        if missing_domains:
            reasons.append("missing domains: " + ", ".join(missing_domains))

        citation_blob = " ".join(citations_list).lower()
        missing_sources = []
        for source in evidence.required_sources:
            if source.lower() not in citation_blob:
                missing_sources.append(source)
        if missing_sources:
            reasons.append("missing sources: " + ", ".join(missing_sources))

        if reasons:
            return False, "; ".join(reasons)
        return True, None

    @staticmethod
    def _extract_domains(citations: Iterable[str]) -> set[str]:
        domains: set[str] = set()
        for citation in citations:
            if not citation:
                continue
            value = str(citation).strip()
            if not value:
                continue
            if "://" not in value:
                value = "https://" + value
            parsed = urlparse(value)
            host = parsed.netloc or parsed.path.split("/")[0]
            host = host.lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                domains.add(host)
        return domains

    @staticmethod
    def _domain_present(domains: set[str], required: str) -> bool:
        required = required.lower()
        for domain in domains:
            if domain == required or domain.endswith("." + required) or domain.endswith(required):
                return True
        return False

    def _build_prompt(
        self,
        question: str,
        expected: list[str] | None,
        answer: str,
        citations: Iterable[str],
    ) -> str:
        if expected is not None:
            expected_text = "; ".join(expected)
            return "\n".join(
                [
                    "You are grading a search API's answer to a factual question.",
                    "",
                    f"Question: {question}",
                    f"Expected answer: {expected_text}",
                    f"API's answer: {answer}",
                    "",
                    "Think step-by-step:",
                    "1. What are the key facts in the expected answer?",
                    "2. Does the API's answer contain those key facts?",
                    "3. Are there any factual errors in the API's answer?",
                    "4. Is the answer concise and direct? (Verbose padding does not add credit)",
                    "",
                    'Consider semantic equivalence: "4" = "four", "NYC" = "New York City", etc.',
                    "",
                    "Respond with exactly one line:",
                    "CORRECT: [one-sentence explanation]",
                    "or",
                    "INCORRECT: [one-sentence explanation]",
                ]
            )
        citations_text = ", ".join(citations) if citations else "None"
        return "\n".join(
            [
                "You are evaluating a search API's answer for plausibility and quality.",
                "",
                f"Question: {question}",
                f"API's answer: {answer}",
                f"Citations provided: {citations_text}",
                "",
                "Evaluate step-by-step:",
                "1. Does the answer directly and specifically address the question?",
                "2. Are the citations from credible, authoritative sources?",
                "3. Does the answer make claims without citation support?",
                "4. Could this answer be verified by checking the citations?",
                "",
                "Respond with exactly one line:",
                "PLAUSIBLE: [one-sentence explanation]",
                "or",
                "IMPLAUSIBLE: [one-sentence explanation]",
            ]
        )

    def _parse_verdict(self, raw: str, has_expected: bool) -> tuple[str, str] | None:
        match = re.match(r"^(CORRECT|INCORRECT|PLAUSIBLE|IMPLAUSIBLE):\s*(.+)$", raw.strip(), re.I)
        if not match:
            return None
        label = match.group(1).lower()
        explanation = match.group(2).strip() if match.group(2) else ""
        if has_expected and label in {"plausible", "implausible"}:
            return None
        if not has_expected and label in {"correct", "incorrect"}:
            return None
        return label, explanation or "No explanation provided."

    def _fallback(
        self,
        expected: list[str] | None,
        answer: str,
        citations: Iterable[str] | None,
        reason: str,
    ) -> JudgeResult:
        if expected is None:
            plausible = bool(answer.strip()) and bool(list(citations or []))
            return JudgeResult(
                label="plausible" if plausible else "implausible",
                passed=plausible,
                explanation=f"Fallback: {reason}",
            )

        normalized = self._normalize(answer)
        for exp in expected:
            exp_norm = self._normalize(exp)
            if exp_norm in normalized:
                return JudgeResult(
                    label="correct",
                    passed=True,
                    explanation=f"Fallback: matched expected answer ({reason}).",
                )
            if SequenceMatcher(None, normalized, exp_norm).ratio() >= 0.86:
                return JudgeResult(
                    label="correct",
                    passed=True,
                    explanation=f"Fallback: fuzzy match ({reason}).",
                )
            if self._number_equivalent(normalized, exp_norm):
                return JudgeResult(
                    label="correct",
                    passed=True,
                    explanation=f"Fallback: numeric equivalence ({reason}).",
                )
        return JudgeResult(
            label="incorrect",
            passed=False,
            explanation=f"Fallback: no match ({reason}).",
        )

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = text.lower()
        cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _number_equivalent(a: str, b: str) -> bool:
        number_map = {
            "0": "zero",
            "1": "one",
            "2": "two",
            "3": "three",
            "4": "four",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "nine",
        }
        for digit, word in number_map.items():
            if (digit in a and word in b) or (digit in b and word in a):
                return True
        return False


@dataclass(frozen=True)
class GradedQuery:
    query: Query
    responses: dict[str, SearchResult]
    judgments: dict[str, JudgeResult]


@dataclass(frozen=True)
class GradedRun:
    run: RunResult
    graded_queries: list[GradedQuery]


async def grade_run(
    judge: Judge,
    run: RunResult,
    max_concurrency: int | None = None,
) -> GradedRun:
    graded: list[GradedQuery] = []
    limit = max_concurrency or DEFAULT_JUDGE_CONCURRENCY
    semaphore = asyncio.Semaphore(max(1, limit))

    async def grade_one(
        provider_name: str,
        response: SearchResult,
        query: Query,
    ) -> tuple[str, JudgeResult]:
        async with semaphore:
            result = await judge.grade_text(
                query.text,
                query.expected,
                response.answer or "",
                response.citations,
                query.evidence,
            )
        return provider_name, result

    async def grade_query(item: QueryResult) -> GradedQuery:
        tasks = [
            grade_one(provider_name, response, item.query)
            for provider_name, response in item.results.items()
        ]
        judgments = {name: result for name, result in await asyncio.gather(*tasks)}
        return GradedQuery(query=item.query, responses=item.results, judgments=judgments)

    graded = list(await asyncio.gather(*(grade_query(item) for item in run.results)))
    return GradedRun(run=run, graded_queries=graded)
