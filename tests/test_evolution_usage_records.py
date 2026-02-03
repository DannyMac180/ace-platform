"""Unit tests for evolution usage record writing."""

from unittest.mock import MagicMock
from uuid import uuid4

from ace_platform.db.models import UsageRecord
from ace_platform.workers.evolution_task import _write_usage_records_for_evolution


def test_write_usage_records_creates_records_for_operations():
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    user_id = uuid4()
    playbook_id = uuid4()
    job_id = uuid4()

    token_usage = {
        "model": "gpt-4o-mini",
        "operations": {
            "evolution_reflection": {
                "model": "gpt-4o-mini",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "evolution_curator": {
                "model": "gpt-4o-mini",
                "prompt_tokens": 20,
                "completion_tokens": 7,
                "total_tokens": 27,
            },
        },
    }

    _write_usage_records_for_evolution(
        db=db,
        user_id=user_id,
        playbook_id=playbook_id,
        evolution_job_id=job_id,
        token_usage=token_usage,
    )

    assert db.add.call_count == 2
    added_records = [call.args[0] for call in db.add.call_args_list]
    assert all(isinstance(r, UsageRecord) for r in added_records)
    assert {r.operation for r in added_records} == {"evolution_reflection", "evolution_curator"}


def test_write_usage_records_is_idempotent_when_records_exist():
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid4()
    db.execute.return_value = result

    _write_usage_records_for_evolution(
        db=db,
        user_id=uuid4(),
        playbook_id=uuid4(),
        evolution_job_id=uuid4(),
        token_usage={"operations": {"evolution_reflection": {"model": "gpt-4o-mini"}}},
    )

    db.add.assert_not_called()
