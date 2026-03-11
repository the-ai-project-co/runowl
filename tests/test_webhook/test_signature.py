"""Tests for webhook signature verification."""

import hashlib
import hmac

from webhook.signature import verify_signature


def _make_sig(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerifySignature:
    def test_valid_signature_accepted(self) -> None:
        payload = b'{"action":"opened"}'
        secret = "my-webhook-secret"
        sig = _make_sig(payload, secret)
        assert verify_signature(payload, sig, secret)

    def test_wrong_secret_rejected(self) -> None:
        payload = b'{"action":"opened"}'
        sig = _make_sig(payload, "correct-secret")
        assert not verify_signature(payload, sig, "wrong-secret")

    def test_tampered_payload_rejected(self) -> None:
        payload = b'{"action":"opened"}'
        sig = _make_sig(payload, "secret")
        tampered = b'{"action":"closed"}'
        assert not verify_signature(tampered, sig, "secret")

    def test_missing_sha256_prefix_rejected(self) -> None:
        payload = b'{"action":"opened"}'
        raw_digest = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
        # No "sha256=" prefix
        assert not verify_signature(payload, raw_digest, "secret")

    def test_empty_signature_rejected(self) -> None:
        assert not verify_signature(b"payload", "", "secret")

    def test_binary_payload(self) -> None:
        payload = b"\x00\x01\x02\x03"
        secret = "binary-test"
        sig = _make_sig(payload, secret)
        assert verify_signature(payload, sig, secret)
