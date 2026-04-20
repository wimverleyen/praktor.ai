"""
Shared base for LLM-as-judge evaluators.

Provides _parse_json, _init_adapters, evaluate(), and compare() so
HEDISJudge and DiabetesHEDISJudge don't duplicate identical plumbing.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from praktor.settings import MODEL as _DEFAULT_MODEL, create_log

log = create_log()


class BaseJudge(ABC):
    """
    Common plumbing for all clinical LLM judges.

    Subclasses must supply:
        _eval_prompt   — prompt template string for evaluation
        _compare_prompt — prompt template string for comparison
        _default_model  — fallback model name

    And implement:
        _parse_score(response, recommendation) -> score dataclass
        _neutral_score(reason) -> score dataclass
    """

    _eval_prompt: str = ""
    _compare_prompt: str = ""
    _default_model: str = _DEFAULT_MODEL

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._default_model
        self._eval_adapter = None
        self._compare_adapter = None
        self._last_eval_prompt: str | None = None    # rendered prompt from last evaluate()
        self._last_eval_response: str | None = None  # raw LLM output from last evaluate()
        self._init_adapters()

    def _init_adapters(self) -> None:
        # Catch misconfigured subclasses before swallowing the error
        if not self._eval_prompt or not self._compare_prompt:
            raise ValueError(
                f"{self.__class__.__name__}: _eval_prompt and _compare_prompt must be set"
            )
        try:
            from praktor.LLM.llm_interface import AsyncLLMAdapter
            self._eval_adapter = AsyncLLMAdapter(
                prompt_template=self._eval_prompt,
                model=self._model,
                temperature=0.0,
            )
            self._compare_adapter = AsyncLLMAdapter(
                prompt_template=self._compare_prompt,
                model=self._model,
                temperature=0.0,
            )
        except Exception as e:
            log.error(f"{self.__class__.__name__}: adapter init failed: {e}")

    async def evaluate(
        self,
        recommendation: "str | dict",
        member_context: str,
        outcome: "str | None" = None,
    ):
        """Score a recommendation. Returns the subclass score dataclass."""
        if self._eval_adapter is None:
            return self._neutral_score("adapter_unavailable")
        rec_text = (
            json.dumps(recommendation, indent=2)
            if isinstance(recommendation, dict)
            else str(recommendation)
        )
        invoke_data = {
            "recommendation": rec_text,
            "member_context": member_context,
            "outcome": outcome or "pending",
        }
        try:
            self._last_eval_prompt = self._eval_adapter.render(invoke_data)
        except Exception:
            self._last_eval_prompt = None
        try:
            response = await self._eval_adapter.ainvoke(invoke_data)
            self._last_eval_response = response
            return self._parse_score(response, recommendation)
        except Exception as e:
            self._last_eval_response = None
            log.error(f"{self.__class__.__name__}.evaluate failed: {e}")
            return self._neutral_score(str(e))

    async def compare(
        self,
        recommendation_a: str,
        recommendation_b: str,
        member_context: str,
    ) -> dict:
        """Head-to-head comparison. Returns {winner, confidence, reasoning}."""
        if self._compare_adapter is None:
            return {"winner": "A", "confidence": 0.5, "reasoning": "adapter unavailable"}
        try:
            response = await self._compare_adapter.ainvoke({
                "recommendation_a": recommendation_a,
                "recommendation_b": recommendation_b,
                "member_context": member_context,
            })
            result = self._parse_json(
                response, {"winner": "A", "confidence": 0.5, "reasoning": ""}
            )
            # Normalize winner to A/B — LLMs sometimes return "tie", "C", null
            winner = str(result.get("winner", "A")).upper().strip()
            if winner not in {"A", "B"}:
                winner = "A"
            result["winner"] = winner
            return result
        except Exception as e:
            log.error(f"{self.__class__.__name__}.compare failed: {e}")
            return {"winner": "A", "confidence": 0.5, "reasoning": str(e)}

    def _parse_json(self, text: str, default: dict) -> dict:
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        # Use raw_decode to find the first valid JSON object without greedy matching
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch == "{":
                try:
                    obj, _ = decoder.raw_decode(text, i)
                    return obj
                except json.JSONDecodeError:
                    continue
        return default

    @abstractmethod
    def _parse_score(self, response: str, recommendation: Any):
        ...

    @abstractmethod
    def _neutral_score(self, reason: str):
        ...
