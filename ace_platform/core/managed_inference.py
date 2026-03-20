"""Managed inference gateway for cloud workspaces."""

from __future__ import annotations

import os
from dataclasses import replace
from uuid import UUID

import anthropic
import openai
from sqlalchemy.ext.asyncio import AsyncSession

from ace_core.contracts import InferenceGateway, ModelRequest, ModelResponse, TokenUsage
from ace_core.local import (
    AnthropicInferenceProvider,
    DirectInferenceGateway,
    OpenAIInferenceProvider,
)
from ace_platform.config import Settings, get_settings
from ace_platform.core.llm_proxy import calculate_cost
from ace_platform.core.logging import get_logger, sanitize_for_logging
from ace_platform.core.metrics import record_token_usage
from ace_platform.db.models import UsageRecord

logger = get_logger(__name__)

MANAGED_INFERENCE_OPERATION = "managed_inference"
_MANAGED_METADATA_BLOCKLIST = frozenset({"api_key", "base_url", "organization"})


class ManagedInferenceError(Exception):
    """Base error type for managed inference failures."""


class ManagedInferenceConfigurationError(ManagedInferenceError):
    """Raised when the server is missing required managed inference config."""


class ManagedInferenceRequestError(ManagedInferenceError):
    """Raised when the managed inference request cannot be fulfilled."""


