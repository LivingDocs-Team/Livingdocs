"""Fail-closed authentication for trusted service-to-service endpoints."""
import hmac
import os

from fastapi import Header, HTTPException, Request


def require_internal_service(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("INTERNAL_API_SECRET", "")
    if not expected:
        raise HTTPException(503, "Internal service authentication is not configured")
    supplied = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(401, "Trusted internal service credential required")


def require_service_credential_when_configured(request: Request,
                                               authorization: str | None = Header(default=None)) -> None:
    """Service-wide guard (LD-403). When INTERNAL_API_SECRET is configured (Docker Compose and every
    real deployment), all endpoints except /health need the trusted service credential, not only
    /internal/*. Without a configured secret (unit tests, a developer running uvicorn alone) the
    public endpoints stay open as before; /internal/* keeps its own fail-closed check.
    """
    expected = os.getenv("INTERNAL_API_SECRET", "")
    if not expected or request.url.path == "/health":
        return
    supplied = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(401, "Trusted internal service credential required")
