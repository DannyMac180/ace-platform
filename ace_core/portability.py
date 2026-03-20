"""Portable import/export models for playbooks and traces."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PORTABLE_BUNDLE_KIND = "ace.playbook_bundle"
PORTABLE_BUNDLE_VERSION = 1
PORTABLE_PLAYBOOK_NAME_MAX_LENGTH = 255
PORTABLE_PLAYBOOK_CONTENT_MAX_LENGTH = 102_400
PortableOutcome = Literal["success", "failure", "partial"]
PortableScopeKind = Literal["user", "workspace", "organization", "global"]


class PortableScope(BaseModel):
    """Portable scope descriptor shared across local and hosted contexts."""

    kind: PortableScopeKind = "user"
    id: str | None = None


class PortableTrace(BaseModel):
    """Portable task trace captured alongside a playbook."""

    id: str | None = None
    task_description: str
    outcome: PortableOutcome
    notes: str | None = None
    reasoning_trace: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortablePlaybookVersion(BaseModel):
    """Portable immutable playbook version."""

    id: str | None = None
    version_number: int = Field(ge=1)
    content: str = Field(max_length=PORTABLE_PLAYBOOK_CONTENT_MAX_LENGTH)
    bullet_count: int = Field(default=0, ge=0)
    diff_summary: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortablePlaybook(BaseModel):
    """Portable playbook artifact with versions and traces."""

    id: str | None = None
    name: str = Field(min_length=1, max_length=PORTABLE_PLAYBOOK_NAME_MAX_LENGTH)
    description: str | None = None
    status: str = "active"
    source: str | None = None
    scope: PortableScope = Field(default_factory=PortableScope)
    current_version_id: str | None = None
    current_version_number: int | None = Field(default=None, ge=1)
    versions: list[PortablePlaybookVersion] = Field(default_factory=list)
    traces: list[PortableTrace] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_versions(self) -> PortablePlaybook:
        version_numbers = [version.version_number for version in self.versions]
        if len(set(version_numbers)) != len(version_numbers):
            raise ValueError("Portable playbook version numbers must be unique")

        version_ids = {version.id for version in self.versions if version.id is not None}
        if self.current_version_id is not None and self.current_version_id not in version_ids:
            raise ValueError("current_version_id must reference a version in the bundle")

        if self.current_version_number is not None and self.current_version_number not in set(
            version_numbers
        ):
            raise ValueError("current_version_number must reference a version in the bundle")

        return self


class PortableBundleOrigin(BaseModel):
    """Metadata describing where a portable bundle was produced."""

    system: str = "ace-platform"
    context: str | None = None
    api_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortablePlaybookBundle(BaseModel):
    """Stable, versioned bundle for importing/exporting playbooks and traces."""

    kind: Literal["ace.playbook_bundle"] = PORTABLE_BUNDLE_KIND
    schema_version: Literal[1] = PORTABLE_BUNDLE_VERSION
    exported_at: datetime | None = None
    origin: PortableBundleOrigin = Field(default_factory=PortableBundleOrigin)
    playbooks: list[PortablePlaybook] = Field(default_factory=list)


def bundle_to_json(bundle: PortablePlaybookBundle) -> str:
    """Serialize a portable bundle into canonical JSON."""

    return (
        json.dumps(
            bundle.model_dump(mode="json", exclude_none=True),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def bundle_from_json(payload: str | bytes) -> PortablePlaybookBundle:
    """Deserialize a portable bundle from JSON."""

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return PortablePlaybookBundle.model_validate_json(payload)


__all__ = [
    "PORTABLE_BUNDLE_KIND",
    "PORTABLE_BUNDLE_VERSION",
    "PORTABLE_PLAYBOOK_CONTENT_MAX_LENGTH",
    "PORTABLE_PLAYBOOK_NAME_MAX_LENGTH",
    "PortableBundleOrigin",
    "PortableOutcome",
    "PortablePlaybook",
    "PortablePlaybookBundle",
    "PortablePlaybookVersion",
    "PortableScope",
    "PortableScopeKind",
    "PortableTrace",
    "bundle_from_json",
    "bundle_to_json",
]
