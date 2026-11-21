# llm-gateway

An OpenAI-compatible proxy that sits in front of a self-hosted open-weight model and adds the things a raw model server lacks: **per-client rate limiting, concurrency control, response caching, streaming passthrough, and Prometheus metrics**.

Point any OpenAI SDK at the gateway instead of the model, and it enforces limits and emits metrics while forwarding to the backend.

```
OpenAI SDK ──► llm-gateway ──► open-weight model (Ollama / vLLM / llama.cpp)
                  │
                  ├─ token-bucket rate limit (per API key / IP)
                  ├─ concurrency cap (backpressure)
                  ├─ response cache (identical non-streaming calls)
                  └─ /metrics (Prometheus)
```

## Why this exists

A model server (Ollama, vLLM) speaks the OpenAI API but has no notion of *who* is calling, *how often*, or *how expensive* that is. On self-hosted inference, GPU time is the scarce resource, so a gateway that caps per-client request rate, bounds concurrency, and caches repeated prompts is what keeps one caller from starving the rest — and what lets you see utilisation at all.

## Run it

1. Serve an open-weight model with an OpenAI-compatible endpoint. Easiest on a Mac is [Ollama](https://ollama.com):
   ```bash
   ollama serve &
   ollama pull qwen2.5:7b          # or llama3.1:8b, mistral, phi3 ...
   ```
   Ollama exposes `http://localhost:11434/v1` — the gateway's default upstream.

2. Start the gateway:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --port 8080
   ```

3. Call it with any OpenAI client:
   ```bash
   curl localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
     "model": "qwen2.5:7b",
     "messages": [{"role": "user", "content": "Say hello in one line."}]
   }'
   ```

   Streaming works too (`"stream": true`), passed straight through as SSE. Watch the limiter and cache at work:
   ```bash
   curl -s localhost:8080/metrics | grep gateway_
   ```

## Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| `UPSTREAM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible backend (Ollama / vLLM / OpenAI) |
| `UPSTREAM_API_KEY` | — | Bearer token for the backend, if it needs one |
| `RATE_PER_SEC` | `2` | Token-bucket refill per client |
| `BURST` | `10` | Token-bucket capacity |
| `MAX_CONCURRENCY` | `8` | Max in-flight upstream requests |
| `CACHE_TTL_SEC` | `60` | Response cache TTL |

## Status

Working skeleton: proxying, rate limiting, concurrency cap, cache, streaming, metrics, `/healthz`.

## Roadmap

- **Redis-backed rate limiting** so limits hold across replicas (the `floodgate` pattern, in Python)
- **Per-API-key tiers** from a real store (free / pro / enterprise quotas)
- **vLLM upstream** on a GPU + a benchmark harness (tokens/sec, TTFT, p99) comparing it to Ollama
- **Deploy on AWS EC2** (GPU or CPU), containerised, behind the gateway
- **Token-budget limiting** (cap tokens, not just requests) and request/response logging
