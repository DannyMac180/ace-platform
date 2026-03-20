"""
==============================================================================
playbook.py
==============================================================================

Utilities for parsing and manipulating ACE playbooks.
"""

import json
import re
from typing import Any

try:
    from .utils import get_section_slug
except ImportError:  # pragma: no cover - legacy standalone ACE entrypoints
    from utils import get_section_slug

DEFAULT_BULLET_STATUS = "active"
ACTIVE_BULLET_STATUSES = {"active", "candidate"}
DEFAULT_SECTION_CAP = 12
DEFAULT_WARMUP_WINDOW = 5
DEFAULT_MIN_OBSERVATIONS = 3

INT_METADATA_FIELDS = (
    "helpful",
    "harmful",
    "neutral",
    "created_step",
    "last_considered_step",
    "last_used_step",
    "times_considered_not_used",
)
METADATA_PATTERN = re.compile(r"([a-z_]+)=([^\s]+)")
ACE_BULLET_PREFIX_PATTERN = re.compile(
    r"^\[[^\]]+\]\s*helpful=\d+\s*harmful=\d+(?:\s+[a-z_]+=[^\s]+)*\s*::\s*"
)


def normalize_section_name(section_raw: str) -> str:
    """Normalize a section header or operation section name."""
    return section_raw.lower().replace(" ", "_").replace("&", "and")


def parse_playbook_line(line: str) -> dict[str, Any] | None:
    """Parse a single playbook bullet line, supporting legacy and extended metadata."""
    line = line.strip()
    if not line or line.startswith("##"):
        return None

    match = re.match(r"\[([^\]]+)\]\s*(.*?)\s*::\s*(.*)", line)
    if not match:
        return None

    bullet_id, metadata_segment, content = match.groups()
    parsed: dict[str, Any] = {
        "id": bullet_id,
        "helpful": 0,
        "harmful": 0,
        "neutral": 0,
        "created_step": 0,
        "last_considered_step": 0,
        "last_used_step": 0,
        "times_considered_not_used": 0,
        "status": DEFAULT_BULLET_STATUS,
        "content": content.strip(),
        "raw_line": line,
    }

    for key, raw_value in METADATA_PATTERN.findall(metadata_segment):
        if key in INT_METADATA_FIELDS:
            try:
                parsed[key] = int(raw_value)
            except ValueError:
                continue
        elif key == "status":
            parsed["status"] = raw_value

    return parsed


def count_playbook_bullets(playbook_text: str) -> int:
    """Count legacy and lifecycle-enriched ACE bullets in a playbook."""
    return sum(1 for line in playbook_text.splitlines() if parse_playbook_line(line))


def strip_ace_bullet_prefix(text: str) -> str:
    """Remove an ACE bullet prefix from content while preserving the body text."""
    return ACE_BULLET_PREFIX_PATTERN.sub("", text, count=1)


def get_next_global_id(playbook_text: str) -> int:
    """Extract the highest global ID and return the next available number."""
    max_id = 0
    lines = playbook_text.strip().split("\n")

    for line in lines:
        parsed = parse_playbook_line(line)
        if not parsed:
            continue

        id_match = re.search(r"-(\d+)$", parsed["id"])
        if id_match:
            max_id = max(max_id, int(id_match.group(1)))

    return max_id + 1


def format_playbook_line(
    bullet_id: str,
    helpful: int,
    harmful: int,
    content: str,
    *,
    neutral: int = 0,
    created_step: int = 0,
    last_considered_step: int = 0,
    last_used_step: int = 0,
    times_considered_not_used: int = 0,
    status: str = DEFAULT_BULLET_STATUS,
) -> str:
    """Format a bullet into the extended playbook line format."""
    return (
        f"[{bullet_id}] "
        f"helpful={helpful} "
        f"harmful={harmful} "
        f"neutral={neutral} "
        f"created_step={created_step} "
        f"last_considered_step={last_considered_step} "
        f"last_used_step={last_used_step} "
        f"times_considered_not_used={times_considered_not_used} "
        f"status={status} :: {content}"
    )


