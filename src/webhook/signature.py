"""GitHub webhook signature verification (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """Return True if the GitHub webhook signature matches the secret.

    GitHub sends: X-Hub-Signature-256: sha256=<hex-digest>
    """
    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header[len("sha256=") :]
    return hmac.compare_digest(expected, received)
