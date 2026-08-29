from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings


def _configure_real(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "AUTH_MODE", "real")
    monkeypatch.setattr(settings, "AUTH_ADAPTER", "jwt")
    monkeypatch.setattr(settings, "AUTH_JWT_ISSUER", "https://identity.bank.test")
    monkeypatch.setattr(settings, "AUTH_JWT_AUDIENCE", "model-market-assistant")
    monkeypatch.setattr(settings, "AUTH_JWT_PUBLIC_KEY", "test-only-signing-secret-at-least-32-bytes")
    monkeypatch.setattr(settings, "AUTH_JWKS_URL", "")
    monkeypatch.setattr(settings, "AUTH_JWT_ALGORITHMS", ["HS256"])
    return settings


def _token(*, expired=False):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "real-user-1",
            "name": "Real User",
            "role": "business_user",
            "institution_id": "BR_REAL_001",
            "legal_entity_id": "JSRCU",
            "permitted_domains": ["customer_marketing"],
            "can_recommend": True,
            "can_view_results": True,
            "iat": now - timedelta(minutes=2) if expired else now,
            "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=5),
            "iss": "https://identity.bank.test",
            "aud": "model-market-assistant",
        },
        "test-only-signing-secret-at-least-32-bytes",
        algorithm="HS256",
    )


def test_demo_health_explicitly_disclaims_production_auth(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["auth_mode"] == "demo"
    assert response.json()["production_auth_ready"] is False


def test_real_mode_ignores_demo_header_and_requires_bearer(client, monkeypatch):
    _configure_real(monkeypatch)
    response = client.get("/api/v1/feedback/stats", headers={"X-User-Id": "admin"})
    assert response.status_code == 401


def test_real_mode_unconfigured_identity_source_returns_503(client, monkeypatch):
    settings = _configure_real(monkeypatch)
    monkeypatch.setattr(settings, "AUTH_JWT_PUBLIC_KEY", "")
    response = client.get(
        "/api/v1/feedback/stats",
        headers={"Authorization": "Bearer opaque-token"},
    )
    assert response.status_code == 503
    health = client.get("/api/v1/health").json()
    assert health["status"] == "degraded"
    assert health["production_auth_ready"] is False


def test_valid_real_jwt_succeeds_and_expired_token_is_rejected(client, monkeypatch):
    _configure_real(monkeypatch)
    valid = client.get(
        "/api/v1/feedback/stats",
        headers={"Authorization": f"Bearer {_token()}"},
    )
    expired = client.get(
        "/api/v1/feedback/stats",
        headers={"Authorization": f"Bearer {_token(expired=True)}"},
    )
    health = client.get("/api/v1/health").json()
    assert valid.status_code == 200
    assert expired.status_code == 401
    assert health["status"] == "healthy"
    assert health["production_auth_ready"] is True
