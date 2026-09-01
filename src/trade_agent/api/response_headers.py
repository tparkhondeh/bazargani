from __future__ import annotations

from starlette.responses import Response

UI_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'none'; "
    "img-src 'self'; "
    "object-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'"
)


def apply_response_security_headers(response: Response, *, path: str) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith("/api/v1"):
        _append_vary(response, "X-API-Key")
    if path == "/ui" or path.startswith("/ui/"):
        response.headers["Content-Security-Policy"] = UI_CONTENT_SECURITY_POLICY
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"


def _append_vary(response: Response, name: str) -> None:
    existing = [item.strip() for item in response.headers.get("Vary", "").split(",")]
    values = [item for item in existing if item]
    if name.casefold() not in {item.casefold() for item in values}:
        values.append(name)
    response.headers["Vary"] = ", ".join(values)
