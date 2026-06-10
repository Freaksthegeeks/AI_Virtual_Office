import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from groq import Groq
from langfuse_connection import get_langfuse_client

load_dotenv()

DEFAULT_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_COST_PER_TOKEN_USD = 0.0001

MODEL_COST_PER_TOKEN_USD = {
    "mistralai/Mistral-7B-Instruct-v0.3": 0.000003,
    "llama-3.1-8b-instant": 0.00002,
    "llama-3.1-70b-versatile": 0.00006,
    "llama-3.2-90b-vision-preview": 0.00009,
}


def _get_default_provider() -> str:
    return "groq" if os.getenv("GROQ_API_KEY") else "hf-inference"


def _get_default_api_key() -> Optional[str]:
    return os.getenv("GROQ_API_KEY") or os.getenv("HF_TOKEN")


def _get_default_model(provider: str) -> str:
    return DEFAULT_GROQ_MODEL if provider == "groq" else DEFAULT_MODEL


def _count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text.split())


def _estimate_cost(model: str, total_tokens: int) -> float:
    per_token = float(os.getenv("DEFAULT_COST_PER_TOKEN_USD", str(MODEL_COST_PER_TOKEN_USD.get(model, DEFAULT_COST_PER_TOKEN_USD))))
    return round(total_tokens * per_token, 9)


def _parse_generation_response(response: Any) -> str:
    if response is None:
        return ""

    if hasattr(response, "generated_text"):
        return response.generated_text or ""

    if hasattr(response, "text"):
        return response.text or ""

    if isinstance(response, dict):
        return str(response.get("generated_text") or response.get("text") or response.get("output") or "")

    if isinstance(response, (list, tuple)) and len(response) > 0:
        first = response[0]
        if hasattr(first, "generated_text"):
            return first.generated_text or ""
        if isinstance(first, dict):
            return str(first.get("generated_text") or first.get("text") or first.get("output") or "")

    return str(response)


def _parse_chat_response(response: Any) -> str:
    if response is None:
        return ""

    if hasattr(response, "choices") and len(response.choices) > 0:
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, list):
                return "".join(str(part) for part in content)
            if content is not None:
                return str(content)

    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and len(choices) > 0:
            first = choices[0]
            message = first.get("message") if isinstance(first, dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    return "".join(str(part) for part in content)
                if content is not None:
                    return str(content)
            if isinstance(first, dict):
                text = first.get("text")
                if text:
                    return str(text)

    return _parse_generation_response(response)


@dataclass
class LLMTracker:
    model: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    public_key: Optional[str] = None
    client: InferenceClient = field(init=False)
    langfuse_client: Any = field(init=False)

    def __post_init__(self) -> None:
        self.provider = self.provider or _get_default_provider()
        self.api_key = self.api_key or _get_default_api_key()

        if not self.api_key:
            raise RuntimeError(
                "No valid API key found. Set GROQ_API_KEY for Groq or HF_TOKEN for Hugging Face."
            )

        self.model = self.model or _get_default_model(self.provider)
        self.public_key = self.public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        
        # Debug logging
        api_key_preview = self.api_key[:10] + "..." if self.api_key else "NONE"
        print(f"[DEBUG] LLMTracker initialized: provider={self.provider}, model={self.model}, api_key_preview={api_key_preview}", flush=True)
        
        self.client = self._create_inference_client()
        self.langfuse_client = self._create_langfuse_client()

    def _create_inference_client(self) -> Optional[InferenceClient]:
        if self.provider == "groq":
            return None

        client_kwargs: Dict[str, Any] = {
            "provider": self.provider,
            "api_key": self.api_key,
        }

        custom_base_url = os.getenv("HF_API_BASE_URL")
        if custom_base_url:
            client_kwargs["base_url"] = custom_base_url.rstrip("/")

        return InferenceClient(**client_kwargs)

    def _create_disabled_langfuse_client(self) -> Any:
        class DisabledLangfuseClient:
            def create_event(self, *args: Any, **kwargs: Any) -> Any:
                return None

            def flush(self) -> None:
                return None

        return DisabledLangfuseClient()

    def _create_langfuse_client(self) -> Any:
        try:
            return get_langfuse_client()
        except Exception as exc:
            print(f"[DEBUG] Langfuse client init error: {exc}", flush=True)
            return self._create_disabled_langfuse_client()

    def _call_groq_chat(self, prompt: str, model: str, max_tokens: int, temperature: float) -> str:
        """Call Groq API using the official SDK."""
        try:
            client = Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as exc:
            raise RuntimeError(f"Groq API request failed: {str(exc)}")

    def generate(
        self,
        prompt: str,
        event_name: str = "llm-generation",
        metadata: Optional[Dict[str, Any]] = None,
        max_new_tokens: int = 400,
        temperature: float = 0.2,
    ) -> str:
        start_time = time.perf_counter()
        if self.provider == "groq":
            text = self._call_groq_chat(
                prompt=prompt,
                model=self.model,
                max_tokens=max_new_tokens,
                temperature=temperature,
            )
        else:
            response = self.client.text_generation(
                prompt=prompt,
                model=self.model,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
            )
            text = _parse_generation_response(response)

        elapsed = time.perf_counter() - start_time
        input_tokens = _count_tokens(prompt)
        output_tokens = _count_tokens(text)
        total_tokens = input_tokens + output_tokens
        estimated_cost_usd = _estimate_cost(self.model, total_tokens)

        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "duration_seconds": round(elapsed, 3),
        }

        self.track_generation(
            event_name=event_name,
            prompt=prompt,
            output=text,
            metadata={
                "model": self.model,
                "provider": self.provider,
                **(metadata or {}),
            },
            usage=usage,
        )

        return text

    def track_generation(
        self,
        event_name: str,
        prompt: str,
        output: str,
        metadata: Optional[Dict[str, Any]] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> Any:
        payload = {
            "prompt": prompt,
            "provider": self.provider,
            "model": self.model,
            "usage": usage or {},
        }

        try:
            event = self.langfuse_client.create_event(
                name=event_name,
                input=payload,
                output={"response": output},
                metadata=metadata or {},
                version=self.model,
            )
        except Exception as exc:
            print(f"[DEBUG] Langfuse create_event error: {exc}", flush=True)
            event = None

        # Also append a local usage record for quick inspection and cost summaries
        try:
            record = {
                "timestamp": int(time.time()),
                "event_name": event_name,
                "model": self.model,
                "provider": self.provider,
                "usage": usage or {},
                "metadata": metadata or {},
            }
            log_path = os.path.join(os.getcwd(), "langfuse_usage.jsonl")
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            pass

        return event

    def flush(self) -> None:
        try:
            self.langfuse_client.flush()
        except Exception as exc:
            print(f"[DEBUG] Langfuse flush error: {exc}", flush=True)
