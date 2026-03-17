"""Tests for registry API middleware — CSRF, rate limit, request size,
security headers, request ID, and tenant context."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from registry.api.middleware.api_key_auth import APIKeyAuthMiddleware
from registry.api.middleware.csrf import CSRFMiddleware
from registry.api.middleware.request_id import RequestIDMiddleware, request_id_ctx
from registry.api.middleware.request_size import RequestSizeLimitMiddleware
from registry.api.middleware.security_headers import SecurityHeadersMiddleware
from registry.api.middleware.tenant import TenantMiddleware, current_org_slug
from registry.models.database import APIKeyRow


# ---------------------------------------------------------------------------
# Shared helper — tiny app with one POST and one GET route
# ---------------------------------------------------------------------------

def _make_app(*middleware_list) -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    async def _get():
        return {"method": "GET"}

    @app.post("/ok")
    async def _post():
        return {"method": "POST"}

    for mw_cls, kwargs in middleware_list:
        app.add_middleware(mw_cls, **kwargs)
    return app


async def _client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


# ── CSRF Middleware ──────────────────────────────────────────

class TestCSRFMiddleware:
    @pytest.fixture()
    async def client(self):
        app = _make_app((CSRFMiddleware, {}))
        async with await _client(app) as c:
            yield c

    async def test_safe_method_no_origin(self, client: AsyncClient):
        """GET requests should pass without Origin header."""
        resp = await client.get("/ok")
        assert resp.status_code == 200

    async def test_post_without_origin_blocked(self, client: AsyncClient):
        """POST without Origin/Referer should be rejected (403)."""
        resp = await client.post("/ok")
        assert resp.status_code == 403
        assert "Origin or Referer header required" in resp.json()["detail"]

    async def test_post_with_matching_origin(self, client: AsyncClient):
        """POST with matching Origin should pass."""
        resp = await client.post("/ok", headers={"origin": "http://testserver"})
        assert resp.status_code == 200

    async def test_post_with_mismatched_origin(self, client: AsyncClient):
        """POST with different Origin host should be rejected."""
        resp = await client.post("/ok", headers={"origin": "http://evil.example.com"})
        assert resp.status_code == 403
        assert "Cross-origin" in resp.json()["detail"]

    async def test_post_with_bearer_token_exempt(self, client: AsyncClient):
        """Bearer auth skips CSRF check entirely."""
        resp = await client.post("/ok", headers={"authorization": "Bearer my_token"})
        assert resp.status_code == 200

    async def test_post_with_bittensor_auth_exempt(self, client: AsyncClient):
        """Bittensor wallet auth (x-hotkey + x-signature) skips CSRF check."""
        resp = await client.post(
            "/ok",
            headers={"x-hotkey": "5FTest", "x-signature": "abcdef"},
        )
        assert resp.status_code == 200

    async def test_post_with_referer_allowed(self, client: AsyncClient):
        """Referer header (instead of Origin) should also be accepted."""
        resp = await client.post("/ok", headers={"referer": "http://testserver/page"})
        assert resp.status_code == 200


# ── Request-ID Middleware ────────────────────────────────────

class TestRequestIDMiddleware:
    @pytest.fixture()
    async def client(self):
        app = _make_app((RequestIDMiddleware, {}))
        async with await _client(app) as c:
            yield c

    async def test_generates_request_id(self, client: AsyncClient):
        """When no X-Request-ID sent, one is generated."""
        resp = await client.get("/ok")
        rid = resp.headers.get("x-request-id")
        assert rid
        assert len(rid) == 32  # uuid4 hex

    async def test_accepts_valid_uuid(self, client: AsyncClient):
        """Valid hex UUID is accepted and echoed back."""
        custom = uuid.uuid4().hex
        resp = await client.get("/ok", headers={"x-request-id": custom})
        assert resp.headers["x-request-id"] == custom

    async def test_rejects_malicious_value(self, client: AsyncClient):
        """Injection payload is rejected; a fresh UUID is generated."""
        evil = "<script>alert(1)</script>"
        resp = await client.get("/ok", headers={"x-request-id": evil})
        rid = resp.headers["x-request-id"]
        assert rid != evil
        assert len(rid) == 32

    async def test_rejects_oversized_value(self, client: AsyncClient):
        """A very long X-Request-ID string is rejected."""
        long_val = "a" * 100
        resp = await client.get("/ok", headers={"x-request-id": long_val})
        assert resp.headers["x-request-id"] != long_val


# ── Request Size Limit Middleware ────────────────────────────

class TestRequestSizeLimitMiddleware:
    @pytest.fixture()
    async def client(self):
        app = _make_app((RequestSizeLimitMiddleware, {"max_content_length": 100}))
        async with await _client(app) as c:
            yield c

    async def test_small_body_allowed(self, client: AsyncClient):
        """Body within limit should pass."""
        resp = await client.post("/ok", content=b"x" * 50)
        assert resp.status_code == 200

    async def test_large_body_rejected(self, client: AsyncClient):
        """Body exceeding limit should return 413."""
        resp = await client.post(
            "/ok",
            content=b"x" * 200,
            headers={"content-length": "200"},
        )
        assert resp.status_code == 413

    async def test_no_content_length_passes(self, client: AsyncClient):
        """Missing Content-Length is allowed (streaming/chunked)."""
        resp = await client.get("/ok")
        assert resp.status_code == 200


# ── Security Headers Middleware ──────────────────────────────

class TestSecurityHeadersMiddleware:
    async def test_headers_applied(self):
        app = _make_app((SecurityHeadersMiddleware, {"enable_hsts": False}))
        async with await _client(app) as c:
            resp = await c.get("/ok")
        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert "Strict-Transport-Security" not in resp.headers

    async def test_hsts_enabled(self):
        app = _make_app((SecurityHeadersMiddleware, {"enable_hsts": True}))
        async with await _client(app) as c:
            resp = await c.get("/ok")
        assert "Strict-Transport-Security" in resp.headers
        assert "31536000" in resp.headers["strict-transport-security"]


# ── Tenant Middleware ────────────────────────────────────────

class TestTenantMiddleware:
    @pytest.fixture()
    async def client(self):
        app = FastAPI()

        @app.get("/tenant")
        async def _get_tenant():
            return {"slug": current_org_slug.get()}

        app.add_middleware(TenantMiddleware)
        async with await _client(app) as c:
            yield c

    async def test_no_header_default_empty(self, client: AsyncClient):
        resp = await client.get("/tenant")
        assert resp.json()["slug"] == ""

    async def test_org_slug_from_header(self, client: AsyncClient):
        resp = await client.get("/tenant", headers={"x-org-slug": "acme-corp"})
        assert resp.json()["slug"] == "acme-corp"


# ── API Key Auth Middleware ────────────────────────────────

def _make_api_key_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def _protected(request: Request):
        return {"hotkey": getattr(request.state, "api_key_hotkey", "")}

    app.add_middleware(APIKeyAuthMiddleware)
    return app


class TestAPIKeyAuthMiddleware:
    @pytest.fixture()
    async def client(self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
        from registry.api.middleware import api_key_auth

        @asynccontextmanager
        async def _test_session():
            yield db_session

        monkeypatch.setattr(api_key_auth, "get_async_session", _test_session)

        app = _make_api_key_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @staticmethod
    async def _create_api_key_row(
        db_session: AsyncSession,
        *,
        raw_key: str,
        hotkey: str,
        requests_today: int,
        daily_limit: int,
        expires_at: datetime | None,
    ) -> None:
        row = APIKeyRow(
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            hotkey=hotkey,
            label="test",
            requests_today=requests_today,
            daily_limit=daily_limit,
            expires_at=expires_at,
        )
        db_session.add(row)
        await db_session.commit()

    async def test_rejects_expired_api_key(self, client: AsyncClient, db_session: AsyncSession):
        raw_key = "mnn_expired_test_key"
        await self._create_api_key_row(
            db_session,
            raw_key=raw_key,
            hotkey="5FExpiredUserXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
            requests_today=0,
            daily_limit=10,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        resp = await client.get(
            "/protected",
            headers={"authorization": f"Bearer {raw_key}"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "API key has expired"

    async def test_rejects_when_daily_limit_exceeded(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        raw_key = "mnn_limited_test_key"
        await self._create_api_key_row(
            db_session,
            raw_key=raw_key,
            hotkey="5FLimitedUserXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
            requests_today=1,
            daily_limit=1,
            expires_at=None,
        )

        resp = await client.get(
            "/protected",
            headers={"authorization": f"Bearer {raw_key}"},
        )

        assert resp.status_code == 429
        assert resp.json()["detail"] == "Daily API key limit exceeded"
