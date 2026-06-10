import os
from typing import Optional

from dotenv import load_dotenv
from langfuse import Langfuse

load_dotenv()

_langfuse_client: Optional[Langfuse] = None


def _configure_environment() -> None:
    """Support the project's legacy variable while using Langfuse's standard host variable."""
    if not os.getenv("LANGFUSE_HOST") and os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]


def get_langfuse_client(verify_auth: bool = False) -> Langfuse:
    global _langfuse_client

    _configure_environment()

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")

    if not public_key or not secret_key:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must both be set."
        )

    if _langfuse_client is None:
        timeout = int(os.getenv("LANGFUSE_TIMEOUT", "50"))
        _langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            timeout=timeout,
        )

    if verify_auth and not _langfuse_client.auth_check():
        raise RuntimeError("Langfuse authentication failed.")

    return _langfuse_client


def initialize_langfuse() -> Langfuse:
    client = get_langfuse_client(verify_auth=True)
    host = os.getenv("LANGFUSE_HOST")
    print(f"[DEBUG] Connected to Langfuse at {host}", flush=True)
    return client


def flush_langfuse() -> None:
    if _langfuse_client is not None:
        _langfuse_client.flush()
