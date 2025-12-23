"""Metered LLM Client for token tracking and usage logging.

This module provides a wrapper around OpenAI clients that automatically
tracks token usage and logs it to the UsageRecord table for billing purposes.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import openai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ace_platform.db.models import UsageRecord

# Pricing per 1M tokens (as of Dec 2024)
# Format: {model_name: (input_price, output_price)}
MODEL_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    # GPT-4o
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-2024-11-20": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-2024-08-06": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-2024-05-13": (Decimal("5.00"), Decimal("15.00")),
    # GPT-4o mini
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o-mini-2024-07-18": (Decimal("0.15"), Decimal("0.60")),
    # GPT-4 Turbo
    "gpt-4-turbo": (Decimal("10.00"), Decimal("30.00")),
    "gpt-4-turbo-2024-04-09": (Decimal("10.00"), Decimal("30.00")),
    "gpt-4-turbo-preview": (Decimal("10.00"), Decimal("30.00")),
    # GPT-4
    "gpt-4": (Decimal("30.00"), Decimal("60.00")),
    "gpt-4-0613": (Decimal("30.00"), Decimal("60.00")),
    # GPT-3.5 Turbo
    "gpt-3.5-turbo": (Decimal("0.50"), Decimal("1.50")),
    "gpt-3.5-turbo-0125": (Decimal("0.50"), Decimal("1.50")),
    # o1 models
    "o1": (Decimal("15.00"), Decimal("60.00")),
    "o1-2024-12-17": (Decimal("15.00"), Decimal("60.00")),
    "o1-preview": (Decimal("15.00"), Decimal("60.00")),
    "o1-mini": (Decimal("3.00"), Decimal("12.00")),
    "o1-mini-2024-09-12": (Decimal("3.00"), Decimal("12.00")),
}

# Default pricing for unknown models (conservative estimate)
DEFAULT_PRICING = (Decimal("10.00"), Decimal("30.00"))


@dataclass
class UsageInfo:
    """Token usage information from an LLM call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    cost_usd: Decimal
    request_id: str | None = None


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Calculate the cost of an LLM call in USD.

    Args:
        model: The model name used.
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.

    Returns:
        Cost in USD as a Decimal.
    """
    input_price, output_price = MODEL_PRICING.get(model, DEFAULT_PRICING)

    # Prices are per 1M tokens, so divide by 1,000,000
    input_cost = (Decimal(prompt_tokens) * input_price) / Decimal("1000000")
    output_cost = (Decimal(completion_tokens) * output_price) / Decimal("1000000")

    return input_cost + output_cost


class MeteredLLMClient:
    """OpenAI client wrapper that meters token usage.

    This client wraps the OpenAI API and automatically logs all token usage
    to the UsageRecord table for billing and analytics purposes.

    Usage:
        client = MeteredLLMClient(
            api_key="sk-...",
            db_session=session,
            user_id=user.id,
        )

        response = client.chat_completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
            operation="evolution_generator",
            playbook_id=playbook.id,
        )
    """

    def __init__(
        self,
        api_key: str,
        db_session: Session,
        user_id: UUID,
        *,
        base_url: str | None = None,
        organization: str | None = None,
    ):
        """Initialize the metered client.

        Args:
            api_key: OpenAI API key.
            db_session: SQLAlchemy session for logging usage.
            user_id: User ID to associate with usage records.
            base_url: Optional custom base URL for the API.
            organization: Optional OpenAI organization ID.
        """
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
        )
        self._db = db_session
        self._user_id = user_id

    def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        operation: str,
        *,
        playbook_id: UUID | None = None,
        evolution_job_id: UUID | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        extra_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[str, UsageInfo]:
        """Make a chat completion request and log usage.

        Args:
            model: Model name to use.
            messages: List of message dicts with 'role' and 'content'.
            operation: Operation name for usage tracking (e.g., 'evolution_generator').
            playbook_id: Optional playbook ID to associate with usage.
            evolution_job_id: Optional evolution job ID to associate with usage.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            extra_data: Optional extra data to store with usage record.
            **kwargs: Additional arguments passed to the OpenAI API.

        Returns:
            Tuple of (response_content, usage_info).

        Raises:
            openai.OpenAIError: On API errors.
        """
        # Prepare API call parameters
        api_params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }

        # Use max_completion_tokens for newer models
        if max_tokens is not None:
            if model.startswith(("gpt-4o", "o1")):
                api_params["max_completion_tokens"] = max_tokens
            else:
                api_params["max_tokens"] = max_tokens

        # Make the API call
        response = self._client.chat.completions.create(**api_params)

        # Extract usage information
        usage = response.usage
        if usage is None:
            raise ValueError("API response missing usage information")

        cost = calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)

        usage_info = UsageInfo(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            model=model,
            cost_usd=cost,
            request_id=response.id,
        )

        # Log usage to database
        self._log_usage(
            usage_info=usage_info,
            operation=operation,
            playbook_id=playbook_id,
            evolution_job_id=evolution_job_id,
            extra_data=extra_data,
        )

        # Extract response content
        content = response.choices[0].message.content or ""

        return content, usage_info

    def _log_usage(
        self,
        usage_info: UsageInfo,
        operation: str,
        playbook_id: UUID | None,
        evolution_job_id: UUID | None,
        extra_data: dict[str, Any] | None,
    ) -> None:
        """Log usage to the database."""
        record = UsageRecord(
            user_id=self._user_id,
            playbook_id=playbook_id,
            evolution_job_id=evolution_job_id,
            operation=operation,
            model=usage_info.model,
            prompt_tokens=usage_info.prompt_tokens,
            completion_tokens=usage_info.completion_tokens,
            total_tokens=usage_info.total_tokens,
            cost_usd=usage_info.cost_usd,
            request_id=usage_info.request_id,
            extra_data=extra_data,
        )
        self._db.add(record)
        self._db.flush()


class AsyncMeteredLLMClient:
    """Async OpenAI client wrapper that meters token usage.

    This is the async version of MeteredLLMClient for use with FastAPI
    and other async contexts.

    Usage:
        client = AsyncMeteredLLMClient(
            api_key="sk-...",
            db_session=async_session,
            user_id=user.id,
        )

        response = await client.chat_completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
            operation="evolution_generator",
            playbook_id=playbook.id,
        )
    """

    def __init__(
        self,
        api_key: str,
        db_session: AsyncSession,
        user_id: UUID,
        *,
        base_url: str | None = None,
        organization: str | None = None,
    ):
        """Initialize the async metered client.

        Args:
            api_key: OpenAI API key.
            db_session: Async SQLAlchemy session for logging usage.
            user_id: User ID to associate with usage records.
            base_url: Optional custom base URL for the API.
            organization: Optional OpenAI organization ID.
        """
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
        )
        self._db = db_session
        self._user_id = user_id

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        operation: str,
        *,
        playbook_id: UUID | None = None,
        evolution_job_id: UUID | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        extra_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[str, UsageInfo]:
        """Make an async chat completion request and log usage.

        Args:
            model: Model name to use.
            messages: List of message dicts with 'role' and 'content'.
            operation: Operation name for usage tracking.
            playbook_id: Optional playbook ID to associate with usage.
            evolution_job_id: Optional evolution job ID to associate with usage.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            extra_data: Optional extra data to store with usage record.
            **kwargs: Additional arguments passed to the OpenAI API.

        Returns:
            Tuple of (response_content, usage_info).

        Raises:
            openai.OpenAIError: On API errors.
        """
        # Prepare API call parameters
        api_params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }

        # Use max_completion_tokens for newer models
        if max_tokens is not None:
            if model.startswith(("gpt-4o", "o1")):
                api_params["max_completion_tokens"] = max_tokens
            else:
                api_params["max_tokens"] = max_tokens

        # Make the API call
        response = await self._client.chat.completions.create(**api_params)

        # Extract usage information
        usage = response.usage
        if usage is None:
            raise ValueError("API response missing usage information")

        cost = calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)

        usage_info = UsageInfo(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            model=model,
            cost_usd=cost,
            request_id=response.id,
        )

        # Log usage to database
        await self._log_usage(
            usage_info=usage_info,
            operation=operation,
            playbook_id=playbook_id,
            evolution_job_id=evolution_job_id,
            extra_data=extra_data,
        )

        # Extract response content
        content = response.choices[0].message.content or ""

        return content, usage_info

    async def _log_usage(
        self,
        usage_info: UsageInfo,
        operation: str,
        playbook_id: UUID | None,
        evolution_job_id: UUID | None,
        extra_data: dict[str, Any] | None,
    ) -> None:
        """Log usage to the database asynchronously."""
        record = UsageRecord(
            user_id=self._user_id,
            playbook_id=playbook_id,
            evolution_job_id=evolution_job_id,
            operation=operation,
            model=usage_info.model,
            prompt_tokens=usage_info.prompt_tokens,
            completion_tokens=usage_info.completion_tokens,
            total_tokens=usage_info.total_tokens,
            cost_usd=usage_info.cost_usd,
            request_id=usage_info.request_id,
            extra_data=extra_data,
        )
        self._db.add(record)
        await self._db.flush()
