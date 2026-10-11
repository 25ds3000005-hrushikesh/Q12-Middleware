
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

EMAIL = "25ds3000005@ds.study.iitm.ac.in"
ALLOWED_ORIGINS = [
    "https://app-h7eelc.example.com",
    "https://exam.sanand.workers.dev",
]

LIMIT = 11
WINDOW = 10
requests_by_client = defaultdict(deque)


# Middleware 1: Request context
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# Middleware 2: Per-client rate limiter
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/ping" or request.method != "GET":
            return await call_next(request)

        client_id = request.headers.get("X-Client-Id")
        if not client_id:
            client_id = request.client.host if request.client else "unknown"

        now = time.monotonic()
        timestamps = requests_by_client[client_id]

        while timestamps and now - timestamps[0] >= WINDOW:
            timestamps.popleft()

        if len(timestamps) >= LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )

        timestamps.append(now)
        return await call_next(request)


# Add middleware in the correct order
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
)

app.add_middleware(RequestContextMiddleware)



@app.get("/ping")
async def ping(request: Request):
    request_id = request.state.request_id

    return JSONResponse(
        content={
            "email": EMAIL,
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )

