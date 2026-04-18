# praktor.ai Governance

PHI/PII detection, audit logging, and RBAC for AI agents in regulated industries.

---

## Quick start (< 3 min)

```python
from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition
from praktor.governance import block_pii, RegexEntities

class Input(BaseModel):
    agent_type: str = "my_agent"
    text: str
    session_id: str = ""

defn = AgentDefinition(
    name="my_agent",
    prompt_template="Answer: {text}",
    input_schema=Input,
)
defn = block_pii(defn, [RegexEntities.US_SSN, RegexEntities.EMAIL_ADDRESS])
```

That's it. Any SSN or email in `text` is blocked before the LLM sees it.

---

## demo-governance (no Ollama required)

```bash
python -m praktor demo-governance
# with full agent path (requires Ollama):
python -m praktor demo-governance --model llama3:8b
```

---

## block_pii() — one-liner governance

```python
from praktor.governance import block_pii, RegexEntities

defn = block_pii(
    definition,                                     # AgentDefinition
    entities=[RegexEntities.US_SSN,
              RegexEntities.EMAIL_ADDRESS],
    action="block",   # or "redact", "flag", "allow"
    sink="stdout",    # or "local_file"
)
```

Returns a **new** `AgentDefinition` with `governance_policy` set. The original is unchanged.

---

## PolicyAction semantics

| Action   | What happens |
|----------|-------------|
| `BLOCK`  | `GovernancePolicyViolation` raised, execution halted. Audit written. |
| `REDACT` | Matched spans replaced with `[REDACTED:ENTITY_TYPE]` before LLM call. Audit written. |
| `FLAG`   | `AuditEntry.flagged = True`, execution continues. Audit written. |
| `ALLOW`  | Pass through. No audit entry for this detector. |

---

## GovernancePolicy — full control

```python
from praktor.governance.policy import (
    GovernancePolicy, DetectorConfig, PolicyAction, AuditSinkType
)

policy = GovernancePolicy(
    pre_execution=[
        DetectorConfig(
            detector_class="praktor.governance.detectors.RegexDetector",
            entities=["US_SSN", "EMAIL_ADDRESS"],
            action=PolicyAction.BLOCK,
        )
    ],
    post_execution=[
        DetectorConfig(
            detector_class="praktor.governance.detectors.RegexDetector",
            entities=["PHONE_NUMBER"],
            action=PolicyAction.REDACT,
        )
    ],
    audit_sinks=[AuditSinkType.LOCAL_FILE],
    dry_run=False,
)
```

`pre_execution` runs on each string field of the agent payload before the LLM call.
`post_execution` runs on the full LLM response before yielding it to the caller.

---

## DetectorConfig — class or string

`detector_class` accepts a class or a dotted import path string:

```python
# Class (ergonomic):
DetectorConfig(detector_class=RegexDetector, entities=["US_SSN"])

# String (audit log compatible):
DetectorConfig(
    detector_class="praktor.governance.detectors.RegexDetector",
    entities=["US_SSN"],
)
```

Both forms store the qualified name in the audit log.

---

## RegexEntities — named constants

```python
from praktor.governance import RegexEntities

RegexEntities.US_SSN          # "US_SSN"
RegexEntities.PHONE_NUMBER    # "PHONE_NUMBER"
RegexEntities.EMAIL_ADDRESS   # "EMAIL_ADDRESS"
RegexEntities.DATE_OF_BIRTH   # "DATE_OF_BIRTH"
RegexEntities.US_PASSPORT     # "US_PASSPORT"
RegexEntities.CREDIT_CARD     # "CREDIT_CARD"
```

Use these instead of magic strings to avoid silent detection failures.

RegexDetector logs a warning when an unknown entity name is passed — the warning
tells you exactly which name was not recognized.

---

## PresidioDetector — full ML-based PHI

Install:
```bash
pip install praktor[presidio]
python -m spacy download en_core_web_lg
```

