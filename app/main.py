import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .cache import TTLCache
from .config import settings
from .ratelimit import TokenBucket

limiter = TokenBucket(settings.rate_per_sec, settings.burst)
cache = TTLCache(settings.cache_max, settings.cache_ttl_sec)
sem = asyncio.Semaphore(settings.max_concurrency)

REQS = Counter("gateway_requests_total", "Requests handled", ["route", "status"])
RATE_LIMITED = Counter("gateway_rate_limited_total", "Requests rejected by the rate limiter")
CACHE_HITS = Counter("gateway_cache_hits_total", "Responses served from cache")
LATENCY = Histogram("gateway_upstream_latency_seconds", "Upstream request latency", ["route"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    headers = {}
    if settings.upstream_api_key:
        headers["Authorization"] = f"Bearer {settings.upstream_api_key}"
    app.state.client = httpx.AsyncClient(
        base_url=settings.upstream_base_url, headers=headers, timeout=120.0
    )
    yield
    await app.state.client.aclose()


app = FastAPI(title="llm-gateway", lifespan=lifespan)


def _client_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return "key:" + auth[7:]
    return "ip:" + (request.client.host if request.client else "unknown")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/models")
async def list_models(request: Request):
    r = await request.app.state.client.get("/models")
    return JSONResponse(status_code=r.status_code, content=r.json())


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    key = _client_key(request)
    if not limiter.allow(key):
        RATE_LIMITED.inc()
        REQS.labels("chat", "429").inc()
        return JSONResponse(
            status_code=429,
            content={"error": {"message": "rate limit exceeded", "type": "rate_limit"}},
            headers={"Retry-After": "1"},
        )

    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        REQS.labels("chat", "400").inc()
        return JSONResponse(status_code=400, content={"error": {"message": "invalid JSON body"}})

    stream = bool(payload.get("stream", False))
    client: httpx.AsyncClient = request.app.state.client

    # Cache only deterministic, non-streaming requests (keyed on the exact body).
    cache_key = None
    if not stream:
        cache_key = hashlib.sha256(body).hexdigest()
        hit = cache.get(cache_key)
        if hit is not None:
            CACHE_HITS.inc()
            REQS.labels("chat", "200-cache").inc()
            return JSONResponse(content=hit)

    async with sem:  # bound concurrency -> backpressure / queueing
        start = time.monotonic()
        if stream:
            req = client.build_request("POST", "/chat/completions", json=payload)
            upstream = await client.send(req, stream=True)

            async def body_stream():
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                finally:
                    LATENCY.labels("chat").observe(time.monotonic() - start)
                    await upstream.aclose()

            REQS.labels("chat", "200-stream").inc()
            return StreamingResponse(body_stream(), media_type="text/event-stream")

        r = await client.post("/chat/completions", json=payload)
        LATENCY.labels("chat").observe(time.monotonic() - start)
        data = r.json()
        if r.status_code == 200 and cache_key is not None:
            cache.set(cache_key, data)
        REQS.labels("chat", str(r.status_code)).inc()
        return JSONResponse(status_code=r.status_code, content=data)
