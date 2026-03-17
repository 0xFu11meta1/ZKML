"""Webhook security tests: signature correctness and tamper detection."""

from __future__ import annotations

import hashlib
import hmac
import json


def _verify_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def test_webhook_signature_matches_payload():
    from registry.tasks.webhook_delivery import _sign_payload

    payload = {
        "event": "proof.completed",
        "timestamp": "2026-03-17T00:00:00Z",
        "webhook_id": 7,
        "data": {"job_id": 42, "status": "completed"},
    }
    body = json.dumps(payload, sort_keys=True).encode()
    secret = "whsec_test_secret"

    signature = _sign_payload(body, secret)

    assert isinstance(signature, str)
    assert len(signature) == 64
    assert _verify_signature(body, secret, signature) is True


def test_webhook_tampered_payload_fails_signature_verification():
    from registry.tasks.webhook_delivery import _sign_payload

    original_payload = {
        "event": "proof.completed",
        "data": {"job_id": 42, "status": "completed"},
    }
    tampered_payload = {
        "event": "proof.completed",
        "data": {"job_id": 42, "status": "failed"},
    }
    secret = "whsec_test_secret"

    original_body = json.dumps(original_payload, sort_keys=True).encode()
    tampered_body = json.dumps(tampered_payload, sort_keys=True).encode()
    signature = _sign_payload(original_body, secret)

    assert _verify_signature(original_body, secret, signature) is True
    assert _verify_signature(tampered_body, secret, signature) is False


def test_webhook_wrong_secret_fails_signature_verification():
    from registry.tasks.webhook_delivery import _sign_payload

    payload = {
        "event": "proof.failed",
        "data": {"job_id": 84, "error": "timeout"},
    }
    body = json.dumps(payload, sort_keys=True).encode()

    correct_secret = "whsec_correct"
    wrong_secret = "whsec_wrong"

    signature = _sign_payload(body, correct_secret)

    assert _verify_signature(body, correct_secret, signature) is True
    assert _verify_signature(body, wrong_secret, signature) is False
