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
import math
import statistics
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any, Literal

from praktor.LLM.llm_interface import AsyncLLMAdapter
from praktor.core.prompt_registry import PromptRegistry
from praktor.monitoring import record_kpi
from praktor.settings import create_log, MODEL

log = create_log()

# Scores below this threshold on reference (known-good) outputs
# indicate under-calibration — trigger prompt refinement.
_CALIBRATION_THRESHOLD = 7.0

# Number of golden samples to include as few-shot examples in the prompt
_FEW_SHOT_COUNT = 3

# Sample size estimation defaults.
# delta: minimum bias worth detecting (0.5 pts below threshold = meaningful miscalibration)
# alpha: one-tailed false-positive rate
# power: probability of detecting real bias
_SAMPLE_DELTA = 0.5
_SAMPLE_ALPHA = 0.05
_SAMPLE_POWER = 0.80
_SIGMA_FALLBACK = 1.5  # assumed σ when fewer than 2 scored samples

# Private mapping — source of truth for registry key lookup.
# Prefer reading from AgentDefinition.registry_key when available.
_AGENT_TYPE_REGISTRY: dict[str, str] = {
    "hedis_gap":        "judge_hedis",
    "diabetes_hedis":   "judge_diabetes_hedis",
    # General agents share one judge registry key
    "cover_letter":     "judge_general",
    "job_application":  "judge_general",
    "job_interview":    "judge_general",
    "keywords_extraction": "judge_general",
    "message":          "judge_general",
    "search":           "judge_general",
    "thank_you":        "judge_general",
}


def compute_required_n(
    sigma: float = _SIGMA_FALLBACK,
    delta: float = _SAMPLE_DELTA,
    alpha: float = _SAMPLE_ALPHA,
    power: float = _SAMPLE_POWER,
) -> int:
    """Minimum sample size for adequate power to detect undercalibration.

    One-tailed z-test: detect mean < _CALIBRATION_THRESHOLD with given power.
    n = ceil((z_α + z_β)² × σ² / δ²)

    Args:
        sigma: observed (or assumed) score standard deviation
        delta: minimum bias worth detecting (points below threshold)
        alpha: one-tailed false-positive rate
        power: probability of detecting real bias when it exists
    """
    z_alpha = NormalDist().inv_cdf(1 - alpha)
    z_beta = NormalDist().inv_cdf(power)
    return math.ceil((z_alpha + z_beta) ** 2 * sigma ** 2 / delta ** 2)


