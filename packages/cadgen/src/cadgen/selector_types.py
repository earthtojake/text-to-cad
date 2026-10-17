from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SelectorBundle:
    manifest: dict[str, Any]