def format_parsed_playbook_line(parsed: dict[str, Any]) -> str:
    """Serialize a parsed bullet back into the canonical playbook line format."""
    return format_playbook_line(
        parsed["id"],
        parsed.get("helpful", 0),
        parsed.get("harmful", 0),
        parsed.get("content", ""),
        neutral=parsed.get("neutral", 0),
        created_step=parsed.get("created_step", 0),
        last_considered_step=parsed.get("last_considered_step", 0),
        last_used_step=parsed.get("last_used_step", 0),
        times_considered_not_used=parsed.get("times_considered_not_used", 0),
        status=parsed.get("status", DEFAULT_BULLET_STATUS),
    )


def _parse_playbook_items(
    playbook_text: str,
) -> tuple[list[dict[str, Any]], dict[str, int], set[str]]:
    """Parse the playbook into ordered items and an ID index."""
    items: list[dict[str, Any]] = []
    bullet_index: dict[str, int] = {}
    sections: set[str] = {"general"}
    current_section = "general"

    for line in playbook_text.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("##"):
            current_section = normalize_section_name(stripped[2:].strip())
            sections.add(current_section)
            items.append({"kind": "header", "section": current_section, "raw": line})
            continue

        parsed = parse_playbook_line(line)
        if parsed:
            parsed["section"] = current_section
            bullet_index[parsed["id"]] = len(items)
            items.append({"kind": "bullet", "section": current_section, "bullet": parsed})
            continue

        items.append({"kind": "text", "section": current_section, "raw": line})

    return items, bullet_index, sections


def _resolve_section_name(section_raw: str, sections: set[str]) -> str:
    """Resolve an operation section to an existing normalized section name."""
    section = normalize_section_name(section_raw or "general")
    if section in sections:
        return section

    available_sections = sorted(section for section in sections if section != "general")
    if available_sections:
        fallback = available_sections[0]
        print(f"Warning: Section '{section_raw}' not found, adding to '{fallback}'")
        return fallback

    print(f"Warning: Section '{section_raw}' not found, adding to OTHERS")
    return "others"


def _build_new_bullet(
    bullet_id: str,
    section: str,
    content: str,
    current_step: int,
    *,
    helpful: int = 0,
    harmful: int = 0,
    neutral: int = 0,
    last_considered_step: int = 0,
    last_used_step: int = 0,
    times_considered_not_used: int = 0,
    status: str = "candidate",
) -> dict[str, Any]:
    """Create a new bullet dictionary with lifecycle metadata."""
    return {
        "id": bullet_id,
        "section": section,
        "helpful": helpful,
        "harmful": harmful,
        "neutral": neutral,
        "created_step": current_step,
        "last_considered_step": last_considered_step,
        "last_used_step": last_used_step,
        "times_considered_not_used": times_considered_not_used,
        "status": status,
        "content": content,
    }


def _render_playbook_items(
    items: list[dict[str, Any]], additions_by_section: dict[str, list[dict[str, Any]]] | None = None
) -> str:
    """Render playbook items back to text, inserting pending additions after each section."""
    pending = {section: bullets[:] for section, bullets in (additions_by_section or {}).items()}
    final_lines: list[str] = []
    current_section: str | None = None

    for item in items:
        if item["kind"] == "header":
            if current_section and pending.get(current_section):
                final_lines.extend(
                    format_parsed_playbook_line(bullet) for bullet in pending[current_section]
                )
                pending[current_section] = []
            current_section = item["section"]
            final_lines.append(item["raw"])
        elif item["kind"] == "bullet":
            final_lines.append(format_parsed_playbook_line(item["bullet"]))
        else:
            final_lines.append(item["raw"])

    if current_section and pending.get(current_section):
        final_lines.extend(
            format_parsed_playbook_line(bullet) for bullet in pending[current_section]
        )
        pending[current_section] = []

    leftovers = [bullet for bullets in pending.values() for bullet in bullets]
    if leftovers:
        inserted = False
        for index, line in enumerate(final_lines):
            if line.strip() == "## OTHERS":
                final_lines[index + 1 : index + 1] = [
                    format_parsed_playbook_line(bullet) for bullet in leftovers
                ]
                inserted = True
                break
        if not inserted:
            final_lines.extend(format_parsed_playbook_line(bullet) for bullet in leftovers)

    return "\n".join(final_lines)


