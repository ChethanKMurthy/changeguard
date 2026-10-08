"""Local inference through Ollama (https://ollama.com), the zero-cost default.

Uses Ollama's structured outputs: the JSON schema is passed as ``format`` and
decoding is grammar-constrained, so even small local models emit parseable
JSON. Greedy decoding (temperature 0) with a fixed seed makes repeated runs
reproducible on the same hardware and model build.
"""

from __future__ import annotations

import time

import httpx

from changeguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderHealth,
)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout: float = 90.0,
        num_ctx: int = 16384,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx

    def generate(self, request: GenerationRequest) -> GenerationResult:
        options: dict[str, object] = {
            "temperature": request.temperature,
            "num_ctx": self.num_ctx,
            "num_predict": request.max_output_tokens,
        }
        if request.seed is not None:
            options["seed"] = request.seed
        body = {
            "model": self.model,
            "stream": False,
            "format": request.schema,
            "options": options,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        started = time.perf_counter()
        try:
            response = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "timeout", f"Ollama did not respond within {self.timeout:.0f}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("unavailable", f"cannot reach Ollama at {self.base_url}") from exc
        latency = (time.perf_counter() - started) * 1000
        if response.status_code == 404:
            raise ProviderError(
                "config",
                f"model '{self.model}' is not available in Ollama (run `ollama pull {self.model}`)",
            )
        if response.status_code >= 400:
            raise ProviderError("http", f"Ollama returned HTTP {response.status_code}")
        try:
            data = response.json()
            text = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("bad_response", "unexpected response shape from Ollama") from exc
        return GenerationResult(
            text=text,
            model=str(data.get("model", self.model)),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            latency_ms=latency,
            finish_reason=data.get("done_reason"),
            meta={
                "total_duration_ns": data.get("total_duration"),
                "load_duration_ns": data.get("load_duration"),
            },
        )

    def health(self) -> ProviderHealth:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            response.raise_for_status()
            names = {m.get("name") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return ProviderHealth(
                self.name, self.model, True, False, None, f"Ollama not reachable at {self.base_url}"
            )
        available = self.model in names or f"{self.model}:latest" in names
        detail = (
            None
            if available
            else f"model '{self.model}' not pulled; run `ollama pull {self.model}`"
        )
        return ProviderHealth(self.name, self.model, True, True, available, detail)