Use:
```python
DetectorConfig(
    detector_class="praktor.governance.detectors.PresidioDetector",
    entities=["PERSON", "LOCATION", "DATE_TIME", "NRP", "MEDICAL_LICENSE"],
    action=PolicyAction.REDACT,
)
```

PresidioDetector uses the Presidio entity namespace (different from RegexEntities).
The full list is at: https://microsoft.github.io/presidio/supported_entities/

---

## dry_run — test without side effects

```python
policy = GovernancePolicy(
    pre_execution=[DetectorConfig(...)],
    dry_run=True,   # detectors run, findings logged to stderr, nothing raised/written
)
```

With `dry_run=True`:
- Detectors run and findings are logged to stderr
- No `GovernancePolicyViolation` is raised
- No audit sinks are written

Use `dry_run=True` in unit tests and local development.

Expected stderr output:
```
[DRY RUN] pre_execution: field='text', entity=US_SSN, detector=RegexDetector, action=BLOCK
```

---

## Custom detectors

Implement the `PIIDetector` protocol:

```python
from praktor.governance.detectors import PIIDetector, DetectionResult

class MyDetector:
    async def detect(self, text: str, entities: list[str]) -> list[DetectionResult]:
        results = []
        for entity in entities:
            # ... your detection logic ...
            results.append(DetectionResult(
                entity_type=entity,
                start=0, end=5,
                score=0.9,
                text="match",
            ))
        return results
```

Pass as `detector_class=MyDetector` or `detector_class="mypackage.module.MyDetector"`.

---

## AuditSinkType options

| Sink         | Description |
|--------------|-------------|
| `LOCAL_FILE` | Append-only JSONL at `PRAKTOR_AUDIT_LOG` (default: `praktor_audit.jsonl`). Hash-chained, tamper-evident. |
| `STDOUT`     | Print to stdout. Use in development and demos. |
| `KAFKA`      | Phase 2. Raises `NotImplementedError` in Phase 1. |
| `MINIO`      | Phase 2. Raises `NotImplementedError` in Phase 1. |

---

## AuditEntry schema

Each audit entry (one per agent run) is a JSONL record:

```json
{
  "agent_type": "my_agent",
  "session_id": "abc123",
  "model": "qwen2.5",
  "prompt_hash": "sha256:...",
  "response_hash": "sha256:...",
  "governance_actions": [
    {
      "field_name": "text",
      "entity_type": "US_SSN",
      "action": "block",
      "detector_class": "praktor.governance.detectors.RegexDetector",
      "score": 1.0
    }
  ],
  "evaluation_scores": [],
  "flagged": false,
  "timestamp": "2026-04-18T12:00:00Z",
  "chain_hash": "sha256:..."
}
```

`chain_hash` links to the previous entry — breaks if any record is modified.

---

## RBAC (opt-in)

```python
policy = GovernancePolicy(
    rbac_required_roles=["clinician", "admin"],
)
```

Requires `PRAKTOR_RBAC_SECRET` environment variable. If the secret is absent and
roles are non-empty, the Router raises `ConfigurationError` at registration time.
This is the fail-closed design: misconfiguration halts startup, not silently passes.

Issue tokens:
```python
from praktor.governance.rbac import issue_token, verify_token
token = issue_token(caller_id="user@example.com", roles=["clinician"])
```

Pass the token in the payload as `caller_token`.

---

## Governance metrics

When governance fires, the monitoring stack records:

- `governance.violations_total` — count by `action` and `entity_type`
- `governance.detections_total` — count by `entity_type`
- `governance.dry_run_hits_total` — count when `dry_run=True`

Visible in: `python -m praktor monitor summary`, Prometheus, Grafana dashboard.

---

## Limitations (Phase 1)

- Post-execution detection runs on the full buffered response. Streaming is
  interrupted: for agents with `governance_policy`, the response is buffered
  before yielding to the caller.
- Detection does not run on intermediate tool call outputs in ReAct chains.
  Only the final LLM response is checked post-execution.
- RegexDetector covers 6 entity types. For full HIPAA PHI recall, use Presidio.
