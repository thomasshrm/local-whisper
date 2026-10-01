"""Values shared by storage, orchestration and engine adapters."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Kind(StrEnum):
    RAW = "raw"
    INTELLIGENT = "intelligent"
    REPORT = "report"


class Status(StrEnum):
    QUEUED = "queued"
    LOADING = "loading model"
    TRANSCRIBING = "transcribing"
    PROCESSING = "post-processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class Result:
    text: str
    engine: str
    model: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Version:
    id: str
    source_id: str
    kind: Kind
    parent_id: str | None
    text: str
    engine: str
    model: str
    created_at: str
    parameters: dict[str, Any]
