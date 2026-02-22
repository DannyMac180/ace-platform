"""Acquisition tracking helpers.

Utilities for normalizing attribution payloads and source/channel metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

_X_SOURCE_ALIASES = {
    "x",
    "x.com",
    "www.x.com",
    "twitter",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    "t.co",
}

_SUPPORTED_ATTRIBUTION_KEYS = {
    "src",
    "source",
    "channel",
    "campaign",
    "aid",
    "anonymous_id",
    "referrer_host",
    "landing_path",
    "device_type",
    "exp_trial_disclosure",
    "experiment_variant",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}


@dataclass(frozen=True)
class ParsedAttribution:
    """Normalized attribution payload with convenient accessors."""

    source: str | None
    channel: str | None
    campaign: str | None
    snapshot: dict[str, str] | None


def _normalize_text(value: Any, *, max_length: int = 255) -> str | None:
    """Normalize a text value into a compact string or ``None``."""
    if value is None:
        return None

    if isinstance(value, bool):
        raw = "true" if value else "false"
    elif isinstance(value, (int, float)):
        raw = str(value)
    elif isinstance(value, str):
        raw = value
    else:
        return None

    normalized = raw.strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _normalize_referrer_host(value: str | None) -> str | None:
    """Normalize a referrer host or URL into a lowercase hostname."""
    text = _normalize_text(value, max_length=255)
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.hostname:
        return parsed.hostname.lower()

    # Handle host values without a scheme.
    host_only = text.split("/", 1)[0].split(":", 1)[0].lower()
    return host_only or None


def canonicalize_source(source: str | None, referrer_host: str | None = None) -> str | None:
    """Canonicalize source aliases (x|twitter|t.co -> x)."""
    candidate = _normalize_text(source, max_length=64)
    if not candidate:
        candidate = _normalize_referrer_host(referrer_host)

    if not candidate:
        return None

    lowered = candidate.lower()
    if lowered in _X_SOURCE_ALIASES:
        return "x"

    if lowered.endswith("x.com") or lowered.endswith("twitter.com") or lowered == "t.co":
        return "x"

    return lowered


def canonicalize_channel(source: str | None, channel: str | None = None) -> str | None:
    """Canonicalize channel from source and optional explicit channel."""
    explicit = _normalize_text(channel, max_length=64)
    if explicit:
        return explicit.lower()

    if source == "x":
        return "social"

    return None


def normalize_attribution_snapshot(
    attribution: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    """Normalize attribution payload to a small JSON-safe dictionary."""
    if not attribution:
        return None

    snapshot: dict[str, str] = {}
    for key, value in attribution.items():
        if key not in _SUPPORTED_ATTRIBUTION_KEYS and not key.startswith("utm_"):
            continue

        max_len = 255
        if key in {"landing_path", "referrer_host", "campaign", "utm_campaign", "utm_content"}:
            max_len = 512
        elif key in {"anonymous_id", "aid"}:
            max_len = 128

        text = _normalize_text(value, max_length=max_len)
        if text:
            snapshot[key] = text

    if "referrer_host" in snapshot:
        normalized_referrer = _normalize_referrer_host(snapshot["referrer_host"])
        if normalized_referrer:
            snapshot["referrer_host"] = normalized_referrer

    if "landing_path" in snapshot:
        path = snapshot["landing_path"]
        if not path.startswith("/"):
            snapshot["landing_path"] = f"/{path}"

    source_candidate = snapshot.get("src") or snapshot.get("source") or snapshot.get("utm_source")
    source = canonicalize_source(source_candidate, snapshot.get("referrer_host"))
    if source:
        snapshot["source"] = source

    channel_candidate = snapshot.get("channel") or snapshot.get("utm_medium")
    channel = canonicalize_channel(source, channel_candidate)
    if channel:
        snapshot["channel"] = channel

    campaign = snapshot.get("utm_campaign") or snapshot.get("campaign")
    if campaign:
        snapshot["campaign"] = campaign

    return snapshot or None


def parse_signup_attribution(attribution: Mapping[str, Any] | None) -> ParsedAttribution:
    """Parse and normalize attribution fields for signup persistence."""
    snapshot = normalize_attribution_snapshot(attribution)
    if not snapshot:
        return ParsedAttribution(source=None, channel=None, campaign=None, snapshot=None)

    source = canonicalize_source(snapshot.get("source"), snapshot.get("referrer_host"))
    channel = canonicalize_channel(source, snapshot.get("channel"))
    campaign = snapshot.get("campaign")

    return ParsedAttribution(
        source=source,
        channel=channel,
        campaign=campaign,
        snapshot=snapshot,
    )


def attribution_from_query_params(query: Mapping[str, Any]) -> dict[str, str] | None:
    """Build a normalized attribution snapshot from URL query parameters."""
    raw: dict[str, Any] = {}
    for key in _SUPPORTED_ATTRIBUTION_KEYS:
        value = query.get(key)
        if value is not None:
            raw[key] = value

    return normalize_attribution_snapshot(raw)
