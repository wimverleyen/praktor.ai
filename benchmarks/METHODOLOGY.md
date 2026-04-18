# Benchmark Methodology

## What we measure

Framework overhead relative to a bare Ollama baseline on the same hardware.

**Not** absolute TTFT (time-to-first-token). Absolute TTFT is dominated by model
inference time, which is inflated on CPU-only CI hardware (GitHub Actions
ubuntu-latest). Reporting that number would mislead users running on GPU hardware.

**We measure:** `dispatch_entry_to_first_chunk_ms - bare_ollama_first_chunk_ms`

This delta isolates the cost of praktor's routing, schema validation, memory lookup,
and governance hooks — the parts we control.

## Configurations measured

| Config | Description |
|--------|-------------|
| `baseline` | Bare Ollama HTTP call via `requests`. No praktor framework. |
| `no_governance` | praktor Router → Agent → LLM. GovernancePolicy=None. |
| `regex_detector` | praktor Router → Agent → LLM. Pre-execution RegexDetector (5 entities). |

## Hardware

Benchmarks run on GitHub Actions `ubuntu-latest` (2 vCPU, 7 GB RAM).
Model: `qwen2.5` via Ollama (CPU-only).

When running locally: record your hardware in `benchmarks/results.md` alongside
the CI results.

## Targets

| Config | Overhead target |
|--------|----------------|
| `no_governance` | < 50ms vs. baseline |
| `regex_detector` | < 100ms vs. baseline |

These are framework overhead deltas, not absolute latencies.

## How to run

```bash
# Requires Ollama running locally with qwen2.5 pulled
python benchmarks/run_benchmark.py
```

Results are committed to `benchmarks/results.md` on every merge to main via CI.

## Reproducibility

- Warm up: 3 warmup requests before timing (discard)
- Trials: 10 timed requests per configuration
- Metric: median wall-clock time from dispatch entry to first yielded chunk
- Same prompt for all configs: `"Hello. Reply in one word."`
- Same model: `qwen2.5`
- Same Ollama instance

## CI commit

`.github/workflows/benchmark.yml` runs on every merge to main, calls
`python benchmarks/run_benchmark.py --commit`, which updates `results.md` and
commits via `git commit --allow-empty` if the file changed.
