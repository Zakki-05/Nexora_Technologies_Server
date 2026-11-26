import time
from collections import defaultdict
from threading import Lock
from fastapi import Request, HTTPException, status

class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter for endpoint brute-force protection.
    """
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = Lock()

    def get_client_ip(self, request: Request) -> str:
        # Check X-Forwarded-For if behind reverse proxies (Vercel/Render)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request):
        client_ip = self.get_client_ip(request)
        now = time.time()
        cutoff = now - self.window_seconds

        with self.lock:
            # Clean timestamps older than window
            self.requests[client_ip] = [t for t in self.requests[client_ip] if t > cutoff]

            if len(self.requests[client_ip]) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - self.requests[client_ip][0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many login attempts. Please wait {retry_after} seconds before trying again.",
                    headers={"Retry-After": str(max(1, retry_after))}
                )

            self.requests[client_ip].append(now)

# Create singleton instances for auth endpoints
login_rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
refresh_rate_limiter = InMemoryRateLimiter(max_requests=30, window_seconds=60)
