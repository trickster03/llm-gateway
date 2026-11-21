import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Any OpenAI-compatible upstream: Ollama (default), vLLM, llama.cpp server, or OpenAI itself.
    upstream_base_url: str = os.getenv("UPSTREAM_BASE_URL", "http://localhost:11434/v1")
    upstream_api_key: str = os.getenv("UPSTREAM_API_KEY", "")

    # Per-client token-bucket limit (requests/sec + burst). A real deployment would
    # look these up per API key from a store; this is the default tier.
    rate_per_sec: float = float(os.getenv("RATE_PER_SEC", "2"))
    burst: int = int(os.getenv("BURST", "10"))

    # Max in-flight upstream requests (the queue / backpressure knob).
    max_concurrency: int = int(os.getenv("MAX_CONCURRENCY", "8"))

    # Response cache for identical non-streaming requests.
    cache_ttl_sec: float = float(os.getenv("CACHE_TTL_SEC", "60"))
    cache_max: int = int(os.getenv("CACHE_MAX", "512"))


settings = Settings()
