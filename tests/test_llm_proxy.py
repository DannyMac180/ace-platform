"""Tests for MeteredLLMClient.

These tests verify:
1. Cost calculation for various models
2. Token usage tracking
3. Database logging of usage records
4. Async client functionality
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ace_platform.core.llm_proxy import (
    DEFAULT_PRICING,
    MODEL_PRICING,
    AsyncMeteredLLMClient,
    MeteredLLMClient,
    UsageInfo,
    calculate_cost,
)


class TestCalculateCost:
    """Tests for cost calculation function."""

    def test_calculate_cost_gpt4o(self):
        """Test cost calculation for gpt-4o model."""
        # gpt-4o: $2.50 input, $10.00 output per 1M tokens
        cost = calculate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)

        # Input: 1000 * 2.50 / 1M = 0.0025
        # Output: 500 * 10.00 / 1M = 0.005
        # Total: 0.0075
        expected = Decimal("0.0025") + Decimal("0.005")
        assert cost == expected

    def test_calculate_cost_gpt4o_mini(self):
        """Test cost calculation for gpt-4o-mini model."""
        # gpt-4o-mini: $0.15 input, $0.60 output per 1M tokens
        cost = calculate_cost("gpt-4o-mini", prompt_tokens=10000, completion_tokens=1000)

        # Input: 10000 * 0.15 / 1M = 0.0015
        # Output: 1000 * 0.60 / 1M = 0.0006
        expected = Decimal("0.0015") + Decimal("0.0006")
        assert cost == expected

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model uses default pricing."""
        cost = calculate_cost("unknown-model", prompt_tokens=1000, completion_tokens=1000)

        # Default: $10.00 input, $30.00 output per 1M tokens
        input_price, output_price = DEFAULT_PRICING
        expected = (Decimal("1000") * input_price / Decimal("1000000")) + (
            Decimal("1000") * output_price / Decimal("1000000")
        )
        assert cost == expected

    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        cost = calculate_cost("gpt-4o", prompt_tokens=0, completion_tokens=0)
        assert cost == Decimal("0")

    def test_calculate_cost_large_token_count(self):
        """Test cost calculation with large token counts."""
        # 1 million tokens each
        cost = calculate_cost("gpt-4o", prompt_tokens=1000000, completion_tokens=1000000)

        # Input: 1M * 2.50 / 1M = 2.50
        # Output: 1M * 10.00 / 1M = 10.00
        expected = Decimal("2.50") + Decimal("10.00")
        assert cost == expected


class TestModelPricing:
    """Tests for model pricing configuration."""

    def test_all_gpt4o_variants_have_pricing(self):
        """Test that all gpt-4o variants have pricing defined."""
        gpt4o_models = [
            "gpt-4o",
            "gpt-4o-2024-11-20",
            "gpt-4o-2024-08-06",
            "gpt-4o-2024-05-13",
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
        ]
        for model in gpt4o_models:
            assert model in MODEL_PRICING, f"Missing pricing for {model}"

    def test_o1_models_have_pricing(self):
        """Test that o1 models have pricing defined."""
        o1_models = ["o1", "o1-2024-12-17", "o1-preview", "o1-mini", "o1-mini-2024-09-12"]
        for model in o1_models:
            assert model in MODEL_PRICING, f"Missing pricing for {model}"


class TestUsageInfo:
    """Tests for UsageInfo dataclass."""

    def test_usage_info_creation(self):
        """Test creating UsageInfo instance."""
        info = UsageInfo(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
            cost_usd=Decimal("0.001"),
            request_id="req_123",
        )

        assert info.prompt_tokens == 100
        assert info.completion_tokens == 50
        assert info.total_tokens == 150
        assert info.model == "gpt-4o"
        assert info.cost_usd == Decimal("0.001")
        assert info.request_id == "req_123"

    def test_usage_info_optional_request_id(self):
        """Test UsageInfo with no request_id."""
        info = UsageInfo(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
            cost_usd=Decimal("0.001"),
        )
        assert info.request_id is None


