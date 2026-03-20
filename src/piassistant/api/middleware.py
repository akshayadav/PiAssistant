from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str = ""):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        # No key configured → allow everything (backward compatible)
        if not self.api_key:
            return await call_next(request)

        # Safe (read-only) methods → always allowed
        if request.method in SAFE_METHODS:
            return await call_next(request)

        # Static files and dashboard → skip auth
        path = request.url.path
        if path == "/" or path.startswith("/static"):
            return await call_next(request)

        # Check Authorization header
        auth = request.headers.get("authorization", "")
        if auth == f"Bearer {self.api_key}":
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"},
        )
