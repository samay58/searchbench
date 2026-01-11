from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from dotenv import load_dotenv
from openai import AsyncOpenAI

from searchbench.providers.base import SearchResult
from searchbench.queries import Query
from searchbench.runner import RunResult, QueryResult


load_dotenv()


@dataclass(frozen=True)
class JudgeResult:
    label: str
    passed: bool
    explanation: str
    raw: str | None = None
    model: str | None = None


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
        return await self.grade_text(query.text, query.expected, answer, citations)

    async def grade_text(
        self,
        question: str,
        expected: list[str] | None,
        answer: str,
        citations: Iterable[str] | None = None,
    ) -> JudgeResult:
        if not answer:
            return JudgeResult(
                label="incorrect" if expected else "implausible",
                passed=False,
                explanation="No answer provided.",
            )

        prompt = self._build_prompt(question, expected, answer, citations or [])
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
                return JudgeResult(
                    label=label,
                    passed=label in {"correct", "plausible"},
                    explanation=explanation,
                    raw=raw,
                    model=self.model,
                )
        except Exception as exc:
            return self._fallback(expected, answer, citations, str(exc))

        return self._fallback(expected, answer, citations, "Unable to parse judge response.")

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

    def _build_prompt(
        self,
        question: str,
        expected: list[str] | None,
        answer: str,
        citations: Iterable[str],
    ) -> str:
        if expected is not None:
            expected_text = "; ".join(expected)
            return (
                "You are grading a search API's answer to a factual question.\n\n"
                f"Question: {question}\n"
                f"Expected answer: {expected_text}\n"
                f"API's answer: {answer}\n\n"
                "Think step-by-step:\n"
                "1. What are the key facts in the expected answer?\n"
                "2. Does the API's answer contain those key facts?\n"
                "3. Are there any factual errors in the API's answer?\n"
                "4. Is the answer concise and direct? (Verbose padding does not add credit)\n\n"
                "Consider semantic equivalence: \"4\" = \"four\", \"NYC\" = \"New York City\", etc.\n\n"
                "Respond with exactly one line:\n"
                "CORRECT: [one-sentence explanation]\n"
                "or\n"
                "INCORRECT: [one-sentence explanation]"
            )
        citations_text = ", ".join(citations) if citations else "None"
        return (
            "You are evaluating a search API's answer for plausibility and quality.\n\n"
            f"Question: {question}\n"
            f"API's answer: {answer}\n"
            f"Citations provided: {citations_text}\n\n"
            "Evaluate step-by-step:\n"
            "1. Does the answer directly and specifically address the question?\n"
            "2. Are the citations from credible, authoritative sources?\n"
            "3. Does the answer make claims without citation support?\n"
            "4. Could this answer be verified by checking the citations?\n\n"
            "Respond with exactly one line:\n"
            "PLAUSIBLE: [one-sentence explanation]\n"
            "or\n"
            "IMPLAUSIBLE: [one-sentence explanation]"
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


async def grade_run(judge: Judge, run: RunResult) -> GradedRun:
    graded: list[GradedQuery] = []
    for item in run.results:
        judgments: dict[str, JudgeResult] = {}
        for provider_name, response in item.results.items():
            judgments[provider_name] = await judge.grade_text(
                item.query.text,
                item.query.expected,
                response.answer or "",
                response.citations,
            )
        graded.append(
            GradedQuery(
                query=item.query,
                responses=item.results,
                judgments=judgments,
            )
        )
    return GradedRun(run=run, graded_queries=graded)
