"""Fail-closed authentication for trusted service-to-service endpoints."""
import hmac
import os

from fastapi import Header, HTTPException


def require_internal_service(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("INTERNAL_API_SECRET", "")
    if not expected:
        raise HTTPException(503, "Internal service authentication is not configured")
    supplied = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(401, "Trusted internal service credential required")