def get_bullet_observations(parsed: dict[str, Any]) -> int:
    """Return the number of scored observations for a bullet."""
    return parsed.get("helpful", 0) + parsed.get("harmful", 0) + parsed.get("neutral", 0)


def bullet_score(parsed: dict[str, Any]) -> float:
    """Rank bullets for prompt retention and section pruning."""
    active_bonus = 0.5 if parsed.get("status") == "active" else 0.0
    return (
        (parsed.get("helpful", 0) * 2.0)
        - (parsed.get("harmful", 0) * 3.0)
        - parsed.get("neutral", 0)
        - parsed.get("times_considered_not_used", 0)
        + active_bonus
        + (parsed.get("last_used_step", 0) * 0.01)
        + (parsed.get("last_considered_step", 0) * 0.001)
    )


def render_active_playbook(playbook_text: str) -> str:
    """Render only prompt-eligible bullets for the generator."""
    rendered_lines: list[str] = []

    for line in playbook_text.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("##") or not stripped:
            rendered_lines.append(line)
            continue

        parsed = parse_playbook_line(line)
        if not parsed:
            rendered_lines.append(line)
            continue

        if parsed.get("status", DEFAULT_BULLET_STATUS) in ACTIVE_BULLET_STATUSES:
            rendered_lines.append(format_parsed_playbook_line(parsed))

    return "\n".join(rendered_lines)


def update_bullet_counts(
    playbook_text: str,
    bullet_tags: list[dict[str, str]],
    considered_bullet_ids: list[str] | None = None,
    used_bullet_ids: list[str] | None = None,
    current_step: int | None = None,
) -> str:
    """Update bullet evidence and lifecycle metadata based on considered/used bullets."""
    lines = playbook_text.strip().split("\n")
    updated_lines: list[str] = []

    tag_map: dict[str, str] = {}
    for tag in bullet_tags or []:
        if not isinstance(tag, dict):
            continue
        bullet_id = tag.get("id") or tag.get("bullet") or ""
        tag_value = tag.get("tag", "neutral")
        if bullet_id:
            tag_map[bullet_id] = tag_value

    considered_set = set(considered_bullet_ids or tag_map.keys())
    used_set = set(used_bullet_ids or [])

    if not tag_map and not considered_set and not used_set:
        print("Warning: No valid bullet evidence found to update counts")
        return playbook_text

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            updated_lines.append(line)
            continue

        parsed = parse_playbook_line(line)
        if not parsed:
            updated_lines.append(line)
            continue

        bullet_id = parsed["id"]
        was_considered = bullet_id in considered_set
        was_used = bullet_id in used_set

        if was_considered and current_step is not None:
            parsed["last_considered_step"] = current_step
        if was_used and current_step is not None:
            parsed["last_used_step"] = current_step
        if was_considered and not was_used:
            parsed["times_considered_not_used"] += 1

        tag = tag_map.get(bullet_id)
        if tag == "helpful":
            parsed["helpful"] += 1
        elif tag == "harmful":
            parsed["harmful"] += 1
        elif tag == "neutral":
            parsed["neutral"] += 1

        if parsed.get("status") == "candidate" and (was_used or tag == "helpful"):
            parsed["status"] = "active"

        updated_lines.append(format_parsed_playbook_line(parsed))

    return "\n".join(updated_lines)


