"""Proxy behaviour. Login is stubbed out here; test_auth covers that the proxy
requires it."""

import gzip
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.sessions import require_user
from app.config import Settings
from app.main import create_app
from tests.conftest import SERVICES, FakeEmail, FakeServices


@pytest.fixture
def services():
    return FakeServices()


@pytest.fixture
def client(services):
    settings = Settings(
        services=SERVICES,
        upstream_timeout_seconds=5,
        # Never connected to: login is stubbed and nothing else queries it.
        database_url="postgresql+psycopg://unused@localhost:1/unused",
    )
    app = create_app(
        settings, transport=httpx.MockTransport(services.handle), email_sender=FakeEmail()
    )
    app.dependency_overrides[require_user] = lambda: None
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "component": "gateway"}


@pytest.mark.parametrize(
    "service, expected",
    [
        ("c01", "http://c01.test/api/x"),
        ("c02", "http://c02.test/api/x"),
        ("c03", "http://c03.test/base/api/x"),
        ("c04", "http://c04.test/api/x"),
    ],
)
def test_routes_to_each_service(client, services, service, expected):
    client.get(f"/api/{service}/api/x")
    assert str(services.requests[0].url) == expected


def test_forwards_method_query_and_body(client, services):
    r = client.post("/api/c02/estimate?debug=1&x=a%20b", json={"floors": 2})

    forwarded = services.requests[0]
    assert forwarded.method == "POST"
    assert str(forwarded.url) == "http://c02.test/estimate?debug=1&x=a%20b"
    assert forwarded.headers["content-type"] == "application/json"
    assert json.loads(services.bodies[0]) == {"floors": 2}
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_returns_upstream_status_and_headers(client, services):
    services.reply = lambda request: httpx.Response(
        422, json={"detail": "bad"}, headers={"x-custom": "1"}
    )
    r = client.patch("/api/c04/project/1/location", json={})
    assert r.status_code == 422
    assert r.json() == {"detail": "bad"}
    assert r.headers["x-custom"] == "1"


def test_bare_service_path_maps_to_service_root(client, services):
    client.get("/api/c03")
    assert str(services.requests[0].url) == "http://c03.test/base/"


def test_keeps_percent_encoding_in_path(client, services):
    client.get("/api/c01/api/floorplans/status/a%2Fb")
    assert services.requests[0].url.raw_path == b"/api/floorplans/status/a%2Fb"


def test_get_without_body_sends_no_body_headers(client, services):
    # Flask (C04) mishandles a chunked body on a GET, so none must be sent.
    client.get("/api/c04/health")
    headers = services.requests[0].headers
    assert "transfer-encoding" not in headers
    assert "content-length" not in headers


def test_multipart_upload_passes_through(client, services):
    client.post(
        "/api/c01/api/process-cadastral",
        files={"file": ("plan.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    forwarded = services.requests[0]
    body = services.bodies[0]
    assert forwarded.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert forwarded.headers["content-length"] == str(len(body))
    assert b'filename="plan.pdf"' in body
    assert b"%PDF-1.4 fake" in body


def test_compressed_response_is_passed_through_raw(client, services):
    payload = b'{"total_lkr": 12500000}'
    services.reply = lambda request: httpx.Response(
        200,
        content=gzip.compress(payload),
        headers={"content-encoding": "gzip", "content-type": "application/json"},
    )
    r = client.get("/api/c02/estimate")
    assert r.headers["content-encoding"] == "gzip"
    assert r.content == payload


def test_redirects_are_returned_not_followed(client, services):
    services.reply = lambda request: httpx.Response(307, headers={"location": "/elsewhere"})
    r = client.get("/api/c02/old", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/elsewhere"
    assert len(services.requests) == 1


def test_strips_cookie_and_rewrites_forwarding_headers(client, services):
    client.get(
        "/api/c02/health",
        headers={
            "cookie": "__Host-session=secret",
            "x-forwarded-for": "6.6.6.6",
            "forwarded": "for=6.6.6.6",
        },
    )
    headers = services.requests[0].headers
    assert "cookie" not in headers
    assert "forwarded" not in headers
    assert headers["x-forwarded-for"] == "testclient"
    assert headers["host"] == "c02.test"


def test_drops_set_cookie_and_cors_headers_from_services(client, services):
    services.reply = lambda request: httpx.Response(
        200,
        json={},
        headers=[
            ("set-cookie", "a=b"),
            ("access-control-allow-origin", "http://localhost:5173"),
            ("access-control-allow-credentials", "true"),
            ("x-keep", "yes"),
        ],
    )
    r = client.get("/api/c02/health")
    assert "set-cookie" not in r.headers
    assert not any(name.startswith("access-control-") for name in r.headers)
    assert r.headers["x-keep"] == "yes"


def test_unknown_service_is_404(client, services):
    r = client.get("/api/c09/anything")
    assert r.status_code == 404
    assert r.json() == {"detail": "Unknown service 'c09'."}
    assert services.requests == []


def test_rejects_dot_segments(client, services):
    r = client.get("/api/c02/%2e%2e/secret")
    assert r.status_code == 400
    assert services.requests == []


def test_service_down_is_502(client, services):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    services.reply = refuse
    r = client.get("/api/c03/api/timeline/predict")
    assert r.status_code == 502
    assert r.json() == {"detail": "C03 is unavailable. Is the service running?"}


def test_service_timeout_is_504(client, services):
    def stall(request):
        raise httpx.ReadTimeout("too slow", request=request)

    services.reply = stall
    r = client.post("/api/c01/api/select-plan", json={})
    assert r.status_code == 504
    assert r.json() == {"detail": "C01 did not respond in time."}
