"""Tests for managed inference gateway behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ace_core.contracts import InferenceMessage, ModelRequest, ModelResponse, TokenUsage
from ace_platform.core.managed_inference import (
    ManagedInferenceConfigurationError,
    ManagedInferenceGateway,
    ManagedInferenceProviderError,
)


@pytest.mark.asyncio
async def test_managed_inference_gateway_records_usage_and_strips_client_credentials():
    db = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
    response = ModelResponse(
        model="gpt-4o-mini",
        output_text="ok",
        finish_reason="stop",
        usage=TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        metadata={"provider": "openai", "request_id": "req_456"},
    )
    downstream_gateway = AsyncMock()
    downstream_gateway.call = AsyncMock(return_value=response)

    gateway = ManagedInferenceGateway(
        db=db,
        user_id=uuid4(),
        workspace_id="workspace-1",
        gateway=downstream_gateway,
    )
    request = ModelRequest(
        model="gpt-4o-mini",
        messages=[InferenceMessage(role="user", content="hello")],
        metadata={
            "provider": "openai",
            "api_key": "client-secret",
            "base_url": "https://example.invalid",
        },
    )

    await gateway.call(request)

    forwarded_request = downstream_gateway.call.await_args.args[0]
    assert forwarded_request.metadata == {"provider": "openai"}
    db.add.assert_called_once()
    record = db.add.call_args.args[0]
    assert record.operation == "managed_inference"
    assert record.prompt_tokens == 10
    assert record.completion_tokens == 4
    assert record.total_tokens == 14
    assert record.extra_data["workspace_id"] == "workspace-1"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_managed_inference_gateway_reports_missing_provider_config():
    db = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
    downstream_gateway = SimpleNamespace(
        call=AsyncMock(
            side_effect=ManagedInferenceConfigurationError(
                "Managed OpenAI inference is not configured on this server."
            )
        )
    )
    gateway = ManagedInferenceGateway(
        db=db,
        user_id=uuid4(),
        workspace_id="workspace-1",
        gateway=downstream_gateway,
    )

    with pytest.raises(ManagedInferenceConfigurationError):
        await gateway.call(
            ModelRequest(
                model="gpt-4o-mini",
                messages=[InferenceMessage(role="user", content="hello")],
            )
        )


@pytest.mark.asyncio
async def test_managed_inference_gateway_surfaces_provider_status_code():
    db = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
    downstream_gateway = SimpleNamespace(
        call=AsyncMock(
            side_effect=ManagedInferenceProviderError(
                "Managed inference provider is rate limited. Please retry shortly.",
                status_code=429,
            )
        )
    )
    gateway = ManagedInferenceGateway(
        db=db,
        user_id=uuid4(),
        workspace_id="workspace-1",
        gateway=downstream_gateway,
    )

    with pytest.raises(ManagedInferenceProviderError) as exc_info:
        await gateway.call(
            ModelRequest(
                model="gpt-4o-mini",
                messages=[InferenceMessage(role="user", content="hello")],
            )
        )

    assert exc_info.value.status_code == 429