@dataclass
class ParetoCandidate:
    """One prompt candidate in the Pareto frontier search."""
    template: str
    criterion_scores: dict[str, float]   # e.g. {"gap_identification_accuracy": 8.2}
    aggregate_score: float
    round_generated: int                  # which search round produced this candidate
    version_id: str = ""                  # set after saving to PromptRegistry

    def dominates(self, other: "ParetoCandidate") -> bool:
        """True if self is ≥ other on ALL shared criteria AND > on at least one."""
        if not self.criterion_scores or not other.criterion_scores:
            return self.aggregate_score > other.aggregate_score
        criteria = set(self.criterion_scores) & set(other.criterion_scores)
        if not criteria:
            return self.aggregate_score > other.aggregate_score
        return (
            all(self.criterion_scores[c] >= other.criterion_scores[c] for c in criteria)
            and any(self.criterion_scores[c] > other.criterion_scores[c] for c in criteria)
        )

    def clears_threshold(self) -> bool:
        """True when every criterion scores ≥ _CALIBRATION_THRESHOLD (racer exit condition)."""
        return bool(self.criterion_scores) and all(
            v >= _CALIBRATION_THRESHOLD for v in self.criterion_scores.values()
        )


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
    required_n: int = 0
    sufficient_samples: bool = True
    # Pareto search results (populated only when search_mode="pareto")
    search_mode: str = "threshold"
    trials_run: int = 0
    budget_exhausted: bool = False
    pareto_frontier: list = field(default_factory=list)  # list[ParetoCandidate]

    def print_summary(self) -> None:
        arrow = f"→ {self.mean_score_after:.2f}" if self.mean_score_after else ""
        adequacy = (
            f"  ⚠ Underpowered: n={self.n_samples} < required {self.required_n} "
            f"(δ={_SAMPLE_DELTA}, power={int(_SAMPLE_POWER*100)}%)"
            if not self.sufficient_samples else
            f"  ✓ Sample size adequate: n={self.n_samples} ≥ required {self.required_n}"
        )
        print(f"\n{'─'*60}")
        print(f"  Judge calibration: {self.agent_type}")
        print(f"  Samples: {self.n_samples}  mean score: {self.mean_score_before:.2f} {arrow}")
        print(adequacy)
        print(f"  Calibration needed: {'YES' if self.needs_calibration else 'no'}")
        if self.search_mode == "pareto":
            status = "budget exhausted" if self.budget_exhausted else "converged"
            print(f"  Search: pareto  trials={self.trials_run}  ({status})")
            print(f"  Pareto frontier: {len(self.pareto_frontier)} candidate(s)")
        print(f"  Criteria means:")
        for k, v in self.criteria_means.items():
            flag = " ← low" if v < _CALIBRATION_THRESHOLD else ""
            print(f"    {k:<32}: {v:.2f}{flag}")
        if self.pareto_frontier:
            print(f"  Pareto frontier (best per criterion):")
            # For each criterion, show which candidate leads
            all_criteria = list(self.pareto_frontier[0].criterion_scores)
            for c in all_criteria:
                leader = max(self.pareto_frontier, key=lambda p: p.criterion_scores.get(c, 0))
                score = leader.criterion_scores.get(c, 0)
                flag = " ← low" if score < _CALIBRATION_THRESHOLD else ""
                print(f"    {c:<32}: {score:.2f}  (version {leader.version_id[:8]}){flag}")
        if self.prompt_version_id:
            print(f"  Active prompt version: {self.prompt_version_id}")
        if self.notes:
            print(f"  Notes: {self.notes}")
        print()


async def _score_reference_outputs(
    judge,
    samples: list,
    verbose: bool = True,
) -> list[Any]:
    """Run judge on each sample's reference output concurrently. Returns list of score objects."""
    from praktor.settings import PRAKTOR_JUDGE_CONCURRENCY
    sem = asyncio.Semaphore(PRAKTOR_JUDGE_CONCURRENCY)
    _first_error: list[str] = []  # capture first API error for user-visible reporting

    async def _eval_one(sample):
        async with sem:
            try:
                score = await judge.evaluate(
                    recommendation=sample.reference_output,
                    member_context=sample.clinical_scenario,
                    outcome=sample.outcome,
                )
                # Detect silent failure: neutral score stores the error in reasoning
                last_response = getattr(judge, '_last_eval_response', None)
                if last_response is None and not _first_error:
                    reason = getattr(score, 'reasoning', '')
                    if reason:
                        _first_error.append(reason)
                        log.error(f"judge calibration: LLM call failed: {reason}")
                        if verbose:
                            print(f"\n  ERROR: LLM call failed — {reason}", flush=True)
                return score
            except Exception as e:
                log.warning(f"judge calibration: eval failed for {sample.sample_id}: {e}")
                return None

    results = await asyncio.gather(*(_eval_one(s) for s in samples))
    valid = [r for r in results if r is not None]

    # If every score is a neutral fallback (all criteria = 5.0, stdev = 0),
    # the calibration run is invalid — warn loudly rather than silently proceeding.
    if valid and verbose:
        overall_scores = [getattr(s, 'overall', 5.0) for s in valid]
        if len(set(round(x, 4) for x in overall_scores)) == 1 and overall_scores[0] == 5.0:
            if not _first_error:
                print(
                    f"\n  WARNING: All {len(valid)} samples scored exactly 5.0 — "
                    f"this indicates a neutral fallback (LLM call failure). "
                    f"Check praktor.ai.log for the actual error.",
                    flush=True,
                )

    return valid


