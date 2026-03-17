"""Unit tests for semantic playbook matching helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ace_core import playbook_matching as core_playbook_matching
from ace_platform.config import Settings
from ace_platform.core import playbook_matching as platform_playbook_matching
from ace_platform.db.models import Playbook, PlaybookSource, PlaybookStatus


def _test_playbook(
    name: str = "Deploy App", description: str | None = "Deployment checklist"
) -> Playbook:
    return Playbook(
        user_id=uuid4(),
        name=name,
        description=description,
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_build_playbook_match_text_truncates(module) -> None:
    text = module.build_playbook_match_text(
        name="Playbook A",
        description="desc",
        content="x" * 100,
        max_chars=40,
    )
    assert len(text) == 40
    assert text.startswith("Name: Playbook A")


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_generate_local_embedding_is_deterministic(module) -> None:
    a = module.generate_local_embedding("deploy app to production")
    b = module.generate_local_embedding("deploy app to production")
    assert a == b
    assert len(a) > 0


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_cosine_similarity_returns_expected_bounds(module) -> None:
    assert module.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert module.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_keyword_overlap_score(module) -> None:
    score = module.keyword_overlap_score("deploy web app", "playbook for deploy app process")
    assert score > 0.0


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_parse_embedding_rejects_invalid_vectors(module) -> None:
    assert module.parse_embedding(None) is None
    assert module.parse_embedding("not-a-list") is None
    assert module.parse_embedding([1, "x"]) is None


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_score_playbook_match_prefers_semantic_when_models_align(module) -> None:
    score, method = module.score_playbook_match(
        task_description="deploy application to production",
        playbook_text="deployment production application runbook",
        task_embedding=[1.0, 0.0],
        task_embedding_model="test-model",
        playbook_embedding=[1.0, 0.0],
        playbook_embedding_model="test-model",
    )
    assert method == "semantic+keyword"
    assert score >= 0.85


@pytest.mark.parametrize(
    "module",
    [core_playbook_matching, platform_playbook_matching],
)
def test_score_playbook_match_falls_back_to_local_when_models_differ(module) -> None:
    score, method = module.score_playbook_match(
        task_description="debug flaky tests",
        playbook_text="test debugging and flaky test strategy",
        task_embedding=[1.0, 0.0],
        task_embedding_model="model-a",
        playbook_embedding=[1.0, 0.0],
        playbook_embedding_model="model-b",
    )
    assert method == "local-semantic+keyword"
    assert score > 0.0


@pytest.mark.asyncio
async def test_generate_embedding_falls_back_to_local_without_openai_key() -> None:
    settings = Settings(openai_api_key="")
    embedding, model = await core_playbook_matching.generate_embedding(
        "match this task", settings=settings
    )
    assert model == core_playbook_matching.LOCAL_EMBEDDING_MODEL
    assert len(embedding) > 0


@pytest.mark.asyncio
async def test_refresh_playbook_embedding_sets_fields_async() -> None:
    playbook = _test_playbook()
    settings = Settings(openai_api_key="")

    await core_playbook_matching.refresh_playbook_embedding(
        playbook,
        content="deployment instructions and rollback plan",
        settings=settings,
    )

    assert playbook.semantic_embedding is not None
    assert playbook.semantic_embedding_model == core_playbook_matching.LOCAL_EMBEDDING_MODEL
    assert playbook.semantic_embedding_updated_at is not None


def test_refresh_playbook_embedding_sets_fields_sync() -> None:
    playbook = _test_playbook()
    settings = Settings(openai_api_key="")

    core_playbook_matching.refresh_playbook_embedding_sync(
        playbook,
        content="incident response and debugging checklist",
        settings=settings,
    )

    assert playbook.semantic_embedding is not None
    assert playbook.semantic_embedding_model == core_playbook_matching.LOCAL_EMBEDDING_MODEL
    assert playbook.semantic_embedding_updated_at is not None


@pytest.mark.asyncio
async def test_platform_adapter_uses_core_generate_embedding() -> None:
    settings = Settings(openai_api_key="")

    embedding, model = await platform_playbook_matching.generate_embedding(
        "match this task",
        settings=settings,
    )

    assert model == core_playbook_matching.LOCAL_EMBEDDING_MODEL
    assert len(embedding) > 0


@pytest.mark.asyncio
async def test_platform_adapter_refreshes_playbook_fields() -> None:
    playbook = _test_playbook()
    settings = Settings(openai_api_key="")

    await platform_playbook_matching.refresh_playbook_embedding(
        playbook,
        content="deployment instructions and rollback plan",
        settings=settings,
    )

    assert playbook.semantic_embedding is not None
    assert playbook.semantic_embedding_model == core_playbook_matching.LOCAL_EMBEDDING_MODEL
    assert playbook.semantic_embedding_updated_at is not None