def apply_curator_operations(
    playbook_text: str,
    operations: list[dict[str, Any]],
    next_id: int,
    current_step: int = 0,
) -> tuple[str, int]:
    """Apply curator lifecycle operations to the playbook."""
    items, bullet_index, sections = _parse_playbook_items(playbook_text)
    additions_by_section: dict[str, list[dict[str, Any]]] = {}

    for op in operations:
        if not isinstance(op, dict):
            continue

        op_type = op.get("type")

        if op_type == "ADD":
            section = _resolve_section_name(op.get("section", "general"), sections)
            slug = get_section_slug(section)
            bullet_id = f"{slug}-{next_id:05d}"
            next_id += 1

            additions_by_section.setdefault(section, []).append(
                _build_new_bullet(bullet_id, section, op.get("content", ""), current_step)
            )
            print(f"  Added bullet {bullet_id} to section {section}")
            continue

        if op_type == "UPDATE":
            bullet_id = op.get("bullet_id", "")
            item_index = bullet_index.get(bullet_id)
            if item_index is None:
                print(f"Warning: UPDATE skipped because bullet '{bullet_id}' was not found")
                continue

            bullet = items[item_index]["bullet"]
            bullet["content"] = op.get("content", bullet["content"])
            bullet["status"] = "candidate"
            print(f"  Updated bullet {bullet_id}")
            continue

        if op_type == "ARCHIVE":
            bullet_id = op.get("bullet_id", "")
            item_index = bullet_index.get(bullet_id)
            if item_index is None:
                print(f"Warning: ARCHIVE skipped because bullet '{bullet_id}' was not found")
                continue

            items[item_index]["bullet"]["status"] = "archived"
            print(f"  Archived bullet {bullet_id}")
            continue

        if op_type == "MERGE":
            source_ids = [
                source_id for source_id in op.get("source_ids", []) if source_id in bullet_index
            ]
            if len(source_ids) < 2:
                print("Warning: MERGE skipped because fewer than two source bullets were found")
                continue

            source_bullets = [items[bullet_index[source_id]]["bullet"] for source_id in source_ids]
            for source_bullet in source_bullets:
                source_bullet["status"] = "archived"

            section = _resolve_section_name(
                op.get("section", source_bullets[0]["section"]),
                sections | {source_bullets[0]["section"]},
            )
            slug = get_section_slug(section)
            merged_id = f"{slug}-{next_id:05d}"
            next_id += 1

            additions_by_section.setdefault(section, []).append(
                _build_new_bullet(
                    merged_id,
                    section,
                    op.get("content", ""),
                    current_step,
                    helpful=sum(bullet.get("helpful", 0) for bullet in source_bullets),
                    harmful=sum(bullet.get("harmful", 0) for bullet in source_bullets),
                    neutral=sum(bullet.get("neutral", 0) for bullet in source_bullets),
                    last_considered_step=max(
                        bullet.get("last_considered_step", 0) for bullet in source_bullets
                    ),
                    last_used_step=max(
                        bullet.get("last_used_step", 0) for bullet in source_bullets
                    ),
                    times_considered_not_used=sum(
                        bullet.get("times_considered_not_used", 0) for bullet in source_bullets
                    ),
                )
            )
            print(f"  Merged bullets {source_ids} into {merged_id}")
            continue

        if op_type == "CREATE_META":
            print("Warning: CREATE_META is ignored by the lifecycle executor")
            continue

        print(f"Warning: Unsupported curator operation '{op_type}'")

    return _render_playbook_items(items, additions_by_section), next_id