async def _score_paired(judge, samples: list, verbose: bool = False) -> list[tuple]:
    """Like _score_reference_outputs but returns (sample, score) pairs, preserving alignment.
    Pairs with failed evals (score=None) are dropped so callers never see misaligned zips.
    """
    results = await asyncio.gather(
        *(_eval_one_raw(judge, s) for s in samples), return_exceptions=True
    )
    pairs = []
    for s, r in zip(samples, results):
        if isinstance(r, Exception) or r is None:
            continue
        pairs.append((s, r))
    return pairs


async def _eval_one_raw(judge, sample):
    try:
        return await judge.evaluate(
            recommendation=sample.reference_output,
            member_context=sample.clinical_scenario,
            outcome=sample.outcome,
        )
    except Exception as e:
        log.warning(f"judge calibration: eval failed for {sample.sample_id}: {e}")
        return None


def _compute_criteria_means(scores: list, criteria_keys: list[str]) -> dict[str, float]:
    means = {}
    for key in criteria_keys:
        vals = [getattr(s, key, None) for s in scores if getattr(s, key, None) is not None]
        means[key] = statistics.mean(vals) if vals else 0.0
    return means


def create_calibrated_judge(
    judge_cls,
    agent_type: str,
    model: str | None = None,
    registry_key: str | None = None,
):
    """
    Create a judge, loading the active calibrated prompt from PromptRegistry if available.

    Falls back to the judge's default hardcoded prompt when:
      - agent_type has no registry key mapping
      - no active version exists in the registry
      - the registry raises (missing config, schema change, permissions)

    Prefer passing registry_key explicitly (from AgentDefinition.registry_key).
    Falls back to the built-in agent_type → registry_key lookup.
    """
    from praktor.settings import MODEL
    effective_model = model or MODEL
    judge = judge_cls(model=effective_model)

    resolved_key = registry_key or _AGENT_TYPE_REGISTRY.get(agent_type)
    if not resolved_key:
        return judge

    try:
        registry = PromptRegistry()
        active = registry.get_active(resolved_key)
        if active:
            judge._eval_adapter = AsyncLLMAdapter(
                prompt_template=active.template,
                model=effective_model,
                temperature=0.0,
            )
            log.info(
                f"Loaded calibrated prompt {active.version_id[:8]} "
                f"for {resolved_key} (evals={active.eval_count}, score={active.avg_score})"
            )
    except Exception as e:
        log.warning(
            f"create_calibrated_judge: registry lookup failed for {resolved_key}, "
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
    Collapses all general agent types to the single "judge_general" registry key.
    """
    from praktor.evaluation.general_golden_dataset import GENERAL_AGENT_TYPES
    registry = PromptRegistry()

    # Deduplicate registry keys — all general agents share "judge_general"
    _general_set = set(GENERAL_AGENT_TYPES)
    if agent_type:
        keys_to_check = {"judge_general"} if agent_type in _general_set else {_AGENT_TYPE_REGISTRY[agent_type]}
    else:
        keys_to_check = {"judge_hedis", "judge_diabetes_hedis", "judge_general"}

    missing_keys = {k for k in keys_to_check if registry.get_active(k) is None}
    if not missing_keys:
        return

    if verbose:
        print(f"No calibrated judge found for registry keys {missing_keys} — auto-calibrating...")

    # Map missing keys back to calibrate_judges() agent_type argument
    _key_to_cal_type = {
        "judge_hedis": "hedis_gap",
        "judge_diabetes_hedis": "diabetes_hedis",
        "judge_general": "general",
    }
    for key in missing_keys:
        cal_type = _key_to_cal_type.get(key)
        await calibrate_judges(agent_type=cal_type, verbose=verbose)


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


# ---------------------------------------------------------------------------
# Pareto search helpers
# ---------------------------------------------------------------------------

_PARETO_META_PROMPT = """\
You are an expert prompt engineer optimizing a clinical AI judge prompt.
Your goal is to improve the weakest-scoring criterion without degrading the others.

CURRENT PROMPT:
{current_prompt}

CRITERION SCORES (mean across the golden dataset):
{criterion_scores_table}

WEAKEST CRITERION: {weakest_criterion} (score: {weakest_score:.2f}/10)

EXAMPLES THAT SCORED LOWEST ON {weakest_criterion}:
{low_scoring_examples}

Write an improved judge prompt that specifically addresses the weakest criterion.
Rules:
1. Keep all essential placeholders ({{recommendation}}, {{member_context}}, etc.) exactly as-is.
2. Add concrete, specific guidance for {weakest_criterion} — not generic instructions.
3. Do NOT add meta-commentary, markdown fences, or explanations.
4. Return ONLY the improved prompt text, nothing else."""


async def _run_pareto_search(
    judge_cls,
    base_prompt: str,
    registry_key: str,
    samples: list,
    criteria: list[str],
    model: str,
    registry: PromptRegistry,
    max_trials: int,
    candidates_per_round: int,
    verbose: bool,
) -> tuple[list[ParetoCandidate], int, bool]:
    """
    GEPA-inspired Pareto frontier search over judge prompts.

    Each round: generate candidates targeting the weakest criterion, score on
    all golden samples, keep only Pareto-non-dominated prompts.

    Returns: (pareto_frontier, trials_run, budget_exhausted)
    """
    from praktor.LLM.llm_interface import AsyncLLMAdapter

    meta_adapter = AsyncLLMAdapter(
        prompt_template=_PARETO_META_PROMPT,
        model=model,
        temperature=0.4,
    )

    # Estimate call count so the user can make an informed budget decision
    n_scoring_calls = candidates_per_round * max_trials * len(samples)
    if verbose:
        print(
            f"  Pareto search: up to {max_trials} rounds × {candidates_per_round} candidates "
            f"× {len(samples)} samples = ~{n_scoring_calls} judge calls "
            f"+ ~{max_trials * candidates_per_round} meta-LLM calls"
        )

    # Round 0: score the base prompt
    base_judge = judge_cls(model=model)
    base_judge._eval_adapter = AsyncLLMAdapter(
        prompt_template=base_prompt, model=model, temperature=0.0
    )
    base_pairs = await _score_paired(base_judge, samples)
    if not base_pairs:
        return [], 0, False
    base_scores = [sc for _, sc in base_pairs]

    base_criterion_means = _compute_criteria_means(base_scores, criteria)
    base_agg = statistics.mean(
        getattr(s, "overall", 5.0) for s in base_scores
    )
    seed = ParetoCandidate(
        template=base_prompt,
        criterion_scores=base_criterion_means,
        aggregate_score=base_agg,
        round_generated=0,
    )
    pool: list[ParetoCandidate] = [seed]
    frontier: list[ParetoCandidate] = [seed]
    # Map template → aligned (sample, score) pairs for _build_low_scoring_examples
    frontier_raw_scores: dict[str, list[tuple]] = {base_prompt: base_pairs}

    trials_run = 0
    no_improvement_streak = 0
    prev_best_agg = base_agg

    for round_idx in range(1, max_trials + 1):
        trials_run = round_idx
        prev_frontier_size = len(frontier)

        # Pick the current best candidate as the template for this round
        current_best = max(frontier, key=lambda c: c.aggregate_score)

        # Identify the weakest criterion in the current best
        weakest = min(
            current_best.criterion_scores,
            key=lambda k: current_best.criterion_scores[k],
        )
        weakest_score = current_best.criterion_scores[weakest]

        # Build criterion table for the meta-prompt
        crit_table = "\n".join(
            f"  {k:<32}: {v:.2f}/10{'  ← LOWEST' if k == weakest else ''}"
            for k, v in sorted(
                current_best.criterion_scores.items(), key=lambda x: x[1]
            )
        )

        # Pull low-scoring examples for the weakest criterion from the current best's raw scores
        current_best_pairs = frontier_raw_scores.get(current_best.template, base_pairs)
        low_examples_block = _build_low_scoring_examples(current_best_pairs, weakest, n=2)

        # Generate candidates_per_round variant prompts in parallel
        async def _gen_one(_):
            try:
                return await meta_adapter.ainvoke({
                    "current_prompt": current_best.template,
                    "criterion_scores_table": crit_table,
                    "weakest_criterion": weakest,
                    "weakest_score": weakest_score,
                    "low_scoring_examples": low_examples_block,
                })
            except Exception as e:
                log.warning(f"Pareto meta-LLM call failed: {e}")
                return None

        raw_candidates = await asyncio.gather(*(_gen_one(i) for i in range(candidates_per_round)))
        new_templates = [t.strip() for t in raw_candidates if t and t.strip()]

        # Score each new candidate
        round_improved = False
        for template in new_templates:
            if template == current_best.template:
                continue  # meta-LLM returned the same prompt — skip
            cand_judge = judge_cls(model=model)
            cand_judge._eval_adapter = AsyncLLMAdapter(
                prompt_template=template, model=model, temperature=0.0
            )
            cand_pairs = await _score_paired(cand_judge, samples)
            if not cand_pairs:
                continue
            cand_scores = [sc for _, sc in cand_pairs]
            cand_crit = _compute_criteria_means(cand_scores, criteria)
            cand_agg = statistics.mean(getattr(s, "overall", 5.0) for s in cand_scores)
            cand = ParetoCandidate(
                template=template,
                criterion_scores=cand_crit,
                aggregate_score=cand_agg,
                round_generated=round_idx,
            )
            pool.append(cand)

            # Update frontier: keep only non-dominated candidates
            new_frontier = []
            dominated_by_cand = False
            for existing in frontier:
                if cand.dominates(existing):
                    round_improved = True  # candidate beats at least one existing
                    continue              # drop dominated
                new_frontier.append(existing)
                if existing.dominates(cand):
                    dominated_by_cand = True
            if not dominated_by_cand:
                new_frontier.append(cand)
                frontier_raw_scores[template] = cand_pairs
            frontier = new_frontier

            # Racer: any candidate clears all criteria → stop immediately
            if cand.clears_threshold():
                if verbose:
                    print(f"  Round {round_idx}: racer exit — candidate clears {_CALIBRATION_THRESHOLD} on all criteria")
                return frontier, trials_run, False

        best_agg_now = max(c.aggregate_score for c in frontier)
        if verbose:
            print(
                f"  Round {round_idx}/{max_trials}: frontier size={len(frontier)}  "
                f"best_agg={best_agg_now:.2f}  weakest_criterion={weakest} ({weakest_score:.2f})"
            )

        frontier_grew = len(frontier) > prev_frontier_size
        if not round_improved and not frontier_grew or best_agg_now <= prev_best_agg:
            no_improvement_streak += 1
        else:
            no_improvement_streak = 0
        prev_best_agg = best_agg_now

        if no_improvement_streak >= 2:
            if verbose:
                print(f"  Round {round_idx}: no improvement in 2 consecutive rounds — stopping early")
            return frontier, trials_run, False

    return frontier, trials_run, True  # budget exhausted


def _build_low_scoring_examples(
    sample_score_pairs: list, criterion: str, n: int = 2
) -> str:
    """Return the n samples that scored lowest on criterion — gives the meta-LLM the right failure signal.

    sample_score_pairs: list of (sample, score) tuples — pre-aligned, no Nones.
    """
    paired = [
        (s, getattr(sc, criterion, 5.0))
        for s, sc in sample_score_pairs
    ]
    paired.sort(key=lambda x: x[1])
    lines = []
    for s, score in paired[:n]:
        lines.append(f"Scenario: {s.clinical_scenario[:200]}")
        lines.append(f"Reference output: {s.reference_output[:300]}")
        lines.append(f"Score on {criterion}: {score:.1f}/10")
        lines.append("")
    return "\n".join(lines) if lines else "(no examples available)"


async def calibrate_judges(
    agent_type: str | None = None,
    model: str | None = None,
    verbose: bool = True,
    search_mode: Literal["threshold", "pareto"] = "threshold",
    max_trials: int = 10,
    candidates_per_round: int = 3,
) -> list[CalibrationReport]:
    """
    Calibrate AI judges using the golden dataset.

    search_mode="threshold" (default):
      Injects few-shot examples when aggregate score < threshold. One-shot.

    search_mode="pareto":
      Runs a GEPA-inspired Pareto frontier search: generates candidate prompts
      targeting the weakest criterion each round, scores all candidates on the
      full golden dataset, keeps the Pareto-optimal set (non-dominated across
      all criteria), and activates the candidate with the highest aggregate score.
      Respects max_trials (budget cap) and exits early if a racer clears all
      criteria or if no improvement occurs in 2 consecutive rounds.

    Returns list of CalibrationReport (one per agent type).
    """
    from praktor.clinical.evaluation.golden_dataset import load_golden_samples
    from praktor.clinical.evaluation.hedis_judge import HEDISJudge, _CLINICAL_EVAL_PROMPT
    from praktor.clinical.evaluation.diabetes_hedis_judge import (
        DiabetesHEDISJudge, _DIABETES_EVAL_PROMPT,
    )
    from praktor.evaluation.general_judge import GeneralJudge, _GENERAL_EVAL_PROMPT
    from praktor.evaluation.general_golden_dataset import (
        load_general_golden_samples, GENERAL_AGENT_TYPES,
    )

    registry = PromptRegistry()
    effective_model = model or MODEL
    reports = []

    _std_criteria = ["accuracy", "completeness", "relevance", "conciseness", "clarity"]

    configs = {
        "hedis_gap": {
            "judge_cls": HEDISJudge,
            "base_prompt": _CLINICAL_EVAL_PROMPT,
            "registry_key": "judge_hedis",
            "criteria": _std_criteria + [
                "gap_identification_accuracy", "action_appropriateness",
                "evidence_citation_quality", "safety_flag_coverage",
            ],
        },
        "diabetes_hedis": {
            "judge_cls": DiabetesHEDISJudge,
            "base_prompt": _DIABETES_EVAL_PROMPT,
            "registry_key": "judge_diabetes_hedis",
            "criteria": _std_criteria + [
                "inertia_detection_accuracy", "escalation_ladder_correctness",
                "gap_stacking_completeness", "evidence_anchor_quality",
                "safety_exclusion_coverage",
            ],
        },
        # All general agents share one judge — calibrate once under the representative key
        "general": {
            "judge_cls": GeneralJudge,
            "base_prompt": _GENERAL_EVAL_PROMPT,
            "registry_key": "judge_general",
            "criteria": _std_criteria,
        },
    }

    # Resolve requested types → calibration configs
    # Clinical agents map 1:1; all general agent types collapse to "general"
    _general_agent_types = set(GENERAL_AGENT_TYPES)
    if agent_type:
        if agent_type in _general_agent_types:
            types = ["general"]
        else:
            types = [agent_type]
    else:
        types = ["hedis_gap", "diabetes_hedis", "general"]

    # Fast preflight: verify the LLM is reachable before scoring all samples.
    # A 400 "credit balance too low" or 401 "auth error" means every evaluate()
    # call will silently return neutral 5.0 — catch it here instead.
    try:
        _probe = AsyncLLMAdapter(
            prompt_template="Reply with the single word: OK",
            model=effective_model,
            temperature=0.5,  # non-zero → skip cache
        )
        _reply = await _probe.ainvoke({})
        if verbose:
            print(f"  LLM preflight OK ({effective_model}: {_reply.strip()[:30]})")
    except Exception as e:
        msg = str(e)
        print(f"\n  FATAL: LLM preflight failed — {msg}")
        print(f"  Calibration aborted. Fix the LLM connection/credentials and retry.\n")
        return []

    for atype in types:
        cfg = configs[atype]

        # Load the right golden dataset: general type uses GeneralGoldenSample list,
        # clinical types use the clinical GoldenSample list.
        if atype == "general":
            raw_samples = load_general_golden_samples()
            # Wrap general samples so _score_reference_outputs can call judge.evaluate()
            # with the right fields (reference_output / context / outcome=None)
            class _GeneralSampleAdapter:
                def __init__(self, s):
                    self.sample_id = s.sample_id
                    self.reference_output = s.reference_output
                    self.clinical_scenario = s.context
                    self.outcome = "ok"
                    self.measurement_year = 1  # not 0 — include in scoring
            samples = [_GeneralSampleAdapter(s) for s in raw_samples]
        else:
            samples = load_golden_samples(agent_type=atype)

        if verbose:
            print(f"\nCalibrating judge for '{atype}' using {len(samples)} golden samples...")

        judge = cfg["judge_cls"](model=effective_model)

        # Step 1: score reference outputs — exclude promoted samples (measurement_year=0)
        # because their clinical_scenario is a session ID, not a real clinical context.
        scoring_samples = [s for s in samples if s.measurement_year != 0]
        scores_before = await _score_reference_outputs(judge, scoring_samples, verbose=verbose)
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

        # Sample size estimation — σ from observed scores, fallback to assumed 1.5.
        # If stdev=0 (all neutral fallbacks), the distribution is degenerate — use fallback σ.
        overall_scores = [getattr(s, "overall", 5.0) for s in scores_before]
        sigma_obs = (
            statistics.stdev(overall_scores)
            if len(overall_scores) >= 2
            else _SIGMA_FALLBACK
        )
        sigma_obs = max(sigma_obs, _SIGMA_FALLBACK)  # floor at assumed σ to avoid n=0
        required_n = compute_required_n(sigma=sigma_obs)
        sufficient = len(scores_before) >= required_n

        record_kpi(f"judge.calibration.score_before.{atype}", overall_before)
        record_kpi(f"judge.calibration.n_samples.{atype}", len(scores_before))
        record_kpi(f"judge.calibration.n_required.{atype}", required_n)

        if verbose:
            print(f"  Mean score on reference outputs: {overall_before:.2f}/10 "
                  f"({'calibration needed' if needs_cal else 'OK'})")
            if not sufficient:
                print(
                    f"  ⚠ WARNING: n={len(scores_before)} samples — need {required_n} for "
                    f"{int(_SAMPLE_POWER*100)}% power to detect {_SAMPLE_DELTA}-pt bias "
                    f"(σ≈{sigma_obs:.2f}). Add more golden samples for reliable calibration."
                )

        version_id = None
        overall_after = None

        # Always register the base prompt so `prompt list` has at least one entry
        try:
            base_ver = registry.save(
                agent_name=cfg["registry_key"],
                template=cfg["base_prompt"],
                notes="Base judge prompt",
            )
            if registry.get_active(cfg["registry_key"]) is None:
                registry.set_active(cfg["registry_key"], base_ver.version_id)
                version_id = base_ver.version_id
        except Exception as e:
            log.warning(f"Judge base prompt save failed: {e}")

        pareto_frontier: list[ParetoCandidate] = []
        trials_run = 0
        budget_exhausted = False

        if needs_cal:
            if search_mode == "pareto":
                if verbose:
                    print(
                        f"  Score below {_CALIBRATION_THRESHOLD} — "
                        f"running Pareto frontier search (max_trials={max_trials}, "
                        f"candidates_per_round={candidates_per_round})..."
                    )
                try:
                    pareto_frontier, trials_run, budget_exhausted = await _run_pareto_search(
                        judge_cls=cfg["judge_cls"],
                        base_prompt=cfg["base_prompt"],
                        registry_key=cfg["registry_key"],
                        samples=scoring_samples,
                        criteria=cfg["criteria"],
                        model=effective_model,
                        registry=registry,
                        max_trials=max_trials,
                        candidates_per_round=candidates_per_round,
                        verbose=verbose,
                    )
                    # Save all Pareto-optimal candidates; activate the aggregate-best
                    if pareto_frontier:
                        best = max(pareto_frontier, key=lambda c: c.aggregate_score)
                        for cand in pareto_frontier:
                            try:
                                is_best = cand is best
                                ver = registry.save(
                                    agent_name=cfg["registry_key"],
                                    template=cand.template,
                                    notes=(
                                        f"Pareto search round={cand.round_generated} "
                                        f"agg={cand.aggregate_score:.2f} "
                                        f"{'[activated]' if is_best else ''}"
                                    ),
                                    criterion_scores=cand.criterion_scores,
                                    optimized_for_model=effective_model,
                                )
                                cand.version_id = ver.version_id
                                if is_best:
                                    registry.set_active(cfg["registry_key"], ver.version_id)
                                    version_id = ver.version_id
                                    overall_after = best.aggregate_score
                            except Exception as e:
                                log.warning(f"Pareto candidate save failed: {e}")

                        if overall_after is not None:
                            record_kpi(f"judge.calibration.score_after.{atype}", overall_after)
                            record_kpi(
                                f"judge.calibration.delta.{atype}",
                                overall_after - overall_before,
                            )
                            record_kpi(f"judge.calibration.pareto_frontier_size.{atype}", len(pareto_frontier))
                            record_kpi(f"judge.calibration.trials_run.{atype}", trials_run)
                            if verbose:
                                print(
                                    f"  Pareto search complete: {len(pareto_frontier)} non-dominated candidate(s)  "
                                    f"best_agg={overall_after:.2f}/10 "
                                    f"(Δ={overall_after - overall_before:+.2f})"
                                )
                                registry.record_eval(
                                    cfg["registry_key"], version_id,
                                    score=overall_after, latency_ms=0.0,
                                )
                except Exception as e:
                    log.warning(f"Pareto search failed: {e}")
                    if verbose:
                        print(f"  Warning: Pareto search failed: {e} — falling back to threshold mode")
                    search_mode = "threshold"  # fall through to threshold below

            if search_mode == "threshold" and needs_cal:
                if verbose:
                    print(f"  Score below {_CALIBRATION_THRESHOLD} — injecting few-shot calibration examples...")

                few_shot = _build_few_shot_block(samples, _FEW_SHOT_COUNT)
                calibrated_prompt = cfg["base_prompt"] + few_shot

                try:
                    cal_ver = registry.save(
                        agent_name=cfg["registry_key"],
                        template=calibrated_prompt,
                        notes=f"Calibrated: few-shot from golden dataset "
                              f"(mean before={overall_before:.2f})",
                        optimized_for_model=effective_model,
                    )
                    registry.set_active(cfg["registry_key"], cal_ver.version_id)
                    version_id = cal_ver.version_id

                    # Verify: re-score all non-promoted samples with calibrated judge
                    cal_judge = cfg["judge_cls"](model=effective_model)
                    cal_judge._eval_adapter = AsyncLLMAdapter(
                        prompt_template=calibrated_prompt,
                        model=effective_model,
                        temperature=0.0,
                    )
                    scores_after = await _score_reference_outputs(cal_judge, scoring_samples, verbose=verbose)
                    if scores_after:
                        overall_after = statistics.mean(
                            getattr(s, "overall", 5.0) for s in scores_after
                        )
                        record_kpi(f"judge.calibration.score_after.{atype}", overall_after)
                        record_kpi(
                            f"judge.calibration.delta.{atype}",
                            overall_after - overall_before,
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

        power_note = (
            f"⚠ Underpowered: n={len(scores_before)} < required {required_n} "
            f"(δ={_SAMPLE_DELTA}, {int(_SAMPLE_POWER*100)}% power, σ≈{sigma_obs:.2f}). "
            f"Add more golden samples."
            if not sufficient else ""
        )
        base_note = "" if needs_cal else "Judge well-calibrated — no changes needed."
        notes = " | ".join(n for n in [base_note, power_note] if n)

        report = CalibrationReport(
            agent_type=atype,
            n_samples=len(scoring_samples),
            mean_score_before=overall_before,
            mean_score_after=overall_after,
            criteria_means=means_before,
            needs_calibration=needs_cal,
            prompt_version_id=version_id,
            notes=notes,
            required_n=required_n,
            sufficient_samples=sufficient,
            search_mode=search_mode,
            trials_run=trials_run,
            budget_exhausted=budget_exhausted,
            pareto_frontier=pareto_frontier,
        )
        if verbose:
            report.print_summary()
        reports.append(report)

    return reports
