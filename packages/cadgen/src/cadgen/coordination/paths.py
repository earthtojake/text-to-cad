"""Where an artifact's coordination files live.

One derivation, imported by BOTH the producer (cadgen) and the reader (the CAD Viewer's
server), so the two can no longer disagree about which file to look at. Before this module
the derivation existed twice -- ``cadgen._internal.generation_status.generation_lock_path``
and a hand-written copy in ``viewer/server_py/artifact.py`` -- kept in sync only by a test
that compared path strings.

All three files are HIDDEN SIBLINGS of the artifact's output directory, so they live under
the gitignored ``__cadgen__`` tree next to the package they describe. For an output dir
``<folder>/__cadgen__/models/<name>.step`` the files are::

    <folder>/__cadgen__/models/.<name>.step.generation.lock           writer sentinel
    <folder>/__cadgen__/models/.<name>.step.generator.lock            generator sentinel
    <folder>/__cadgen__/models/.<name>.step.generation.progress.json  status record

The names are fixed per output dir, which is what lets an arbitrary reader find them
without being told anything but the directory.
"""

from __future__ import annotations

from pathlib import Path

# The writer sentinel's name is FROZEN. A bundled skill carrying an older cadgen and a
# newer viewer (or the reverse) must still mutually exclude during a rollout, and that
# only works while both derive the same path.
WRITE_LOCK_SUFFIX = ".generation.lock"

# Held by a run that occupies the model's generator but writes no package (an export, an
# on-demand topology extraction). Separate from the writer sentinel so a reader can tell
# "this model is being rewritten" from "this model's generator is busy" -- the former must
# hide the artifact, the latter must not.
GENERATOR_LOCK_SUFFIX = ".generator.lock"

# The status record. Deliberately still named `.generation.progress.json`: the v2 schema is
# a strict superset of v1, so a reader that predates this package keeps working unchanged
# while producers are migrated. Renaming it would open a window -- between the producer
# cutover and the reader cutover -- where the viewer showed `generating` with no bar.
STATUS_SUFFIX = ".generation.progress.json"

# The GENERATOR run's status record, and the reason there are two. Generator runs and writer
# runs take different sentinels ON PURPOSE, so they do not exclude each other -- which meant
# that while they shared one record file, an export's record landed on top of a live build's
# progress. `snapshot()` attributes progress only to the WRITE sentinel's holder, so the
# export's run id did not match and the build's bar vanished mid-run; worse, the export's
# terminal record carries no `stageMs`, so it also erased the phase weighting the next build
# reads. Nothing consumes this file today -- it exists so a generator run has somewhere of
# its own to report, and cannot reach the writer's record.
GENERATOR_STATUS_SUFFIX = ".generator.progress.json"


def _sibling(output_dir: Path | str, suffix: str) -> Path:
    package = Path(output_dir)
    return package.parent / f".{package.name}{suffix}"


def write_lock_path(output_dir: Path | str) -> Path:
    """The sentinel held for the duration of a run that MUTATES ``output_dir``."""
    return _sibling(output_dir, WRITE_LOCK_SUFFIX)


def generator_lock_path(output_dir: Path | str) -> Path:
    """The sentinel held by a run that occupies the generator but writes no package."""
    return _sibling(output_dir, GENERATOR_LOCK_SUFFIX)


def status_path(output_dir: Path | str) -> Path:
    """The status/progress record describing the most recent WRITER run for ``output_dir``."""
    return _sibling(output_dir, STATUS_SUFFIX)


def generator_status_path(output_dir: Path | str) -> Path:
    """The status record for a run that occupies ``output_dir``'s generator but writes no
    package. Separate from :func:`status_path` so it cannot overwrite a live build's."""
    return _sibling(output_dir, GENERATOR_STATUS_SUFFIX)
