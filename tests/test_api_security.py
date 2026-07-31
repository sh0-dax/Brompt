"""Security tests for the FastAPI surface: constant-time key verification,
per-request key reads, and CORS allowlist handling.

These require ``fastapi``/``httpx`` and are skipped where they are absent.
"""

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from brompt.api.routes import _cors_origins, create_app, verify_api_key


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


class TestVerifyApiKey:
    def test_skipped_when_key_unset(self, monkeypatch):
        monkeypatch.delenv("BROMPT_API_KEY", raising=False)
        verify_api_key(_FakeRequest(headers={}))

    def test_accepts_valid_bearer(self, monkeypatch):
        monkeypatch.setenv("BROMPT_API_KEY", "secret-123")
        verify_api_key(_FakeRequest(headers={"Authorization": "Bearer secret-123"}))

    def test_rejects_wrong_key(self, monkeypatch):
        monkeypatch.setenv("BROMPT_API_KEY", "secret-123")
        with pytest.raises(HTTPException) as exc:
            verify_api_key(_FakeRequest(headers={"Authorization": "Bearer wrong"}))
        assert exc.value.status_code == 401

    def test_rejects_missing_header(self, monkeypatch):
        monkeypatch.setenv("BROMPT_API_KEY", "secret-123")
        with pytest.raises(HTTPException) as exc:
            verify_api_key(_FakeRequest(headers={}))
        assert exc.value.status_code == 401

    def test_reads_key_per_request(self, monkeypatch):
        monkeypatch.setenv("BROMPT_API_KEY", "first-key")
        verify_api_key(_FakeRequest(headers={"Authorization": "Bearer first-key"}))

        monkeypatch.setenv("BROMPT_API_KEY", "rotated-key")
        verify_api_key(_FakeRequest(headers={"Authorization": "Bearer rotated-key"}))

        with pytest.raises(HTTPException):
            verify_api_key(_FakeRequest(headers={"Authorization": "Bearer first-key"}))


class TestCors:
    @staticmethod
    def _cors_middleware(app):
        matches = [m for m in app.user_middleware if m.cls is CORSMiddleware]
        assert matches, "CORSMiddleware not registered"
        return matches[0]

    def test_default_origins_have_no_wildcard(self):
        cors = self._cors_middleware(create_app())
        assert "*" not in cors.kwargs["allow_origins"]
        assert cors.kwargs["allow_credentials"] is True

    def test_custom_origins_from_env(self, monkeypatch):
        monkeypatch.setenv(
            "BROMPT_CORS_ORIGINS", "https://a.example.com,https://b.example.com"
        )
        cors = self._cors_middleware(create_app())
        assert cors.kwargs["allow_origins"] == [
            "https://a.example.com", "https://b.example.com",
        ]
        assert cors.kwargs["allow_credentials"] is True

    def test_wildcard_disables_credentials(self, monkeypatch):
        monkeypatch.setenv("BROMPT_CORS_ORIGINS", "*")
        cors = self._cors_middleware(create_app())
        assert cors.kwargs["allow_origins"] == ["*"]
        assert cors.kwargs["allow_credentials"] is False

    def test_cors_origins_parser(self, monkeypatch):
        monkeypatch.setenv("BROMPT_CORS_ORIGINS", "http://x, http://y ,http://z")
        assert _cors_origins() == ["http://x", "http://y", "http://z"]
