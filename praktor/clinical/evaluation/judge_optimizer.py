"""
Judge prompt calibration using the golden dataset.

Runs reference outputs (known-good) through each judge and measures
calibration error. If scores are systematically low, injects few-shot
examples into the judge prompts and stores an improved version in
PromptRegistry under the key "judge_hedis" / "judge_diabetes_hedis".

Usage:
    python -m praktor judge-optimize             # calibrate both judges
    python -m praktor judge-optimize --agent hedis_gap

    # Programmatic:
    from praktor.clinical.evaluation.judge_optimizer import calibrate_judges
    import asyncio
    report = asyncio.run(calibrate_judges())
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass
from typing import Any

from praktor.settings import create_log, MODEL

log = create_log()

# Scores below this threshold on reference (known-good) outputs
# indicate under-calibration — trigger prompt refinement.
_CALIBRATION_THRESHOLD = 7.0

# Number of golden samples to include as few-shot examples in the prompt
_FEW_SHOT_COUNT = 3

# Maps agent_type → PromptRegistry key. Single source of truth imported by
# golden_dataset.py and production_eval.py — change here to change everywhere.
_REGISTRY_KEYS: dict[str, str] = {
    "hedis_gap":      "judge_hedis",
    "diabetes_hedis": "judge_diabetes_hedis",
}


@dataclass
class CalibrationReport:
    agent_type: str
    n_samples: int
    mean_score_before: float
    mean_score_after: float | None
    criteria_means: dict[str, float]
    needs_calibration: bool
    prompt_version_id: str | None
    notes: str

    def print_summary(self) -> None:
        arrow = f"→ {self.mean_score_after:.2f}" if self.mean_score_after else ""
        print(f"\n{'─'*60}")
        print(f"  Judge calibration: {self.agent_type}")
        print(f"  Samples: {self.n_samples}  mean score: {self.mean_score_before:.2f} {arrow}")
        print(f"  Calibration needed: {'YES' if self.needs_calibration else 'no'}")
        print(f"  Criteria means:")
        for k, v in self.criteria_means.items():
            flag = " ← low" if v < _CALIBRATION_THRESHOLD else ""
            print(f"    {k:<32}: {v:.2f}{flag}")
        if self.prompt_version_id:
            print(f"  New prompt version: {self.prompt_version_id}")
        if self.notes:
            print(f"  Notes: {self.notes}")
        print()


async def _score_reference_outputs(judge, samples: list) -> list[Any]:
    """Run judge on each sample's reference output. Returns list of score objects."""
    scores = []
    for sample in samples:
        try:
            score = await judge.evaluate(
                recommendation=sample.reference_output,
                member_context=sample.clinical_scenario,
                outcome=sample.outcome,
            )
            scores.append(score)
        except Exception as e:
            log.warning(f"judge calibration: eval failed for {sample.sample_id}: {e}")
    return scores


def _compute_criteria_means(scores: list, criteria_keys: list[str]) -> dict[str, float]:
    means = {}
    for key in criteria_keys:
        vals = [getattr(s, key, None) for s in scores if getattr(s, key, None) is not None]
        means[key] = statistics.mean(vals) if vals else 0.0
    return means


def create_calibrated_judge(judge_cls, agent_type: str, model: str | None = None):
    """
    Create a judge, loading the active calibrated prompt from PromptRegistry if available.

    Falls back to the judge's default hardcoded prompt when:
      - agent_type has no registry key mapping
      - no active version exists in the registry
      - the registry raises (missing config, schema change, permissions)
    """
    from praktor.settings import MODEL
    effective_model = model or MODEL
    judge = judge_cls(model=effective_model)

    registry_key = _REGISTRY_KEYS.get(agent_type)
    if not registry_key:
        return judge

    try:
        from praktor.core.prompt_registry import PromptRegistry
        from praktor.LLM.llm_interface import AsyncLLMAdapter
        registry = PromptRegistry()
        active = registry.get_active(registry_key)
        if active:
            judge._eval_adapter = AsyncLLMAdapter(
                prompt_template=active.template,
                model=effective_model,
                temperature=0.0,
            )
            log.info(
                f"Loaded calibrated prompt {active.version_id[:8]} "
                f"for {registry_key} (evals={active.eval_count}, score={active.avg_score})"
            )
    except Exception as e:
        log.warning(
            f"create_calibrated_judge: registry lookup failed for {registry_key}, "
            f"using default prompt: {e}"
        )

    return judge


