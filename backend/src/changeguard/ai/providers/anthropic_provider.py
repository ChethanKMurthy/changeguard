"""Claude through the official Anthropic Python SDK (optional extra ``changeguard[anthropic]``).

Schema-constrained output uses structured outputs (``output_config.format``
with a JSON schema), which guarantees the first text block is valid JSON.
Sampling parameters are not sent: current Claude models reject
``temperature`` and choose their own sampling, so reproducibility comes from
the response cache and recorded replays instead. Refusals are surfaced as a
provider error; for models that support it, server-side fallback
(``fallbacks: "default"``) re-runs a declined request on Anthropic's
recommended fallback model.
"""

from __future__ import annotations

import time
from typing import Any

from changeguard.ai.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderHealth,
)

# Models that accept the server-side ``fallbacks: "default"`` parameter on the Claude API.
_FALLBACK_PREFIXES = ("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        api_key: str | None = None,
        timeout: float = 90.0,
        effort: str = "medium",
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        if client is not None:
            self._client = client
            return
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra installed
            raise ProviderError(
                "config", "install the Anthropic SDK: pip install 'changeguard[anthropic]'"
            ) from exc
        # api_key=None lets the SDK resolve credentials from the environment.
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    def _uses_fallbacks(self) -> bool:
        return self.model.startswith(_FALLBACK_PREFIXES)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        import anthropic

        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max(request.max_output_tokens, 16000),
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": request.schema},
            },
        }
        started = time.perf_counter()
        try:
            if self._uses_fallbacks():
                response = self._client.beta.messages.create(
                    **params, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self._client.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise ProviderError("timeout", "Claude API request timed out") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate_limited", "Claude API rate limit reached") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderError("config", "Claude API rejected the credentials") from exc
        except anthropic.NotFoundError as exc:
            raise ProviderError("config", f"model '{self.model}' was not found") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError("http", f"Claude API returned HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("unavailable", "cannot reach the Claude API") from exc
        latency = (time.perf_counter() - started) * 1000

        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise ProviderError(
                "refused", f"Claude declined the request (category: {category or 'unspecified'})"
            )
        if response.stop_reason == "max_tokens":
            raise ProviderError("bad_response", "Claude output was truncated at max_tokens")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise ProviderError("bad_response", "Claude response contained no text block")
        usage = response.usage
        return GenerationResult(
            text=text,
            model=str(response.model),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=latency,
            finish_reason=str(response.stop_reason),
            meta={"request_id": getattr(response, "_request_id", None)},
        )

    def health(self) -> ProviderHealth:
        import anthropic

        try:
            # The Models API validates the key and model without generating tokens.
            self._client.models.retrieve(self.model)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            return ProviderHealth(self.name, self.model, True, True, None, "credentials rejected")
        except anthropic.NotFoundError:
            return ProviderHealth(
                self.name, self.model, True, True, False, f"model '{self.model}' not found"
            )
        except anthropic.APIError:
            return ProviderHealth(
                self.name, self.model, True, False, None, "cannot reach the Claude API"
            )
        return ProviderHealth(self.name, self.model, True, True, True, None)
