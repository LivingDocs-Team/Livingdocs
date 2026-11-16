"""LD-403: the whole AI service (not only /internal/*) needs the service credential once
INTERNAL_API_SECRET is configured, as it is in Docker Compose. /health stays open for the
container healthcheck. Without a configured secret the public endpoints behave as before."""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
SECRET = "service-wide-test-secret"
GOOD = {"Authorization": f"Bearer {SECRET}"}

# (method, path, json body) of public endpoints that used to be reachable without any credential.
PUBLIC_ENDPOINTS = [
    ("GET", "/jobs", None),
    ("GET", "/jobs/missing", None),
    ("POST", "/generate", {"scope": "file", "target": "a.py", "files": []}),
    ("GET", "/templates", None),
    ("GET", "/templates/sections", None),
    ("POST", "/templates", {"name": "x", "instructions": "x", "sections": ["Overview"]}),
    ("DELETE", "/templates/missing", None),
    ("GET", "/documents", None),
    ("GET", "/drift/reports", None),
    ("GET", "/drift/severity-rules", None),
    ("POST", "/drift/analyze", {}),
]


@pytest.mark.parametrize("method,path,body", PUBLIC_ENDPOINTS)
def test_public_endpoints_reject_missing_wrong_and_malformed_credentials(monkeypatch, method, path, body):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    for headers in (None, {"Authorization": "Bearer wrong"}, {"Authorization": SECRET},
                    {"Authorization": "Basic dGVzdDp0ZXN0"}, {"Authorization": "Bearer "}):
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401, (method, path, headers, response.text)


@pytest.mark.parametrize("method,path,body", [("GET", "/jobs", None), ("GET", "/templates", None),
                                              ("GET", "/drift/severity-rules", None)])
def test_correct_credential_reaches_the_endpoint(monkeypatch, method, path, body):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    assert client.request(method, path, json=body, headers=GOOD).status_code == 200


def test_health_stays_open_for_the_container_healthcheck(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    assert client.get("/health").status_code == 200


def test_internal_routes_keep_working_with_the_credential_and_fail_without_it(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    assert client.get("/internal/documents/missing").status_code == 401
    assert client.get("/internal/documents/missing", headers=GOOD).status_code == 404


def test_without_a_configured_secret_public_endpoints_stay_open_but_internal_ones_fail_closed(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    assert client.get("/jobs").status_code == 200
    assert client.get("/templates").status_code == 200
    assert client.get("/internal/documents/missing").status_code == 503
