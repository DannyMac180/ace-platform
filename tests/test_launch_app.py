from __future__ import annotations

from ace_platform.symphony.launch_app import infer_extension, sanitize_label


def test_sanitize_label_normalizes_root_and_path_segments() -> None:
    assert sanitize_label("/") == "root"
    assert sanitize_label("/settings/team members") == "settings-team-members"


def test_infer_extension_prefers_known_text_types() -> None:
    assert infer_extension("text/html; charset=utf-8") == ".html"
    assert infer_extension("application/json") == ".json"
    assert infer_extension(None) == ".txt"
