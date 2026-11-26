"""Tests for the desktop-only localhost session guard."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from app.desktop_security import (
    SESSION_COOKIE_NAME,
    STARTUP_TOKEN_HEADER,
    DesktopSecurityMiddleware,
)


EXPECTED_HOST = "127.0.0.1:8765"
EXPECTED_ORIGIN = f"http://{EXPECTED_HOST}"
SESSION_TOKEN = "test-session-token-that-is-long-enough"


def _client(*, enabled: bool = True) -> TestClient:
    app = FastAPI()
    app.state.desktop_security_enabled = enabled
    app.state.desktop_session_token = SESSION_TOKEN
    app.state.desktop_expected_host = EXPECTED_HOST
    app.state.desktop_expected_origin = EXPECTED_ORIGIN
    app.add_middleware(DesktopSecurityMiddleware)

    @app.get("/")
    def index():
        return HTMLResponse("<html><body>PDF Analyst</body></html>")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/data")
    def data():
        return {"value": "private"}

    @app.post("/api/change")
    def change():
        return {"updated": True}

    return TestClient(app)


def _navigation_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "host": EXPECTED_HOST,
        "sec-fetch-mode": "navigate",
        "sec-fetch-dest": "document",
        "sec-fetch-site": "none",
    }
    headers.update(overrides)
    return headers


def test_api_rejects_requests_without_desktop_session() -> None:
    with _client() as client:
        response = client.get("/api/data", headers={"host": EXPECTED_HOST})

    assert response.status_code == 401
    assert response.json()["detail"] == "Desktop session required"


def test_top_level_navigation_sets_httponly_strict_session_cookie() -> None:
    with _client() as client:
        page = client.get("/", headers=_navigation_headers())
        assert page.status_code == 200

        set_cookie = page.headers.get("set-cookie", "").lower()
        assert SESSION_COOKIE_NAME in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=strict" in set_cookie
        assert "path=/" in set_cookie
        assert "max-age=" not in set_cookie
        assert SESSION_TOKEN not in page.text

        # TestClient retains the cookie as a browser would. Direct PDF links
        # and fetch() requests are protected by the same /api middleware.
        api_response = client.get(
            "/api/data",
            headers={"host": EXPECTED_HOST, "sec-fetch-site": "same-origin"},
        )

    assert api_response.status_code == 200
    assert api_response.json() == {"value": "private"}


def test_cross_site_navigation_cannot_mint_a_session_cookie() -> None:
    with _client() as client:
        response = client.get(
            "/",
            headers=_navigation_headers(
                origin="https://attacker.example",
                **{"sec-fetch-site": "cross-site"},
            ),
        )

    assert response.status_code == 403
    assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_non_navigation_request_cannot_mint_a_session_cookie() -> None:
    with _client() as client:
        response = client.get(
            "/",
            headers={
                "host": EXPECTED_HOST,
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "sec-fetch-site": "same-origin",
            },
        )
        api_response = client.get("/api/data", headers={"host": EXPECTED_HOST})

    assert response.status_code == 200
    assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")
    assert api_response.status_code == 401


def test_wrong_host_is_rejected() -> None:
    with _client() as client:
        response = client.get("/api/data", headers={"host": "attacker.example"})

    assert response.status_code == 421


def test_wrong_origin_is_rejected_even_with_a_valid_cookie() -> None:
    with _client() as client:
        client.get("/", headers=_navigation_headers())
        response = client.post(
            "/api/change",
            headers={
                "host": EXPECTED_HOST,
                "origin": "https://attacker.example",
                "sec-fetch-site": "same-origin",
            },
        )

    assert response.status_code == 403


def test_cross_site_api_request_is_rejected_even_with_a_valid_cookie() -> None:
    with _client() as client:
        client.get("/", headers=_navigation_headers())
        response = client.get(
            "/api/data",
            headers={
                "host": EXPECTED_HOST,
                "origin": EXPECTED_ORIGIN,
                "sec-fetch-site": "cross-site",
            },
        )

    assert response.status_code == 403


def test_startup_token_is_valid_only_for_health_check() -> None:
    with _client() as client:
        health = client.get(
            "/api/health",
            headers={
                "host": EXPECTED_HOST,
                STARTUP_TOKEN_HEADER: SESSION_TOKEN,
            },
        )
        other = client.get(
            "/api/data",
            headers={
                "host": EXPECTED_HOST,
                STARTUP_TOKEN_HEADER: SESSION_TOKEN,
            },
        )

    assert health.status_code == 200
    assert other.status_code == 401


def test_guard_is_inactive_outside_desktop_mode() -> None:
    with _client(enabled=False) as client:
        response = client.get("/api/data")

    assert response.status_code == 200
