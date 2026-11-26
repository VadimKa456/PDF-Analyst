"""Desktop-only request protection for the loopback HTTP server.

The desktop launcher creates a fresh random token for each process. A genuine
top-level navigation to the app receives it as an HttpOnly, SameSite=Strict
session cookie. API calls, including direct PDF links, then use the cookie
without exposing the token to JavaScript or placing it in the URL.
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SESSION_COOKIE_NAME = "pdf_analyst_session"
STARTUP_TOKEN_HEADER = "X-PDF-Analyst-Startup-Token"


class DesktopSecurityMiddleware(BaseHTTPMiddleware):
    """Protect desktop-mode requests while leaving server/dev mode unchanged."""

    async def dispatch(self, request: Request, call_next) -> Response:
        state = request.app.state
        if not getattr(state, "desktop_security_enabled", False):
            return await call_next(request)

        expected_host = str(getattr(state, "desktop_expected_host", "")).lower()
        expected_origin = str(getattr(state, "desktop_expected_origin", ""))
        session_token = str(getattr(state, "desktop_session_token", ""))

        # Reject unexpected Host headers (including DNS-rebinding hostnames).
        supplied_host = request.headers.get("host", "").lower()
        if not expected_host or supplied_host != expected_host:
            return JSONResponse(
                {"detail": "Unexpected Host header"},
                status_code=421,
            )

        # If a browser sends Origin, it must be this exact loopback origin.
        supplied_origin = request.headers.get("origin")
        if supplied_origin is not None and supplied_origin != expected_origin:
            return JSONResponse(
                {"detail": "Cross-origin request rejected"},
                status_code=403,
            )

        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site":
            return JSONResponse(
                {"detail": "Cross-site request rejected"},
                status_code=403,
            )

        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        if is_api:
            supplied_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
            authenticated = bool(session_token) and secrets.compare_digest(
                supplied_cookie, session_token
            )

            # The launcher may perform one internal readiness check before
            # opening the UI. This header is accepted only for GET /api/health.
            startup_check = (
                path == "/api/health"
                and request.method == "GET"
                and bool(session_token)
                and secrets.compare_digest(
                    request.headers.get(STARTUP_TOKEN_HEADER, ""),
                    session_token,
                )
            )
            if not authenticated and not startup_check:
                return JSONResponse(
                    {"detail": "Desktop session required"},
                    status_code=401,
                )

        response = await call_next(request)

        # Mint the cookie only for a top-level app document navigation, never
        # for an API fetch, image, script, stylesheet, or cross-site navigation.
        is_document_navigation = (
            request.method == "GET"
            and not is_api
            and request.headers.get("sec-fetch-mode", "").lower() == "navigate"
            and request.headers.get("sec-fetch-dest", "").lower() == "document"
            and fetch_site in {"", "none", "same-origin"}
        )
        if is_document_navigation and session_token:
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=session_token,
                httponly=True,
                secure=False,  # The desktop listener is HTTP on loopback only.
                samesite="strict",
                path="/",
            )
            response.headers["Cache-Control"] = "no-store"
        return response
