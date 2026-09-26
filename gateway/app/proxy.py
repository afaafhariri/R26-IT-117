"""Reverse proxy from /api/<service>/<path> to the component services.

The browser only ever talks to the gateway. A request to /api/c02/estimate is
forwarded to C02's /estimate with the method, query string, body and headers
intact, and the response is streamed back unchanged, so no service needs to
know the gateway exists. That is what lets C01 stay untouched. Session and
ownership checks will be added here, before a request is forwarded.
"""

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

logger = logging.getLogger("gateway.proxy")

router = APIRouter()

_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

_HOP_BY_HOP = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
    }
)

# Never forwarded upstream. Cookies belong to the gateway (the session cookie
# must not leak to the services), httpx sets Host from the target URL, and the
# forwarding headers are rewritten from what the gateway itself saw.
_DROP_REQUEST = _HOP_BY_HOP | {
    b"host",
    b"cookie",
    b"forwarded",
    b"x-forwarded-for",
    b"x-forwarded-host",
    b"x-forwarded-proto",
}


def _keep_response_header(name: bytes) -> bool:
    # Services don't get to set cookies or CORS policy on the gateway's origin.
    # The gateway is same-origin only, so any Access-Control-* header a
    # service adds would only widen who can read the gateway's responses.
    return (
        name not in _HOP_BY_HOP
        and name != b"set-cookie"
        and not name.startswith(b"access-control-")
    )


def _error(status: int, detail: str) -> JSONResponse:
    # Same {"detail": ...} shape FastAPI uses, which the planner UI already reads.
    return JSONResponse(status_code=status, content={"detail": detail})


def _upstream_headers(request: Request) -> list[tuple[bytes, bytes]]:
    headers = [(k, v) for k, v in request.headers.raw if k not in _DROP_REQUEST]
    # The gateway is the public edge, so any X-Forwarded-* the client sent is
    # untrusted and replaced rather than appended to.
    headers += [
        (b"x-forwarded-for", (request.client.host if request.client else "").encode()),
        (b"x-forwarded-proto", request.url.scheme.encode()),
        (b"x-forwarded-host", request.headers.get("host", "").encode("latin-1")),
    ]
    return headers


@router.api_route("/api/{service}", methods=_METHODS, include_in_schema=False)
@router.api_route("/api/{service}/{path:path}", methods=_METHODS, include_in_schema=False)
async def proxy(request: Request, service: str, path: str = ""):
    base = request.app.state.settings.services.get(service)
    if base is None:
        return _error(404, f"Unknown service '{service}'.")

    if any(segment in (".", "..") for segment in path.split("/")):
        return _error(400, "Path must not contain '.' or '..' segments.")

    # Forward the raw (still percent-encoded) path so an encoded character like
    # %2F reaches the service exactly as the client sent it.
    prefix = f"/api/{service}".encode()
    raw_path = request.scope.get("raw_path") or request.scope["path"].encode()
    if not raw_path.startswith(prefix):
        return _error(400, "Malformed request path.")
    rest = raw_path[len(prefix):] or b"/"
    query = request.scope.get("query_string", b"")

    base_url = httpx.URL(base)
    target = base_url.copy_with(
        raw_path=base_url.raw_path.rstrip(b"/") + rest + (b"?" + query if query else b"")
    )

    has_body = "content-length" in request.headers or "transfer-encoding" in request.headers
    client: httpx.AsyncClient = request.app.state.http
    upstream_request = client.build_request(
        request.method,
        target,
        headers=_upstream_headers(request),
        content=request.stream() if has_body else None,
    )

    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        logger.warning("%s timed out: %s /%s", service, request.method, path)
        return _error(504, f"{service.upper()} did not respond in time.")
    except httpx.RequestError as exc:
        logger.warning(
            "%s unreachable: %s /%s (%s)", service, request.method, path, type(exc).__name__
        )
        return _error(502, f"{service.upper()} is unavailable. Is the service running?")

    response = StreamingResponse(
        # Raw bytes, not decoded ones: the response keeps its original
        # Content-Encoding and Content-Length, and the browser decompresses it.
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        background=BackgroundTask(upstream.aclose),
    )
    response.raw_headers = [
        (name.lower(), value)
        for name, value in upstream.headers.raw
        if _keep_response_header(name.lower())
    ]
    return response
