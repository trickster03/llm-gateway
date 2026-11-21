import json
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All gateway config in one typed, validated model.

    Values resolve from (highest precedence first): AWS Secrets Manager when
    SECRET_ID is set, then process env, then a .env file, then the defaults
    below. Secrets are ordinary fields with an empty default — nothing secret is
    ever written in code, and non-secret config (URLs, limits) stays plain env.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Non-secret config
    upstream_base_url: str = "http://localhost:11434/v1"  # Ollama default
    rate_per_sec: float = 2
    burst: int = 10
    max_concurrency: int = 8
    cache_ttl_sec: float = 60
    cache_max: int = 512

    # Secret: empty unless provided by env / .env / Secrets Manager
    upstream_api_key: str = ""


def _aws_secrets() -> dict:
    """Fetch a JSON secret from AWS Secrets Manager, only when SECRET_ID is set.

    Returns {} otherwise, so local / self-hosted runs need no AWS and no boto3.
    The secret is expected to be a JSON object keyed by Settings field names,
    e.g. {"upstream_api_key": "sk-..."}.
    """
    secret_id = os.getenv("SECRET_ID")
    if not secret_id:
        return {}
    import boto3  # lazy: only needed when SECRET_ID is set

    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "ap-south-1"))
    raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


settings = Settings(**_aws_secrets())
