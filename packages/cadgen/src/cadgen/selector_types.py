from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SelectorProfile(str, Enum):
    SUMMARY = "summary"
    REFS = "refs"
    ARTIFACT = "artifact"


@dataclass
class SelectorBundle:
    manifest: dict[str, Any]
    buffers: dict[str, array] = field(default_factory=dict)
