from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "packages" / "ace-core" / "src"


def _load_package_modules(*module_names: str):
    for name in list(sys.modules):
        if name == "ace_core" or name.startswith("ace_core."):
            sys.modules.pop(name)

    sys.path.insert(0, str(PACKAGE_SRC))
    try:
        return [importlib.import_module(name) for name in module_names]
    finally:
        sys.path = [entry for entry in sys.path if entry != str(PACKAGE_SRC)]


def test_package_generator_returns_considered_and_used_ids(monkeypatch) -> None:
    (generator_module,) = _load_package_modules("ace_core.ace.core.generator")

    response = json.dumps(
        {
            "reasoning": "demo",
            "considered_bullet_ids": ["str-00001", "mis-00002"],
            "used_bullet_ids": ["str-00001"],
            "final_answer": "42",
        }
    )

    monkeypatch.setattr(
        generator_module,
        "timed_llm_call",
        lambda *args, **kwargs: (response, {"role": "generator", "call_id": "test"}),
    )

    generator = generator_module.Generator(api_client=None, api_provider="openai", model="test")
    _, considered_ids, used_ids, _ = generator.generate(
        question="What is 6 * 7?",
        playbook="## STRATEGIES & INSIGHTS",
        use_json_mode=True,
    )

    assert considered_ids == ["str-00001", "mis-00002"]
    assert used_ids == ["str-00001"]


def test_package_generator_defaults_missing_used_ids_to_considered_ids(monkeypatch) -> None:
    (generator_module,) = _load_package_modules("ace_core.ace.core.generator")

    response = json.dumps(
        {
            "reasoning": "demo",
            "considered_bullet_ids": ["str-00001", "mis-00002"],
            "final_answer": "42",
        }
    )

    monkeypatch.setattr(
        generator_module,
        "timed_llm_call",
        lambda *args, **kwargs: (response, {"role": "generator", "call_id": "test"}),
    )

    generator = generator_module.Generator(api_client=None, api_provider="openai", model="test")
    _, considered_ids, used_ids, _ = generator.generate(
        question="What is 6 * 7?",
        playbook="## STRATEGIES & INSIGHTS",
        use_json_mode=True,
    )

    assert considered_ids == ["str-00001", "mis-00002"]
    assert used_ids == ["str-00001", "mis-00002"]


def test_package_bulletpoint_analyzer_excludes_archived_bullets() -> None:
    (analyzer_module,) = _load_package_modules("ace_core.ace.core.bulletpoint_analyzer")

    analyzer = analyzer_module.BulletpointAnalyzer(client=None, model="test")
    _lines, bullets, _mapping = analyzer._parse_playbook(
        """## STRATEGIES & INSIGHTS
[str-00001] helpful=1 harmful=0 neutral=0 created_step=1 last_considered_step=4 last_used_step=4 times_considered_not_used=0 status=active :: Use a table for multi-step reasoning.
[mis-00002] helpful=0 harmful=2 neutral=1 created_step=1 last_considered_step=4 last_used_step=0 times_considered_not_used=2 status=archived :: Guess before checking constraints.
[str-00003] helpful=0 harmful=0 neutral=0 created_step=2 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=candidate :: Verify each constraint before choosing a path.
"""
    )

    assert [bullet["id"] for bullet in bullets] == ["str-00001", "str-00003"]


def test_package_playbook_utils_supports_lifecycle_operations_and_metadata() -> None:
    (playbook_utils,) = _load_package_modules("ace_core.playbook_utils")

    playbook = """## STRATEGIES & INSIGHTS
[str-00001] helpful=1 harmful=0 neutral=0 created_step=1 last_considered_step=1 last_used_step=1 times_considered_not_used=0 status=active :: Use a table for multi-step reasoning.
[str-00002] helpful=1 harmful=0 neutral=0 created_step=1 last_considered_step=1 last_used_step=1 times_considered_not_used=0 status=active :: Verify each constraint before choosing a path.
[mis-00003] helpful=0 harmful=2 neutral=1 created_step=1 last_considered_step=4 last_used_step=0 times_considered_not_used=2 status=active :: Guess before checking constraints.

## OTHERS"""

    updated_playbook, next_id = playbook_utils.apply_curator_operations(
        playbook,
        [
            {
                "type": "UPDATE",
                "bullet_id": "str-00001",
                "content": "Use a table, then verify each intermediate step against the constraints.",
            }
        ],
        next_id=4,
        current_step=6,
    )
    assert (
        "Use a table, then verify each intermediate step against the constraints."
        in updated_playbook
    )
    assert "status=candidate" in updated_playbook

    updated_playbook, next_id = playbook_utils.apply_curator_operations(
        updated_playbook,
        [
            {
                "type": "MERGE",
                "source_ids": ["str-00001", "str-00002"],
                "section": "strategies_and_insights",
                "content": "Use a structured table and verify each intermediate step against the constraints.",
            },
            {
                "type": "ARCHIVE",
                "bullet_id": "mis-00003",
                "reason": "repeatedly harmful and stale",
            },
        ],
        next_id=next_id,
        current_step=6,
    )

    assert next_id == 5
    assert "status=archived :: Guess before checking constraints." in updated_playbook
    assert "[str-00004]" in updated_playbook
    assert (
        "status=candidate :: Use a structured table and verify each intermediate step against the constraints."
        in updated_playbook
    )

    reflected_playbook = playbook_utils.update_bullet_counts(
        updated_playbook,
        [
            {"id": "str-00004", "tag": "helpful"},
            {"id": "mis-00003", "tag": "neutral"},
        ],
        considered_bullet_ids=["str-00004", "mis-00003"],
        used_bullet_ids=["str-00004"],
        current_step=7,
    )

    assert "helpful=3" in reflected_playbook
    assert "last_used_step=7" in reflected_playbook
    assert "last_considered_step=7" in reflected_playbook
    assert (
        "times_considered_not_used=3 status=archived :: Guess before checking constraints."
        in reflected_playbook
    )

    active_playbook = playbook_utils.render_active_playbook(reflected_playbook)
    assert "[mis-00003]" not in active_playbook
    assert "[str-00004]" in active_playbook


