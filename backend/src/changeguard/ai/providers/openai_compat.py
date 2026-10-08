"""Any server implementing the OpenAI chat-completions API.

Covers OpenAI itself and the many free or self-hosted servers that speak the
same protocol (LM Studio, vLLM, llama.cpp ``server``, Groq, OpenRouter, ...).
JSON-schema response formatting is requested; servers that ignore it still
return text that the synthesizer validates.
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


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def generate(self, request: GenerationRequest) -> GenerationResult:
        body: dict[str, object] = {
            "model": self.model,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "schema": request.schema,
                    "strict": True,
                },
            },
        }
        if request.seed is not None:
            body["seed"] = request.seed
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "timeout", f"model server did not respond within {self.timeout:.0f}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("unavailable", f"cannot reach {self.base_url}") from exc
        latency = (time.perf_counter() - started) * 1000
        if response.status_code == 429:
            raise ProviderError("rate_limited", "model server rate limit reached")
        if response.status_code in (401, 403):
            raise ProviderError("config", "model server rejected the API key")
        if response.status_code >= 400:
            raise ProviderError("http", f"model server returned HTTP {response.status_code}")
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            if message.get("refusal"):
                raise ProviderError("refused", "the model declined the request")
            text = message["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "bad_response", "unexpected response shape from model server"
            ) from exc
        usage = data.get("usage") or {}
        return GenerationResult(
            text=text or "",
            model=str(data.get("model", self.model)),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency,
            finish_reason=choice.get("finish_reason"),
        )

    def health(self) -> ProviderHealth:
        try:
            response = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=5.0)
        except httpx.HTTPError:
            return ProviderHealth(
                self.name, self.model, True, False, None, f"cannot reach {self.base_url}"
            )
        if response.status_code in (401, 403):
            return ProviderHealth(self.name, self.model, True, True, None, "API key rejected")
        if response.status_code >= 400:
            return ProviderHealth(
                self.name,
                self.model,
                True,
                True,
                None,
                f"/models returned HTTP {response.status_code}",
            )
        try:
            ids = {m.get("id") for m in response.json().get("data", [])}
        except ValueError:
            return ProviderHealth(self.name, self.model, True, True, None, None)
        return ProviderHealth(
            self.name, self.model, True, True, self.model in ids if ids else None, None
        )
