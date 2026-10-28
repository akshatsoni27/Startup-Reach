from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import Request

from app.config import get_settings

_attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = Lock()

PROVIDER_ROUTES = {
    "/api/v1/research-runs",
}


def _route_is_limited(request: Request) -> bool:
    if request.method != "POST":
        return False
    path = request.url.path.rstrip("/")
    return (
        path in PROVIDER_ROUTES
        or path.endswith("/research")
        or path.endswith("/contacts/research")
    )


def check_rate_limit(request: Request) -> None:
    if not _route_is_limited(request):
        return
    settings = get_settings()
    now = monotonic()
    window = settings.rate_limit_window_seconds
    limit = settings.rate_limit_max_requests
    client = request.client.host if request.client else "unknown"
    key = (client, request.url.path.rstrip("/"))
    with _lock:
        timestamps = _attempts[key]
        while timestamps and now - timestamps[0] >= window:
            timestamps.popleft()
        if len(timestamps) >= limit:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please retry later.",
                headers={"Retry-After": str(max(1, int(window)))},
            )
        timestamps.append(now)


def reset_rate_limits() -> None:
    with _lock:
        _attempts.clear()
