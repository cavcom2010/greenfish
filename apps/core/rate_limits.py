"""
Simple cache-backed rate limiting helpers.
"""
import time
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


def client_identity(request):
    """Return a stable identifier for per-user or per-IP limits."""
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        return f"user:{user.pk}"

    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    remote_addr = request.META.get("REMOTE_ADDR", "").strip()
    return f"ip:{forwarded_for or remote_addr or 'unknown'}"


def session_identity(request):
    """Return a stable identifier for the current browser session."""
    session = getattr(request, "session", None)
    if session is None:
        return "session:unknown"

    session_key = session.session_key
    if not session_key:
        try:
            session.save()
        except Exception:
            return "session:unknown"
        session_key = session.session_key

    return f"session:{session_key or 'unknown'}"


def consume_rate_limit(namespace, *, identity, limit, window_seconds):
    """Increment a cache bucket and return retry-after seconds if blocked."""
    now = int(time.time())
    bucket = now // window_seconds
    cache_key = f"ratelimit:{namespace}:{identity}:{bucket}"

    current_count = cache.get(cache_key, 0) + 1
    cache.set(cache_key, current_count, timeout=window_seconds + 5)

    if current_count <= limit:
        return None

    return max(1, window_seconds - (now % window_seconds))


def rate_limited_response(*, retry_after, response_type="json", message=None):
    """Build a standard rate-limit response with Retry-After."""
    if response_type == "plain":
        response = HttpResponse(message or "Too Many Requests", status=429)
    else:
        response = JsonResponse(
            {"error": message or "Too many requests. Try again later."},
            status=429,
        )
    response["Retry-After"] = str(retry_after)
    return response


def rate_limit(namespace, *, limit, window_seconds, methods=("POST",), response_type="json"):
    """Rate-limit a view using the configured Django cache backend."""

    allowed_methods = {method.upper() for method in methods}

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if allowed_methods and request.method.upper() not in allowed_methods:
                return view_func(request, *args, **kwargs)

            try:
                retry_after = consume_rate_limit(
                    namespace,
                    identity=client_identity(request),
                    limit=limit,
                    window_seconds=window_seconds,
                )
            except Exception:
                return view_func(request, *args, **kwargs)

            if retry_after is None:
                return view_func(request, *args, **kwargs)

            return rate_limited_response(retry_after=retry_after, response_type=response_type)

        return wrapped

    return decorator