async def ensure_judges_calibrated(
    agent_type: str | None = None,
    verbose: bool = True,
) -> None:
    """
    Auto-calibrate judges that have no active calibrated version in PromptRegistry.

    Called at the top of run_offline_eval() and run_demo() so the first eval
    run automatically calibrates rather than requiring a manual judge-optimize step.
    """
    from praktor.core.prompt_registry import PromptRegistry
    registry = PromptRegistry()
    types = [agent_type] if agent_type else list(_REGISTRY_KEYS.keys())
    needs_cal = [t for t in types if registry.get_active(_REGISTRY_KEYS[t]) is None]

    if not needs_cal:
        return

    if verbose:
        print(f"No calibrated judge found for {needs_cal} — auto-calibrating...")

    cal_agent = needs_cal[0] if len(needs_cal) == 1 else None
    await calibrate_judges(agent_type=cal_agent, verbose=verbose)


def _build_few_shot_block(samples: list, n: int) -> str:
    """
    Build a few-shot calibration block from N golden samples.
    Shows what a high-quality recommendation looks like.
    """
    chosen = samples[:n]
    lines = ["\n--- CALIBRATION EXAMPLES (high-quality reference responses) ---\n"]
    for s in chosen:
        lines.append(f"Example (scenario: {s.clinical_scenario[:100]}...):")
        lines.append(f"Reference response:\n{s.reference_output}\n")
        lines.append(f"Expected score range: 8-9/10 for most criteria.\n")
    return "\n".join(lines)