class TestMeteredLLMClient:
    """Tests for synchronous MeteredLLMClient."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = MagicMock()
        return session

    @pytest.fixture
    def user_id(self):
        """Create a test user ID."""
        return uuid4()

    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        response = MagicMock()
        response.id = "chatcmpl-123"
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Hello! How can I help you today?"
        response.usage = MagicMock()
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 15
        response.usage.total_tokens = 25
        return response

    def test_chat_completion_success(self, mock_db_session, user_id, mock_openai_response):
        """Test successful chat completion."""
        with patch("ace_platform.core.llm_proxy.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.return_value = mock_client

            client = MeteredLLMClient(
                api_key="sk-test",
                db_session=mock_db_session,
                user_id=user_id,
            )

            content, usage = client.chat_completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="test_operation",
            )

            assert content == "Hello! How can I help you today?"
            assert usage.prompt_tokens == 10
            assert usage.completion_tokens == 15
            assert usage.total_tokens == 25
            assert usage.model == "gpt-4o"
            assert usage.request_id == "chatcmpl-123"

            # Verify database logging
            mock_db_session.add.assert_called_once()
            mock_db_session.flush.assert_called_once()

    def test_chat_completion_with_playbook_id(self, mock_db_session, user_id, mock_openai_response):
        """Test chat completion with playbook ID."""
        playbook_id = uuid4()

        with patch("ace_platform.core.llm_proxy.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.return_value = mock_client

            client = MeteredLLMClient(
                api_key="sk-test",
                db_session=mock_db_session,
                user_id=user_id,
            )

            client.chat_completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="evolution_generator",
                playbook_id=playbook_id,
            )

            # Verify the usage record was created with playbook_id
            call_args = mock_db_session.add.call_args
            usage_record = call_args[0][0]
            assert usage_record.playbook_id == playbook_id

    def test_chat_completion_uses_max_completion_tokens_for_gpt4o(
        self, mock_db_session, user_id, mock_openai_response
    ):
        """Test that gpt-4o models use max_completion_tokens parameter."""
        with patch("ace_platform.core.llm_proxy.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.return_value = mock_client

            client = MeteredLLMClient(
                api_key="sk-test",
                db_session=mock_db_session,
                user_id=user_id,
            )

            client.chat_completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="test",
                max_tokens=1000,
            )

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "max_completion_tokens" in call_kwargs
            assert call_kwargs["max_completion_tokens"] == 1000
            assert "max_tokens" not in call_kwargs

    def test_chat_completion_uses_max_tokens_for_older_models(
        self, mock_db_session, user_id, mock_openai_response
    ):
        """Test that older models use max_tokens parameter."""
        with patch("ace_platform.core.llm_proxy.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.return_value = mock_client

            client = MeteredLLMClient(
                api_key="sk-test",
                db_session=mock_db_session,
                user_id=user_id,
            )

            client.chat_completion(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="test",
                max_tokens=1000,
            )

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "max_tokens" in call_kwargs
            assert call_kwargs["max_tokens"] == 1000
            assert "max_completion_tokens" not in call_kwargs

    def test_chat_completion_missing_usage_raises_error(self, mock_db_session, user_id):
        """Test that missing usage info raises ValueError."""
        with patch("ace_platform.core.llm_proxy.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            response = MagicMock()
            response.usage = None
            mock_client.chat.completions.create.return_value = response
            mock_openai.return_value = mock_client

            client = MeteredLLMClient(
                api_key="sk-test",
                db_session=mock_db_session,
                user_id=user_id,
            )

            with pytest.raises(ValueError, match="missing usage information"):
                client.chat_completion(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "Hello!"}],
                    operation="test",
                )


@pytest.mark.asyncio
class TestAsyncMeteredLLMClient:
    """Tests for asynchronous AsyncMeteredLLMClient."""

    @pytest.fixture
    def mock_async_db_session(self):
        """Create a mock async database session."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def user_id(self):
        """Create a test user ID."""
        return uuid4()

    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        response = MagicMock()
        response.id = "chatcmpl-456"
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Async response content"
        response.usage = MagicMock()
        response.usage.prompt_tokens = 20
        response.usage.completion_tokens = 30
        response.usage.total_tokens = 50
        return response

    async def test_async_chat_completion_success(
        self, mock_async_db_session, user_id, mock_openai_response
    ):
        """Test successful async chat completion."""
        with patch("ace_platform.core.llm_proxy.openai.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
            mock_openai.return_value = mock_client

            client = AsyncMeteredLLMClient(
                api_key="sk-test",
                db_session=mock_async_db_session,
                user_id=user_id,
            )

            content, usage = await client.chat_completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="async_test",
            )

            assert content == "Async response content"
            assert usage.prompt_tokens == 20
            assert usage.completion_tokens == 30
            assert usage.total_tokens == 50
            assert usage.model == "gpt-4o"

            # Verify database logging
            mock_async_db_session.add.assert_called_once()
            mock_async_db_session.flush.assert_awaited_once()

    async def test_async_chat_completion_with_evolution_job_id(
        self, mock_async_db_session, user_id, mock_openai_response
    ):
        """Test async chat completion with evolution job ID."""
        evolution_job_id = uuid4()

        with patch("ace_platform.core.llm_proxy.openai.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
            mock_openai.return_value = mock_client

            client = AsyncMeteredLLMClient(
                api_key="sk-test",
                db_session=mock_async_db_session,
                user_id=user_id,
            )

            await client.chat_completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="evolution_reflector",
                evolution_job_id=evolution_job_id,
            )

            # Verify the usage record was created with evolution_job_id
            call_args = mock_async_db_session.add.call_args
            usage_record = call_args[0][0]
            assert usage_record.evolution_job_id == evolution_job_id

    async def test_async_chat_completion_with_extra_data(
        self, mock_async_db_session, user_id, mock_openai_response
    ):
        """Test async chat completion with extra data."""
        extra_data = {"step": "generator", "iteration": 1}

        with patch("ace_platform.core.llm_proxy.openai.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
            mock_openai.return_value = mock_client

            client = AsyncMeteredLLMClient(
                api_key="sk-test",
                db_session=mock_async_db_session,
                user_id=user_id,
            )

            await client.chat_completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
                operation="evolution_generator",
                extra_data=extra_data,
            )

            # Verify extra_data was stored
            call_args = mock_async_db_session.add.call_args
            usage_record = call_args[0][0]
            assert usage_record.extra_data == extra_data