def test_package_ace_scores_considered_bullets_and_prunes_after_curator(tmp_path: Path) -> None:
    ace_module, playbook_utils = _load_package_modules(
        "ace_core.ace.ace", "ace_core.playbook_utils"
    )

    class FakeGenerator:
        def __init__(self) -> None:
            self.playbooks: list[str] = []

        def generate(self, *, playbook: str, **kwargs):
            self.playbooks.append(playbook)
            return (
                json.dumps({"final_answer": "42"}),
                ["str-00001", "mis-00002"],
                ["str-00001"],
                {"role": "generator", "call_id": kwargs.get("call_id", "test")},
            )

    class FakeReflector:
        def __init__(self) -> None:
            self.bullets_considered = ""

        def reflect(self, *, bullets_considered: str, **kwargs):
            self.bullets_considered = bullets_considered
            return (
                "reflection",
                [
                    {"id": "str-00001", "tag": "helpful"},
                    {"id": "mis-00002", "tag": "neutral"},
                ],
                {"role": "reflector"},
            )

    class FakeCurator:
        def curate(self, *, current_playbook: str, next_global_id: int, **kwargs):
            return current_playbook, next_global_id, [], {"role": "curator"}

    class FakeProcessor:
        @staticmethod
        def answer_is_correct(final_answer: str, target: str) -> bool:
            return final_answer == target

    ace = ace_module.ACE.__new__(ace_module.ACE)
    ace.generator = FakeGenerator()
    ace.reflector = FakeReflector()
    ace.curator = FakeCurator()
    ace.use_bulletpoint_analyzer = False
    ace.bulletpoint_analyzer = None
    ace.bulletpoint_analyzer_threshold = 0.9
    ace.next_global_id = 4
    ace.playbook = """## STRATEGIES & INSIGHTS
[str-00001] helpful=0 harmful=0 neutral=0 created_step=1 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=active :: Use a table for multi-step reasoning.
[mis-00002] helpful=0 harmful=0 neutral=0 created_step=1 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=active :: Avoid guessing before checking constraints.
[ctx-00003] helpful=0 harmful=0 neutral=0 created_step=1 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=candidate :: Mention every context clue even when unused.

## OTHERS"""

    pre_answer, post_answer, _ = ace_module.ACE._train_single_sample(
        ace,
        task_dict={"question": "What is 6 * 7?", "context": "math", "target": "42"},
        data_processor=FakeProcessor(),
        step_id="train_e_1_s_6",
        epoch=1,
        step=6,
        usage_log_path=str(tmp_path / "usage.jsonl"),
        log_dir=str(tmp_path),
        config_params={
            "max_num_rounds": 1,
            "curator_frequency": 1,
            "token_budget": 2048,
            "use_json_mode": True,
            "no_ground_truth": False,
        },
        total_samples=10,
    )

    assert pre_answer == "42"
    assert post_answer == "42"
    assert "[str-00001]" in ace.reflector.bullets_considered
    assert "[mis-00002]" in ace.reflector.bullets_considered
    assert "helpful=1" in ace.playbook
    assert "neutral=1" in ace.playbook
    assert "last_used_step=6" in ace.playbook
    assert "last_considered_step=6" in ace.playbook
    assert "times_considered_not_used=1" in ace.playbook
    assert "status=archived :: Mention every context clue even when unused." in ace.playbook
    assert "[ctx-00003]" not in ace.generator.playbooks[-1]
    assert ace.generator.playbooks[0] == playbook_utils.render_active_playbook(
        """## STRATEGIES & INSIGHTS
[str-00001] helpful=0 harmful=0 neutral=0 created_step=1 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=active :: Use a table for multi-step reasoning.
[mis-00002] helpful=0 harmful=0 neutral=0 created_step=1 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=active :: Avoid guessing before checking constraints.
[ctx-00003] helpful=0 harmful=0 neutral=0 created_step=1 last_considered_step=0 last_used_step=0 times_considered_not_used=0 status=candidate :: Mention every context clue even when unused.

## OTHERS"""
    )