async def calibrate_judges(
    agent_type: str | None = None,
    model: str | None = None,
    verbose: bool = True,
) -> list[CalibrationReport]:
    """
    Calibrate AI judges using the golden dataset.

    For each judge:
      1. Score all reference outputs (known-good responses)
      2. Compute per-criterion calibration error
      3. If mean < threshold, inject few-shot examples into the prompt
      4. Re-score a subset to verify improvement
      5. Store improved prompt in PromptRegistry

    Returns list of CalibrationReport (one per agent type).
    """
    from praktor.clinical.evaluation.golden_dataset import load_golden_samples
    from praktor.clinical.evaluation.hedis_judge import HEDISJudge, _CLINICAL_EVAL_PROMPT
    from praktor.clinical.evaluation.diabetes_hedis_judge import (
        DiabetesHEDISJudge, _DIABETES_EVAL_PROMPT,
    )
    from praktor.core.prompt_registry import PromptRegistry

    registry = PromptRegistry()
    effective_model = model or MODEL
    reports = []

    configs = {
        "hedis_gap": {
            "judge_cls": HEDISJudge,
            "base_prompt": _CLINICAL_EVAL_PROMPT,
            "registry_key": _REGISTRY_KEYS["hedis_gap"],
            "criteria": [
                "accuracy", "completeness", "relevance", "conciseness", "clarity",
                "gap_identification_accuracy", "action_appropriateness",
                "evidence_citation_quality", "safety_flag_coverage",
            ],
        },
        "diabetes_hedis": {
            "judge_cls": DiabetesHEDISJudge,
            "base_prompt": _DIABETES_EVAL_PROMPT,
            "registry_key": _REGISTRY_KEYS["diabetes_hedis"],
            "criteria": [
                "accuracy", "completeness", "relevance", "conciseness", "clarity",
                "inertia_detection_accuracy", "escalation_ladder_correctness",
                "gap_stacking_completeness", "evidence_anchor_quality",
                "safety_exclusion_coverage",
            ],
        },
    }

    types = [agent_type] if agent_type else ["hedis_gap", "diabetes_hedis"]

    for atype in types:
        cfg = configs[atype]
        samples = load_golden_samples(agent_type=atype)

        if verbose:
            print(f"\nCalibrating judge for '{atype}' using {len(samples)} golden samples...")

        judge = cfg["judge_cls"](model=effective_model)

        # Step 1: score reference outputs — exclude promoted samples (measurement_year=0)
        # because their clinical_scenario is a session ID, not a real clinical context.
        scoring_samples = [s for s in samples if s.measurement_year != 0]
        scores_before = await _score_reference_outputs(judge, scoring_samples)
        if not scores_before:
            reports.append(CalibrationReport(
                agent_type=atype, n_samples=0,
                mean_score_before=0.0, mean_score_after=None,
                criteria_means={}, needs_calibration=False,
                prompt_version_id=None, notes="no scores obtained",
            ))
            continue

        means_before = _compute_criteria_means(scores_before, cfg["criteria"])
        overall_before = statistics.mean(
            getattr(s, "overall", 5.0) for s in scores_before
        )
        needs_cal = overall_before < _CALIBRATION_THRESHOLD

        if verbose:
            print(f"  Mean score on reference outputs: {overall_before:.2f}/10 "
                  f"({'calibration needed' if needs_cal else 'OK'})")

        version_id = None
        overall_after = None

        if needs_cal:
            if verbose:
                print(f"  Score below {_CALIBRATION_THRESHOLD} — injecting few-shot calibration examples...")

            few_shot = _build_few_shot_block(samples, _FEW_SHOT_COUNT)
            calibrated_prompt = cfg["base_prompt"] + few_shot

            # Save calibrated prompt to PromptRegistry
            try:
                existing = registry.get_active(cfg["registry_key"])
                if existing is None:
                    # Create initial version from base prompt
                    ver = registry.save(
                        agent_name=cfg["registry_key"],
                        prompt_template=cfg["base_prompt"],
                        notes="Initial judge prompt",
                    )
                    registry.set_active(cfg["registry_key"], ver.version_id)

                # Save calibrated version
                cal_ver = registry.save(
                    agent_name=cfg["registry_key"],
                    prompt_template=calibrated_prompt,
                    notes=f"Calibrated: few-shot from golden dataset "
                          f"(mean before={overall_before:.2f})",
                )
                registry.set_active(cfg["registry_key"], cal_ver.version_id)
                version_id = cal_ver.version_id

                # Verify: re-score 3 samples with calibrated judge
                cal_judge = cfg["judge_cls"](model=effective_model)
                # Temporarily patch the eval prompt
                cal_judge._eval_adapter = None
                from praktor.LLM.llm_interface import AsyncLLMAdapter
                cal_judge._eval_adapter = AsyncLLMAdapter(
                    prompt_template=calibrated_prompt,
                    model=effective_model,
                    temperature=0.0,
                )

                verify_samples = samples[:3]
                scores_after = await _score_reference_outputs(cal_judge, verify_samples)
                if scores_after:
                    overall_after = statistics.mean(
                        getattr(s, "overall", 5.0) for s in scores_after
                    )
                    if verbose:
                        print(f"  Verification score: {overall_after:.2f}/10 "
                              f"(Δ={overall_after - overall_before:+.2f})")
                        registry.record_eval(
                            cfg["registry_key"], version_id,
                            score=overall_after, latency_ms=0.0,
                        )

            except Exception as e:
                log.warning(f"Judge calibration prompt save failed: {e}")
                if verbose:
                    print(f"  Warning: prompt save failed: {e}")

        report = CalibrationReport(
            agent_type=atype,
            n_samples=len(scoring_samples),
            mean_score_before=overall_before,
            mean_score_after=overall_after,
            criteria_means=means_before,
            needs_calibration=needs_cal,
            prompt_version_id=version_id,
            notes="" if needs_cal else "Judge well-calibrated — no changes needed.",
        )
        if verbose:
            report.print_summary()
        reports.append(report)

    return reports
