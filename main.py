
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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
class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming_id = headers.get(b"x-request-id")

        request_id = (
            incoming_id.decode("latin-1")
            if incoming_id
            else str(uuid.uuid4())
        )

        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                response_headers.append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
                message["headers"] = response_headers

            await send(message)

        await self.app(scope, receive, send_with_request_id)


# Middleware 2: Per-client rate limiter
class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope["path"] != "/ping" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        client_id = headers.get(b"x-client-id")

        if client_id:
            client_id = client_id.decode("latin-1")
        else:
            client = scope.get("client")
            client_id = client[0] if client else "unknown"

        now = time.monotonic()
        timestamps = requests_by_client[client_id]

        while timestamps and now - timestamps[0] >= WINDOW:
            timestamps.popleft()

        if len(timestamps) >= LIMIT:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
            await response(scope, receive, send)
            return

        timestamps.append(now)
        await self.app(scope, receive, send)


# Register middleware
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=[
        "X-Request-ID",
        "X-Client-Id",
        "Content-Type",
    ],
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
