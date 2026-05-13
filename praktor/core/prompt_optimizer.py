"""
Automated prompt optimizer — two modes, one interface.

    optimizer = PromptOptimizer(agent_name="cover_letter", model="llama3:8b")
    new_version = await optimizer.optimize(
        examples=[{"input": {...}, "output": "..."}],
        metric=lambda score: score >= 7.0,
    )
    print(new_version.version_id)

Native mode (always available):
    A meta-LLM receives the current prompt, a sample of past evaluations,
    and a rewrite instruction. It returns an improved prompt. The new version
    is saved to PromptRegistry and scored with JudgeEvaluator.

DSPy mode (activates automatically when dspy-ai is installed):
    Uses BootstrapFewShot / MIPROv2 to compile a better prompt via
    few-shot learning. Requires a callable metric function.

Both modes produce a new PromptVersion saved to the registry.
Activate the new version explicitly with registry.set_active(agent_name, id).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable

from praktor.core.judge import JudgeEvaluator, JudgeScore
from praktor.core.prompt_registry import PromptRegistry, PromptVersion
from praktor.LLM.llm_interface import AsyncLLMAdapter
from praktor.settings import MODEL, OLLAMA_HOST, create_log

log = create_log()

# ---------------------------------------------------------------------------
# Meta-prompt for native optimizer (COPRO-style rewrite)
# ---------------------------------------------------------------------------

_META_PROMPT = """\
You are an expert prompt engineer. Your task is to improve an AI assistant's \
system prompt based on evaluation feedback.

CURRENT PROMPT:
{current_prompt}

EVALUATION FEEDBACK (recent examples with scores):
{feedback}

OPTIMIZATION GOAL:
{goal}

Rules for rewriting:
1. Keep all essential placeholders (e.g. {{question}}, {{history}}) exactly as-is.
2. Be concrete — replace vague instructions with specific guidance.
3. Add examples or format hints where the feedback shows confusion.
4. Cut filler words and redundant instructions.
5. Do NOT add meta-commentary, markdown fences, or explanations.

Return ONLY the improved prompt text, nothing else."""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class OptimizationResult:
    """Outcome of one optimization run."""
    version: PromptVersion
    score_before: float | None
    score_after: float | None
    mode: str                    # "native" or "dspy"
    notes: str = ""

    def improved(self) -> bool:
        if self.score_before is None or self.score_after is None:
            return True
        return self.score_after > self.score_before

    def summary(self) -> str:
        before = f"{self.score_before:.1f}" if self.score_before is not None else "—"
        after  = f"{self.score_after:.1f}"  if self.score_after  is not None else "—"
        arrow  = "↑" if self.improved() else "↓"
        return (
            f"[{self.mode}] {before} → {after} {arrow}  "
            f"version={self.version.short_id()}  {self.notes[:60]}"
        )


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class PromptOptimizer:
    """
    Automated prompt optimizer for a single agent.

    Picks the backend automatically:
    - DSPy backend: when dspy-ai is installed and `use_dspy=True` (default)
    - Native backend: always available (meta-LLM rewrite)

    Args:
        agent_name: Name of the agent whose prompt to optimize.
        model:      LLM model for both optimization and evaluation.
        registry:   PromptRegistry instance (default: global store).
        judge:      JudgeEvaluator instance (default: same model).
        use_dspy:   Try DSPy backend first (falls back to native on ImportError).
        store_dir:  Optional override for PromptRegistry store directory.
    """

    def __init__(
        self,
        agent_name: str,
        model: str = MODEL,
        registry: PromptRegistry | None = None,
        judge: JudgeEvaluator | None = None,
        use_dspy: bool = True,
        store_dir: str | None = None,
        max_trials: int = 20,
    ) -> None:
        self.agent_name = agent_name
        self.model = model
        self.registry = registry or PromptRegistry(store_dir)
        self.judge = judge or JudgeEvaluator(model=model)
        self._use_dspy = use_dspy
        # max_trials is stored for Phase 2 Pareto search.
        # In Phase 1, effective DSPy trial budget is controlled by auto="light" (~7 trials).
        self.max_trials = max_trials
        self._meta_adapter = AsyncLLMAdapter(
            prompt_template=_META_PROMPT,
            model=model,
            temperature=0.4,   # slight creativity for rewrites
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def optimize(
        self,
        examples: list[dict[str, Any]],
        *,
        metric: Callable[[float], bool] | None = None,
        goal: str = "Improve clarity, accuracy, and response quality.",
        notes: str = "",
    ) -> OptimizationResult:
        """
        Run one optimization cycle.

        Args:
            examples: List of {"input": dict, "output": str} dicts.
                      "input" is the payload dict passed to the agent.
                      "output" is the agent's actual response.
            metric:   Optional callable(score) → bool that says "good enough".
                      Used by DSPy backend; ignored in native mode.
            goal:     Natural-language description of what to improve.
            notes:    Notes to attach to the new PromptVersion.

        Returns:
            OptimizationResult with the new version and before/after scores.
        """
        active = self.registry.get_active(self.agent_name)
        if active is None:
            raise ValueError(
                f"No active prompt version for agent '{self.agent_name}'. "
                "Save and activate a version first."
            )

        score_before = active.avg_score

        if self._use_dspy:
            try:
                return await self._optimize_dspy(active, examples, metric, goal, notes)
            except ImportError:
                log.info("dspy-ai not installed — falling back to native optimizer")
            except Exception as e:
                log.warning(f"DSPy optimization failed ({e}) — falling back to native")

        return await self._optimize_native(active, examples, goal, notes)

    async def evaluate_and_record(
        self,
        version_id: str,
        question: str,
        response: str,
        expected: str = "",
    ) -> JudgeScore:
        """
        Evaluate a response and record the score in the registry.

        Convenience method: judge → record_eval → return score.
        """
        score = await self.judge.evaluate(question, response, expected)
        # latency_ms is not available here; use 0 as placeholder
        self.registry.record_eval(
            self.agent_name, version_id, score.score, latency_ms=0.0
        )
        return score

    # ------------------------------------------------------------------
    # Native backend
    # ------------------------------------------------------------------

    async def _optimize_native(
        self,
        active: PromptVersion,
        examples: list[dict[str, Any]],
        goal: str,
        notes: str,
    ) -> OptimizationResult:
        """COPRO-style meta-LLM rewrite."""
        feedback = self._format_feedback(examples)

        new_template = await self._meta_adapter.ainvoke({
            "current_prompt": active.template,
            "feedback": feedback,
            "goal": goal,
        })
        new_template = new_template.strip()

        if not new_template or new_template == active.template:
            log.info("Native optimizer: no change produced — returning current version")
            return OptimizationResult(
                version=active,
                score_before=active.avg_score,
                score_after=active.avg_score,
                mode="native",
                notes="no change",
            )

        new_version = self.registry.save(
            self.agent_name,
            template=new_template,
            notes=notes or f"native-opt: {goal[:60]}",
        )

        # Quick evaluation using the provided examples
        score_after = await self._eval_on_examples(new_template, examples)
        if score_after is not None:
            self.registry.record_eval(
                self.agent_name, new_version.version_id,
                score=score_after, latency_ms=0.0,
            )
            new_version.avg_score = score_after

        log.info(
            f"Native optimizer: {active.short_id()} → {new_version.short_id()}  "
            f"score {active.avg_score} → {score_after}"
        )
        return OptimizationResult(
            version=new_version,
            score_before=active.avg_score,
            score_after=score_after,
            mode="native",
            notes=new_version.notes,
        )

    # ------------------------------------------------------------------
    # DSPy backend
    # ------------------------------------------------------------------

    async def _optimize_dspy(
        self,
        active: PromptVersion,
        examples: list[dict[str, Any]],
        metric: Callable[[float], bool] | None,
        goal: str,
        notes: str,
    ) -> OptimizationResult:
        """
        DSPy BootstrapFewShot optimization.

        Compiles a Predict module whose signature is derived from the
        input/output keys of the provided examples. The compiled module's
        best prompt is extracted and saved as a new PromptVersion.
        """
        import dspy  # type: ignore[import]

        # Wire DSPy to the same LLM
        lm = self._make_dspy_lm()
        dspy.configure(lm=lm)

        # Build a dynamic signature from example keys
        input_keys = list(examples[0]["input"].keys()) if examples else ["question"]
        sig = self._build_signature(input_keys)

        # Convert examples to dspy.Example objects
        dspy_examples = [
            dspy.Example(
                **ex["input"],
                output=ex.get("output", ""),
            ).with_inputs(*input_keys)
            for ex in examples
        ]

        # MIPROv2 requires enough examples for a meaningful train/val split.
        if len(dspy_examples) < 15:
            log.warning(
                f"MIPROv2 requires 15+ examples for meaningful instruction search; "
                f"got {len(dspy_examples)} — falling back to native optimizer."
            )
            raise ValueError("insufficient_examples_for_miprov2")

        # Define metric function
        def _metric(example, prediction, trace=None):
            response = getattr(prediction, "output", str(prediction))
            question = getattr(example, input_keys[0], "")
            # Run sync evaluate inside DSPy's synchronous metric contract
            loop = asyncio.new_event_loop()
            try:
                score_obj = loop.run_until_complete(
                    self.judge.evaluate(str(question), str(response))
                )
                if metric is not None:
                    return metric(score_obj.score)
                return score_obj.score >= 7.0
            finally:
                loop.close()

        program = dspy.Predict(sig)
        # MIPROv2 jointly optimizes instructions and few-shot demonstrations via
        # Bayesian search. auto="light" runs ~7 trials — appropriate for small
        # golden datasets. Switch to "medium" (~25 trials) when n >= 30.
        # Do NOT pass num_trials alongside auto= — the preset owns the trial budget.
        try:
            optimizer = dspy.teleprompt.MIPROv2(
                metric=_metric,
                auto="light",
                max_bootstrapped_demos=3,
                max_labeled_demos=3,
                requires_permission_to_run=False,
            )
        except (AttributeError, TypeError):
            # DSPy version doesn't have MIPROv2 — fall back to BootstrapFewShot
            log.warning("MIPROv2 not available in installed DSPy version — using BootstrapFewShot")
            optimizer = dspy.teleprompt.BootstrapFewShot(metric=_metric, max_bootstrapped_demos=3)

        # Compile runs synchronously (DSPy internal)
        compiled = await asyncio.to_thread(
            optimizer.compile, program, trainset=dspy_examples
        )

        # Extract the best prompt text from the compiled predictor
        new_template = self._extract_dspy_prompt(compiled, active.template)

        new_version = self.registry.save(
            self.agent_name,
            template=new_template,
            notes=notes or f"dspy-opt: {goal[:60]}",
        )

        score_after = await self._eval_on_examples(new_template, examples)
        if score_after is not None:
            self.registry.record_eval(
                self.agent_name, new_version.version_id,
                score=score_after, latency_ms=0.0,
            )
            new_version.avg_score = score_after

        log.info(
            f"DSPy optimizer: {active.short_id()} → {new_version.short_id()}  "
            f"score {active.avg_score} → {score_after}"
        )
        return OptimizationResult(
            version=new_version,
            score_before=active.avg_score,
            score_after=score_after,
            mode="dspy",
            notes=new_version.notes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_dspy_lm(self) -> Any:
        """Create a DSPy LM from the optimizer's model string."""
        import dspy  # type: ignore[import]

        model = self.model

        # Ollama models: prepend provider prefix if needed
        if "/" not in model and not model.startswith(("gpt-", "claude-", "gemini-")):
            base = OLLAMA_HOST or "http://localhost:11434"
            return dspy.LM(f"ollama_chat/{model}", api_base=base, api_key="ollama")

        # OpenAI
        if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
            return dspy.LM(f"openai/{model}")

        # Anthropic
        if model.startswith("claude-"):
            return dspy.LM(f"anthropic/{model}")

        # Fallback: pass as-is (litellm routing)
        return dspy.LM(model)

    @staticmethod
    def _build_signature(input_keys: list[str]) -> type:
        """Dynamically build a dspy.Signature class from input key names."""
        import dspy  # type: ignore[import]

        fields: dict[str, Any] = {}
        for key in input_keys:
            fields[key] = dspy.InputField(desc=key)
        fields["output"] = dspy.OutputField(desc="response")

        return type("DynamicSignature", (dspy.Signature,), fields)

    @staticmethod
    def _extract_dspy_prompt(compiled: Any, fallback: str) -> str:
        """
        Pull the optimized instruction + few-shot demos from a compiled DSPy module.

        DSPy 2.5+: instruction lives at compiled.predictors()[0].signature.instructions
        Older DSPy: falls back to reading compiled.demos only.
        Both: appends few-shot examples block to the instruction text.
        """
        instruction = fallback
        try:
            # DSPy 2.5+ attribute path (verify against dir(compiled) if this breaks)
            instruction = compiled.predictors()[0].signature.instructions or fallback
        except (AttributeError, IndexError, TypeError):
            pass

        try:
            demos = compiled.demos if hasattr(compiled, "demos") else []
            if not demos:
                return instruction

            examples_block = "\n\n".join(
                "Example:\n" + "\n".join(f"  {k}: {v}" for k, v in d.items() if k != "output")
                + f"\n  → {d.get('output', '')}"
                for d in demos[:3]
            )
            return f"{instruction}\n\n{examples_block}"
        except Exception:
            return instruction

    def _format_feedback(self, examples: list[dict[str, Any]]) -> str:
        """Format examples+scores as readable feedback for the meta-prompt."""
        lines = []
        for i, ex in enumerate(examples[:8], 1):
            inp = ex.get("input", {})
            out = ex.get("output", "")
            score = ex.get("score")
            score_str = f"score={score:.1f}/10" if score is not None else "score=unknown"
            lines.append(
                f"[{i}] {score_str}\n"
                f"  Input: {json.dumps(inp, ensure_ascii=False)[:120]}\n"
                f"  Output: {out[:160]}"
            )
        return "\n\n".join(lines) if lines else "(no examples provided)"

    async def _eval_on_examples(
        self,
        template: str,
        examples: list[dict[str, Any]],
        max_eval: int = 3,
    ) -> float | None:
        """
        Quickly score a template against the provided examples.

        Uses the judge to evaluate the first `max_eval` examples whose
        output is already known (i.e., examples that include "output").
        Returns the mean score, or None if no outputs are available.
        """
        scored = [e for e in examples if e.get("output")][:max_eval]
        if not scored:
            return None

        scores = await asyncio.gather(*[
            self.judge.evaluate(
                question=str(ex["input"].get("question", list(ex["input"].values())[0])),
                response=ex["output"],
            )
            for ex in scored
        ])
        return round(sum(s.score for s in scores) / len(scores), 2)