def prune_playbook(
    playbook_text: str,
    current_step: int,
    *,
    max_active_bullets_per_section: int = DEFAULT_SECTION_CAP,
    warmup_window: int = DEFAULT_WARMUP_WINDOW,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> tuple[str, list[str]]:
    """Apply deterministic archive rules to keep the active playbook bounded."""
    items, _, _ = _parse_playbook_items(playbook_text)
    section_bullets: dict[str, list[dict[str, Any]]] = {}

    for item in items:
        if item["kind"] != "bullet":
            continue

        bullet = item["bullet"]
        if bullet.get("status", DEFAULT_BULLET_STATUS) not in ACTIVE_BULLET_STATUSES:
            continue

        section_bullets.setdefault(item["section"], []).append(bullet)

    archived_ids: list[str] = []
    archived_id_set: set[str] = set()

    for bullets in section_bullets.values():
        retained: list[dict[str, Any]] = []

        for bullet in bullets:
            created_step = bullet.get("created_step", 0)
            age = current_step - created_step if created_step > 0 else 0
            observations = get_bullet_observations(bullet)
            never_used = bullet.get("last_used_step", 0) == 0
            harmful_dominates = (
                observations >= min_observations
                and bullet.get("harmful", 0) > bullet.get("helpful", 0)
                and bullet.get("harmful", 0) >= max(1, bullet.get("neutral", 0))
            )

            if never_used and age >= warmup_window:
                archived_id_set.add(bullet["id"])
                archived_ids.append(bullet["id"])
                continue

            if harmful_dominates:
                archived_id_set.add(bullet["id"])
                archived_ids.append(bullet["id"])
                continue

            retained.append(bullet)

        ranked = sorted(retained, key=bullet_score, reverse=True)
        for bullet in ranked[max_active_bullets_per_section:]:
            if bullet["id"] not in archived_id_set:
                archived_id_set.add(bullet["id"])
                archived_ids.append(bullet["id"])

    if not archived_id_set:
        return playbook_text, []

    for item in items:
        if item["kind"] == "bullet" and item["bullet"]["id"] in archived_id_set:
            item["bullet"]["status"] = "archived"

    return _render_playbook_items(items), archived_ids


def get_playbook_stats(playbook_text: str) -> dict[str, Any]:
    """Generate statistics about the playbook, including lifecycle state counts."""
    lines = playbook_text.strip().split("\n")
    stats: dict[str, Any] = {
        "total_bullets": 0,
        "active_bullets": 0,
        "candidate_bullets": 0,
        "archived_bullets": 0,
        "high_performing": 0,
        "problematic": 0,
        "unused": 0,
        "by_section": {},
    }

    current_section = "general"

    for line in lines:
        if line.strip().startswith("##"):
            current_section = line.strip()[2:].strip()
            continue

        parsed = parse_playbook_line(line)
        if not parsed:
            continue

        stats["total_bullets"] += 1
        observations = get_bullet_observations(parsed)
        status = parsed.get("status", DEFAULT_BULLET_STATUS)

        if status == "active":
            stats["active_bullets"] += 1
        elif status == "candidate":
            stats["candidate_bullets"] += 1
        elif status == "archived":
            stats["archived_bullets"] += 1

        if parsed["helpful"] > 5 and parsed["harmful"] < 2:
            stats["high_performing"] += 1
        elif parsed["harmful"] > parsed["helpful"] and parsed["harmful"] > 0:
            stats["problematic"] += 1
        elif observations == 0:
            stats["unused"] += 1

        section_stats = stats["by_section"].setdefault(
            current_section,
            {
                "count": 0,
                "active": 0,
                "candidate": 0,
                "archived": 0,
                "helpful": 0,
                "harmful": 0,
                "neutral": 0,
            },
        )
        section_stats["count"] += 1
        section_stats[status] = section_stats.get(status, 0) + 1
        section_stats["helpful"] += parsed["helpful"]
        section_stats["harmful"] += parsed["harmful"]
        section_stats["neutral"] += parsed["neutral"]

    return stats


def extract_json_from_text(text, json_key=None):
    """Extract JSON object from text, handling various formats."""
    try:
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        json_pattern = r"```json\s*(.*?)\s*```"
        matches = re.findall(json_pattern, text, re.DOTALL | re.IGNORECASE)

        if matches:
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        def find_json_objects(raw_text):
            """Find JSON objects using balanced brace counting."""
            json_objects = []
            i = 0
            while i < len(raw_text):
                if raw_text[i] == "{":
                    brace_count = 1
                    start = i
                    i += 1

                    while i < len(raw_text) and brace_count > 0:
                        if raw_text[i] == "{":
                            brace_count += 1
                        elif raw_text[i] == "}":
                            brace_count -= 1
                        elif raw_text[i] == '"':
                            i += 1
                            while i < len(raw_text) and raw_text[i] != '"':
                                if raw_text[i] == "\\":
                                    i += 1
                                i += 1
                        i += 1

                    if brace_count == 0:
                        json_objects.append(raw_text[start:i])
                else:
                    i += 1

            return json_objects

        for json_str in find_json_objects(text):
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    except Exception as exc:
        print(f"Failed to extract JSON: {exc}")
        preview = text[:500] + "..." if len(text) > 500 else text
        print(f"Raw content preview:\n{preview}")

    return None


def extract_playbook_bullets(playbook_text: str, bullet_ids: list[str]) -> str:
    """Extract specific bullets from the playbook for reflector input."""
    if not bullet_ids:
        return "(No bullets considered by generator)"

    found_bullets: list[str] = []
    bullet_id_set = set(bullet_ids)

    for line in playbook_text.strip().split("\n"):
        parsed = parse_playbook_line(line)
        if parsed and parsed["id"] in bullet_id_set:
            found_bullets.append(format_parsed_playbook_line(parsed))

    if not found_bullets:
        return "(Generator referenced bullet IDs but none were found in playbook)"

    return "\n".join(found_bullets)
