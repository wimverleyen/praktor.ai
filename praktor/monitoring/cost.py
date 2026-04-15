"""
Token cost table — maps LLM model identifiers to USD pricing.

Cost per 1 000 tokens, as of 2025-Q2 (update when pricing changes):
    (input_usd_per_1k, output_usd_per_1k)

Local models (Ollama) have zero cost.
Unknown models default to zero cost with a warning.

Usage:
    cost = compute_cost("gpt-4o", input_tokens=1200, output_tokens=400)
    # → float (USD)

    matched = match_model("claude-sonnet-4-6")
    # → "claude-sonnet"
"""

from __future__ import annotations

import re
from settings import create_log

log = create_log()

# ---------------------------------------------------------------------------
# Pricing table — (input_usd_per_1k, output_usd_per_1k)
# Keys are normalized lowercase prefixes.
# Longest match wins.
# ---------------------------------------------------------------------------

COST_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini":             (0.000150, 0.000600),
    "gpt-4o":                  (0.002500, 0.010000),
    "gpt-4-turbo":             (0.010000, 0.030000),
    "gpt-4":                   (0.030000, 0.060000),
    "gpt-3.5-turbo":           (0.000500, 0.001500),
    "o1-mini":                 (0.001100, 0.004400),
    "o1":                      (0.015000, 0.060000),
    "o3-mini":                 (0.001100, 0.004400),
    "o3":                      (0.010000, 0.040000),
    # Anthropic
    "claude-opus-4":           (0.015000, 0.075000),
    "claude-sonnet-4":         (0.003000, 0.015000),
    "claude-haiku-4":          (0.000250, 0.001250),
    "claude-3-5-sonnet":       (0.003000, 0.015000),
    "claude-3-5-haiku":        (0.000800, 0.004000),
    "claude-3-opus":           (0.015000, 0.075000),
    "claude-3-sonnet":         (0.003000, 0.015000),
    "claude-3-haiku":          (0.000250, 0.001250),
    # Mistral
    "mistral-large":           (0.002000, 0.006000),
    "mistral-small":           (0.000200, 0.000600),
    "mistral-medium":          (0.000270, 0.000810),
    "codestral":               (0.000200, 0.000600),
    # Google
    "gemini-1.5-pro":          (0.001250, 0.005000),
    "gemini-1.5-flash":        (0.000075, 0.000300),
    "gemini-2.0-flash":        (0.000100, 0.000400),
    # Meta / Groq hosted
    "llama-3.3-70b":           (0.000590, 0.000790),
    "llama-3.1-70b":           (0.000590, 0.000790),
    "llama-3.1-8b":            (0.000050, 0.000080),
    # Local models (Ollama, LM Studio, vLLM) — zero cost
    "llama3":                  (0.0, 0.0),
    "llama2":                  (0.0, 0.0),
    "mistral":                 (0.0, 0.0),
    "qwen":                    (0.0, 0.0),
    "phi":                     (0.0, 0.0),
    "gemma":                   (0.0, 0.0),
    "deepseek":                (0.0, 0.0),
    "codellama":               (0.0, 0.0),
    "nomic":                   (0.0, 0.0),
    "mxbai":                   (0.0, 0.0),
    "ollama":                  (0.0, 0.0),
}

# Pre-sort by key length descending — longest match wins
_SORTED_KEYS = sorted(COST_TABLE.keys(), key=len, reverse=True)


def match_model(model: str) -> str | None:
    """
    Find the best-matching cost table key for a model string.

    Uses longest-prefix matching after normalizing the input to lowercase.
    Returns None if no match is found.

    Examples:
        match_model("claude-sonnet-4-6") → "claude-sonnet-4"
        match_model("gpt-4o-mini-2024-07-18") → "gpt-4o-mini"
        match_model("llama3:8b") → "llama3"
    """
    normalized = model.lower().strip()
    # Strip version tags like ":8b", "-20241022", "-latest"
    normalized = re.sub(r"(:\w+|-\d{8}|-latest)$", "", normalized)

    for key in _SORTED_KEYS:
        if normalized.startswith(key) or key in normalized:
            return key
    return None


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Compute USD cost for a single LLM call.

    Args:
        model:         Model identifier string (partial matches accepted).
        input_tokens:  Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.

    Returns:
        Cost in USD (float). Returns 0.0 for unknown or local models.
    """
    key = match_model(model)
    if key is None:
        return 0.0

    inp_rate, out_rate = COST_TABLE[key]
    return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000


def format_cost(usd: float) -> str:
    """Human-readable cost string."""
    if usd >= 1.0:
        return f"${usd:.4f}"
    if usd >= 0.0001:
        return f"${usd:.6f}"
    if usd == 0.0:
        return "$0.00 (local)"
    return f"${usd:.8f}"
