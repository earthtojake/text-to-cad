"""The publish rule — the ONLY mechanism for concurrent builds of one model.

*Never replace a current record with a stale one.* At publish, re-hash the
model's closure files as they are on disk NOW and compare with the bytes this
build ran:

- unchanged → publish everything;
- changed (this build is already stale) → if the record on disk is current,
  publish only the objects (content-addressed, harmless) and skip record +
  outputs; if the record on disk is also stale, publish anyway.

There is no serialization and no dedupe: two builds of one model run at once,
whatever their sources; the disk never goes backwards; a build never blocks its
author. Check-then-rename is not atomic — in a microsecond window a stale result
can still land last — and the ordinary gate catches that on the next request.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cadgen.store.closure import current_closure_hash
from cadgen.store.gate import stale


@dataclass(frozen=True)
class PublishDecision:
    publish_outputs: bool
    reason: str


def decide(model: Path | str, *, ran_closure_hash: str, ran_files: Iterable[str]) -> PublishDecision:
    """Whether this build may publish its record + named outputs."""
    now = current_closure_hash(Path(model), list(ran_files))
    if now == ran_closure_hash:
        return PublishDecision(True, "source unchanged since this build ran")
    # This build ran source that has moved on. Only defer to the disk if what is
    # there is CURRENT — a stale result is still better than nothing.
    if not stale(model).stale:
        return PublishDecision(False, "source changed during the build and the record on disk is already current")
    return PublishDecision(True, "source changed during the build; publishing anyway (record on disk is stale too)")