class ManagedInferenceProviderError(ManagedInferenceError):
    """Raised when the upstream provider returns a stable request error."""

    def __init__(self, detail: str, *, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def resolve_provider_name(request: ModelRequest, default_provider: str = "openai") -> str:
    """Resolve the target provider from request metadata or model naming."""
    provider = request.metadata.get("provider")
    if isinstance(provider, str) and provider.strip():
        return provider.strip().lower()

    model = request.model.strip().lower()
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return default_provider


def _managed_request(request: ModelRequest) -> ModelRequest:
    """Drop client-controlled provider credentials before upstream invocation."""
    metadata = {
        key: value
        for key, value in request.metadata.items()
        if key not in _MANAGED_METADATA_BLOCKLIST
    }
    provider = metadata.get("provider")
    if isinstance(provider, str):
        metadata["provider"] = provider.strip().lower()
    return replace(request, metadata=metadata)


class ManagedOpenAIAdapter:
    """OpenAI adapter using platform-managed credentials."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openai_api_key
        self._provider = OpenAIInferenceProvider(api_key=self._api_key)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self._api_key:
            raise ManagedInferenceConfigurationError(
                "Managed OpenAI inference is not configured on this server."
            )
        return await self._provider.complete(_managed_request(request))


class ManagedAnthropicAdapter:
    """Anthropic adapter using platform-managed credentials."""

    def __init__(self) -> None:
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._provider = AnthropicInferenceProvider(api_key=self._api_key or None)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self._api_key:
            raise ManagedInferenceConfigurationError(
                "Managed Anthropic inference is not configured on this server."
            )
        return await self._provider.complete(_managed_request(request))


class ManagedInferenceGateway(InferenceGateway):
    """Execute managed inference with server-side routing, metering, and logs."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        user_id: UUID,
        workspace_id: str,
        settings: Settings | None = None,
        gateway: InferenceGateway | None = None,
    ) -> None:
        active_settings = settings or get_settings()
        self._db = db
        self._user_id = user_id
        self._workspace_id = workspace_id
        self._gateway = gateway or DirectInferenceGateway(
            providers={
                "openai": ManagedOpenAIAdapter(active_settings),
                "anthropic": ManagedAnthropicAdapter(),
            }
        )

    async def call(self, request: ModelRequest) -> ModelResponse:
        """Route one request through managed providers and persist usage."""
        provider_name = resolve_provider_name(request)
        log_payload = sanitize_for_logging(
            {
                "workspace_id": self._workspace_id,
                "user_id": str(self._user_id),
                "provider": provider_name,
                "model": request.model,
                "message_count": len(request.messages),
                "messages": [
                    {
                        "role": message.role,
                        "name": message.name,
                        "content": message.content,
                    }
                    for message in request.messages
                ],
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "metadata": request.metadata,
            }
        )
        logger.info(
            "Managed inference request received",
            extra={"managed_inference_request": log_payload},
        )

        try:
            response = await self._gateway.call(_managed_request(request))
        except ManagedInferenceConfigurationError:
            logger.warning(
                "Managed inference provider is unavailable",
                extra={"managed_inference_request": log_payload},
            )
            raise
        except ValueError as exc:
            logger.warning(
                "Managed inference request rejected",
                extra={
                    "managed_inference_request": log_payload,
                    "managed_inference_error": str(exc),
                },
            )
            raise ManagedInferenceRequestError(str(exc)) from exc
        except (
            openai.AuthenticationError,
            anthropic.AuthenticationError,
        ) as exc:
            logger.warning(
                "Managed inference provider credentials are invalid",
                extra={
                    "managed_inference_request": log_payload,
                    "managed_inference_error": type(exc).__name__,
                },
            )
            raise ManagedInferenceConfigurationError(
                f"Managed {provider_name} inference is not configured correctly on this server."
            ) from exc
        except (openai.BadRequestError, anthropic.BadRequestError) as exc:
            logger.warning(
                "Managed inference provider rejected the request",
                extra={
                    "managed_inference_request": log_payload,
                    "managed_inference_error": type(exc).__name__,
                },
            )
            raise ManagedInferenceProviderError(
                "Managed inference request was rejected by the provider.",
                status_code=400,
            ) from exc
        except (openai.RateLimitError, anthropic.RateLimitError) as exc:
            logger.warning(
                "Managed inference provider is rate limited",
                extra={
                    "managed_inference_request": log_payload,
                    "managed_inference_error": type(exc).__name__,
                },
            )
            raise ManagedInferenceProviderError(
                "Managed inference provider is rate limited. Please retry shortly.",
                status_code=429,
            ) from exc
        except (openai.APIConnectionError, anthropic.APIConnectionError) as exc:
            logger.warning(
                "Managed inference provider is temporarily unavailable",
                extra={
                    "managed_inference_request": log_payload,
                    "managed_inference_error": type(exc).__name__,
                },
            )
            raise ManagedInferenceProviderError(
                "Managed inference provider is temporarily unavailable. Please retry.",
                status_code=503,
            ) from exc
        except (openai.APIError, anthropic.APIStatusError, anthropic.APIError) as exc:
            logger.warning(
                "Managed inference provider request failed",
                extra={
                    "managed_inference_request": log_payload,
                    "managed_inference_error": type(exc).__name__,
                },
            )
            raise ManagedInferenceProviderError(
                "Managed inference provider request failed.",
                status_code=502,
            ) from exc
        except Exception:
            logger.exception(
                "Managed inference upstream call failed",
                extra={"managed_inference_request": log_payload},
            )
            raise

        await self._record_usage(response, provider_name)
        logger.info(
            "Managed inference request completed",
            extra={
                "managed_inference_response": {
                    "workspace_id": self._workspace_id,
                    "user_id": str(self._user_id),
                    "provider": response.metadata.get("provider", provider_name),
                    "model": response.model,
                    "finish_reason": response.finish_reason,
                    "request_id": response.metadata.get("request_id"),
                    "usage": _usage_dict(response.usage),
                    "output_chars": len(response.output_text),
                }
            },
        )
        return response

    async def _record_usage(self, response: ModelResponse, provider_name: str) -> None:
        """Persist managed inference usage for billing and analytics."""
        usage = response.usage or TokenUsage()
        prompt_tokens = usage.input_tokens or 0
        completion_tokens = usage.output_tokens or 0
        total_tokens = usage.total_tokens or (prompt_tokens + completion_tokens)

        self._db.add(
            UsageRecord(
                user_id=self._user_id,
                playbook_id=None,
                evolution_job_id=None,
                operation=MANAGED_INFERENCE_OPERATION,
                model=response.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=calculate_cost(response.model, prompt_tokens, completion_tokens),
                request_id=str(response.metadata.get("request_id"))
                if response.metadata.get("request_id")
                else None,
                extra_data={
                    "managed": True,
                    "workspace_id": self._workspace_id,
                    "provider": response.metadata.get("provider", provider_name),
                    "finish_reason": response.finish_reason,
                },
            )
        )
        await self._db.flush()
        record_token_usage(
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=float(calculate_cost(response.model, prompt_tokens, completion_tokens)),
        )


def _usage_dict(usage: TokenUsage | None) -> dict[str, int | None] | None:
    """Serialize token usage for structured logging."""
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


__all__ = [
    "MANAGED_INFERENCE_OPERATION",
    "ManagedInferenceConfigurationError",
    "ManagedInferenceError",
    "ManagedInferenceGateway",
    "ManagedInferenceProviderError",
    "ManagedInferenceRequestError",
    "ManagedAnthropicAdapter",
    "ManagedOpenAIAdapter",
    "resolve_provider_name",
]
