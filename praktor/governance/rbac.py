"""
RBAC (Role-Based Access Control) for praktor agents.

CallerIdentity: represents an authenticated caller with one or more roles.
verify_token(): validates HMAC-SHA256 tokens. Fail-closed — any error = denied.

Token format (URL-safe base64):
    header.payload.signature

    header:  {"alg": "HS256"}
    payload: {"sub": <caller_id>, "roles": [<role>...], "iat": <unix_ts>, "jti": <uuid>}
    signature: HMAC-SHA256(header + "." + payload, secret)

Replay protection: each token has a unique jti (JWT ID). Processed jtis are
tracked in a bounded in-memory set. Tokens older than TOKEN_TTL_SECONDS are
rejected. In multi-process deployments, replay protection is per-process only
(upgrade to Redis for cross-process protection).

RBAC fail-closed rule: if an AgentDefinition has rbac_required_roles and
PRAKTOR_RBAC_SECRET is absent from env, Router raises ConfigurationError.
Never silently open access.

Usage:
    # Issuing tokens (for testing / integration):
    from governance.rbac import issue_token
    token = issue_token(caller_id="ml-team", roles=["hipaa-agent"], secret="mykey")

    # Verifying in Router:
    from governance.rbac import verify_token, CallerIdentity
    identity = verify_token(token, secret="mykey", required_roles=["hipaa-agent"])
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass

TOKEN_TTL_SECONDS = int(300)   # 5 minutes
_MAX_SEEN_JTIS = 10_000        # Bounded replay cache


@dataclass(frozen=True)
class CallerIdentity:
    caller_id: str
    roles: list[str]


class RBACError(Exception):
    """Raised when token verification fails. Always fail-closed."""


class ConfigurationError(Exception):
    """
    Raised at dispatch time when rbac_required_roles is non-empty but
    PRAKTOR_RBAC_SECRET is absent. Never silently open access.
    """


# ---------------------------------------------------------------------------
# Module-level replay cache (in-process only)
# ---------------------------------------------------------------------------
_seen_jtis: deque[str] = deque(maxlen=_MAX_SEEN_JTIS)
_seen_jtis_set: set[str] = set()


def _record_jti(jti: str) -> None:
    if len(_seen_jtis) >= _MAX_SEEN_JTIS:
        oldest = _seen_jtis[0]  # deque will pop it automatically; sync the set
        _seen_jtis_set.discard(oldest)
    _seen_jtis.append(jti)
    _seen_jtis_set.add(jti)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    # Restore padding
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _sign(header_b64: str, payload_b64: str, secret: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return _b64encode(sig)


def issue_token(caller_id: str, roles: list[str], secret: str) -> str:
    """
    Issue a signed HMAC-SHA256 token.

    Used for testing and CLI tooling. In production, tokens are typically
    issued by an external identity provider and verified here.
    """
    header = _b64encode(json.dumps({"alg": "HS256"}).encode())
    payload = _b64encode(json.dumps({
        "sub": caller_id,
        "roles": roles,
        "iat": int(time.time()),
        "jti": uuid.uuid4().hex,
    }).encode())
    sig = _sign(header, payload, secret)
    return f"{header}.{payload}.{sig}"


def verify_token(
    token: str,
    secret: str,
    required_roles: list[str],
) -> CallerIdentity:
    """
    Verify a token and return CallerIdentity if valid.

    Raises RBACError for any failure:
    - Malformed token
    - Invalid signature
    - Expired token (iat + TOKEN_TTL_SECONDS < now)
    - Replayed jti
    - Missing required role

    Always fail-closed: any unexpected exception raises RBACError.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise RBACError("Malformed token: expected 3 parts")

        header_b64, payload_b64, sig = parts

        # Verify signature
        expected_sig = _sign(header_b64, payload_b64, secret)
        if not hmac.compare_digest(expected_sig, sig):
            raise RBACError("Token signature invalid")

        # Decode payload
        try:
            payload = json.loads(_b64decode(payload_b64))
        except Exception:
            raise RBACError("Token payload is not valid JSON")

        # Check expiry
        iat = payload.get("iat", 0)
        if time.time() - iat > TOKEN_TTL_SECONDS:
            raise RBACError(f"Token expired (issued {int(time.time() - iat)}s ago, TTL={TOKEN_TTL_SECONDS}s)")

        # Replay protection
        jti = payload.get("jti", "")
        if not jti:
            raise RBACError("Token missing jti (replay protection required)")
        if jti in _seen_jtis_set:
            raise RBACError(f"Token jti already used (replay detected): {jti}")
        _record_jti(jti)

        # Role check
        caller_roles: list[str] = payload.get("roles", [])
        for role in required_roles:
            if role not in caller_roles:
                raise RBACError(
                    f"Caller '{payload.get('sub')}' missing required role '{role}'. "
                    f"Has: {caller_roles}"
                )

        return CallerIdentity(
            caller_id=str(payload.get("sub", "unknown")),
            roles=caller_roles,
        )

    except RBACError:
        raise
    except Exception as e:
        raise RBACError(f"Token verification failed: {e}") from e
