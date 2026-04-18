# HIPAA Deployment Guide

praktor.ai architectural alignment with HIPAA requirements for covered entities
deploying AI agents that process Protected Health Information (PHI).

**Disclaimer:** praktor.ai is not HIPAA certified. This guide describes how
praktor's architecture supports compliant deployments. Your organization's
compliance officer and legal team must perform the actual HIPAA risk assessment
and audit. praktor provides the technical controls; your org provides the
administrative and physical safeguards.

---

## Why praktor for HIPAA environments

HIPAA's Security Rule requires three safeguard categories: technical,
administrative, and physical. praktor addresses the technical safeguards:

1. **Data never leaves the perimeter.** Local inference via Ollama means PHI
   is processed on your hardware. No API calls to cloud providers.
2. **PHI detection before LLM execution.** GovernancePolicy pre-execution hooks
   detect and redact PHI in prompts before the LLM processes them.
3. **Tamper-evident audit logging.** Hash-chained JSONL entries with SHA-256
   digests. PHI is never stored in audit logs (hashes only).
4. **Role-based access control.** HMAC-SHA256 tokens with TTL and replay protection.

---

## Deployment Checklist

### 1. Local Inference Setup

```bash
# Install Ollama (no internet required after initial model pull)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (do this on a machine with internet, then transfer)
ollama pull qwen2.5

# For air-gapped environments: export/import the model
ollama export qwen2.5 > qwen2.5.tar
# Transfer qwen2.5.tar to air-gapped machine
ollama import qwen2.5 < qwen2.5.tar
```

### 2. Install praktor (air-gapped)

```bash
# On a machine with internet:
pip download praktor -d ./praktor-wheels/
pip download praktor[presidio] -d ./praktor-wheels/  # optional, for full PHI recall

# Transfer praktor-wheels/ to air-gapped machine
pip install --no-index --find-links=./praktor-wheels/ praktor
```

### 3. Configure Governance Policy

```python
from praktor.governance import (
    GovernancePolicy, DetectorConfig, PolicyAction, AuditSinkType,
)

hipaa_policy = GovernancePolicy(
    pre_execution=[
        DetectorConfig(
            detector_class="governance.detectors.RegexDetector",
            entities=["US_SSN", "PHONE_NUMBER", "EMAIL_ADDRESS", "DATE_OF_BIRTH"],
            action=PolicyAction.REDACT,  # Replace PHI before LLM sees it
            threshold=0.8,
        ),
    ],
    post_execution=[
        DetectorConfig(
            detector_class="governance.detectors.RegexDetector",
            entities=["US_SSN", "PHONE_NUMBER"],
            action=PolicyAction.BLOCK,  # Halt if LLM generates PHI
        ),
    ],
    audit_sinks=[AuditSinkType.LOCAL_FILE],
    rbac_required_roles=["hipaa-reader"],
)
```

For full PHI recall (names, addresses, medical record numbers):

```bash
pip install praktor[presidio]
```

Then use `"governance.detectors.PresidioDetector"` instead of `RegexDetector`.

### 4. RBAC Configuration

```bash
# Generate a shared secret (store securely, rotate quarterly)
export PRAKTOR_RBAC_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

Issue tokens for authorized callers:

```python
from praktor.governance import issue_token

token = issue_token(
    caller_id="ml-pipeline-prod",
    roles=["hipaa-reader"],
    secret=os.environ["PRAKTOR_RBAC_SECRET"],
)
```

Tokens expire after 5 minutes (configurable via `TOKEN_TTL_SECONDS`).

### 5. Audit Log Retention

HIPAA requires audit logs for 6 years. Configure retention:

```bash
# Audit log location
export PRAKTOR_AUDIT_LOG=/var/log/praktor/audit.jsonl

# Max file size before rotation (default: 100MB)
export PRAKTOR_AUDIT_MAX_BYTES=104857600

# Set up external backup (cron example)
# 0 2 * * * rsync -a /var/log/praktor/ /backup/praktor-audit/
```

The audit log never stores PHI. `prompt_hash` and `response_hash` are SHA-256
digests. To verify a specific prompt/response against the audit trail, hash the
text and compare with the stored digest.

### 6. Network Isolation

praktor's core framework makes zero network calls when using:
- `DirectTransport` (in-process)
- `OllamaLLM` (localhost only)
- `LocalFileAuditSink` (local disk)

For additional isolation:
- Run in a dedicated VPC/VLAN with no internet egress
- Block all outbound connections at the firewall
- Use `RabbitMQTransport` for inter-service communication within the perimeter

---

## HIPAA Security Rule Mapping

| HIPAA Requirement | praktor Control | Notes |
|-------------------|----------------|-------|
| Access Control (164.312(a)) | RBAC with HMAC tokens, fail-closed | Token required for protected agents |
| Audit Controls (164.312(b)) | Hash-chained JSONL audit log | 6-year retention via external backup |
| Integrity (164.312(c)) | SHA-256 chain links detect tampering | Previous entry hash in every record |
| Transmission Security (164.312(e)) | Local inference, no cloud API calls | Data never leaves the perimeter |
| Minimum Necessary (164.502(b)) | Audit logs store hashes, not PHI | prompt_hash/response_hash only |

---

## Known Limitations

1. **Mid-chain governance boundary.** PII detection runs on payload fields and
   the final response. Intermediate tool call outputs within LCEL chains are
   not governed. Structure agents so PHI appears in the final response, not
   in tool call intermediates.

2. **In-process RBAC replay protection.** Token replay cache is per-process.
   Multi-worker deployments (e.g., gunicorn with multiple workers) need
   external replay protection (Redis, database). Not yet implemented.

3. **RegexDetector recall.** Pattern-based detection catches formatted PHI
   (SSNs, phone numbers, emails) but misses unformatted names and addresses.
   Use PresidioDetector for full PHI recall in HIPAA-critical deployments.

---

## Security Review Accelerator

When presenting praktor to your security review board:

1. **Architecture diagram:** show that data flows are localhost-only
2. **Audit log sample:** generate a test audit entry, show hash-chaining
3. **PHI detection demo:** run RegexDetector on sample PHI, show REDACT output
4. **RBAC demo:** show token issuance, verification, and expiry
5. **This guide:** maps praktor controls to HIPAA requirements

The goal is to reduce security review time from weeks to days by providing
concrete evidence of technical safeguards.
