"""HTTP boundary controls shared by every API route."""

import hashlib
import logging
import secrets
import time
import uuid

from fastapi import Request
from prometheus_client import Counter, Gauge, Histogram
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from backend.app.core.config import Settings

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter(
    "incidentlens_http_requests_total",
    "HTTP requests completed by the API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "incidentlens_http_request_duration_seconds",
    "HTTP request processing latency.",
    ("method", "route"),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "incidentlens_http_requests_in_progress",
    "HTTP requests currently being processed.",
    ("method",),
)


class ApiBoundaryMiddleware(BaseHTTPMiddleware):
    """Apply request IDs, write authentication, rate limits, and safe headers."""

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings
        self.redis = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            decode_responses=True,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        if not request_id or len(request_id) > 128:
            request_id = str(uuid.uuid4())
        started = time.perf_counter()

        HTTP_REQUESTS_IN_PROGRESS.labels(request.method).inc()
        try:
            response = await self._reject_at_boundary(request)
            if response is None:
                response = await call_next(request)
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(request.method).dec()

        duration_ms = (time.perf_counter() - started) * 1000
        route = request.scope.get("route")
        route_label = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, route_label, response.status_code).inc()
        HTTP_REQUEST_DURATION.labels(request.method, route_label).observe(duration_ms / 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        logger.info(
            "request_completed method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response

    async def _reject_at_boundary(self, request: Request) -> Response | None:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.settings.max_request_body_bytes:
                    return JSONResponse(
                        status_code=413, content={"detail": "Request body too large"}
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})

        is_api_write = request.url.path.startswith("/api/") and request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }
        supplied_key = request.headers.get("X-API-Key", "")
        if is_api_write and self.settings.api_key:
            if not secrets.compare_digest(supplied_key, self.settings.api_key):
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        if (
            request.method == "POST"
            and request.url.path.startswith("/api/logs")
            and self.settings.ingest_rate_limit_per_minute > 0
        ):
            limited = await self._is_rate_limited(request, supplied_key)
            if limited:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Ingestion rate limit exceeded"},
                    headers={"Retry-After": "60"},
                )
        return None

    async def _is_rate_limited(self, request: Request, supplied_key: str) -> bool:
        client_host = request.client.host if request.client else "unknown"
        identity = supplied_key or client_host
        identity_hash = hashlib.sha256(identity.encode()).hexdigest()[:24]
        window = int(time.time() // 60)
        redis_key = f"incidentlens:ingest-rate:{identity_hash}:{window}"
        try:
            count = await self.redis.incr(redis_key)
            if count == 1:
                await self.redis.expire(redis_key, 65)
            return count > self.settings.ingest_rate_limit_per_minute
        except Exception as exc:
            # Availability wins when the optional limiter backend is down; the
            # request remains authenticated when API_KEY is configured.
            logger.warning("rate_limit_unavailable error=%s", type(exc).__name__)
            return False
