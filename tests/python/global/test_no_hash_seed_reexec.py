"""No cadgen entry point restarts the interpreter to pin ``PYTHONHASHSEED``.

There used to be one, and it cost a whole second interpreter on every cold
drawing build. Drawing bytes were content-addressed while ezdxf's emitted order
followed string hashing, so a cold ``@dxf`` run re-ran itself with the seed
pinned — first from the retired `dxf gen` dispatch, then from the ``@dxf``
decorator, and briefly from a ``cadgen dxf build`` engine path. The re-run also
had a Windows hazard of its own (issue #245: ``os.execv`` does not quote, so an
interpreter path containing a space arrived as two arguments).

That whole apparatus is deleted. The engine's DXF export (``cadgen.engine.export.dxf``)
makes DXF bytes a function of the drawing's geometry — layers sorted by name, edges
sorted by geometric content, ezdxf's volatile provenance pinned, and its CLASSES
registry (the actual seed-sensitive part) sorted — so the seed cannot reach the file.

The engine's daemon is in scope too. Workers once were spawned with the seed pinned,
which was the same ritual by another route, and worse in one way: a worker whose seed
differed from every other process was a standing warm/cold divergence, ready to hide
the next ordering bug rather than reveal it.

This guard exists because the re-exec is easy to reintroduce and expensive:
it would silently double the cold cost of every drawing, and nothing else in
the suite would notice. If a genuine need for a stable seed ever returns, fix
the ordering that depends on it instead.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CADGEN = REPO_ROOT / "packages/cadgen/src/cadgen"

# Named explicitly rather than globbed: a glob over cadgen would sweep in modules
# that legitimately spawn other programs. These are the places a build starts -- the
# front door, a model script asking the daemon, the engine's commands, its client
# starting the daemon, the daemon spawning a worker, the worker's build.
ENTRY_POINT_SOURCES = [
    CADGEN / "cli/__init__.py",
    CADGEN / "engine/model.py",
    CADGEN / "engine/cli.py",
    CADGEN / "engine/client.py",
    CADGEN / "engine/daemon.py",
    CADGEN / "engine/worker.py",
    CADGEN / "engine/build.py",
]


def _entry_point_sources() -> list[Path]:
    return [path for path in ENTRY_POINT_SOURCES if path.is_file()]


def _strip_comments(source: str) -> str:
    """Drop comments and docstrings: these files are free to EXPLAIN the deletion."""
    without_comments = re.sub(r"#[^\n]*", "", source)
    return re.sub(r'"""(?:.|\n)*?"""', "", without_comments)


class NoHashSeedReExecTest(unittest.TestCase):
    def test_every_named_entry_point_exists(self) -> None:
        self.assertEqual(
            [path.name for path in _entry_point_sources()],
            [path.name for path in ENTRY_POINT_SOURCES],
            "a named entry point moved; point this guard at its new home",
        )

    def test_no_entry_point_pins_the_hash_seed(self) -> None:
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in _entry_point_sources()
            if "PYTHONHASHSEED" in _strip_comments(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(
            [],
            offenders,
            "an entry point pins PYTHONHASHSEED again. DXF byte-determinism is "
            "engineered in cadgen.engine.export.dxf; a seed re-exec would double "
            "every cold drawing build to hide an ordering bug instead of fixing it.",
        )

    def test_no_entry_point_re_execs_the_interpreter(self) -> None:
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in _entry_point_sources()
            if re.search(
                r"\bos\.execv|subprocess\.run\(\s*\[\s*sys\.executable\s*,\s*\*?sys\.argv",
                _strip_comments(path.read_text(encoding="utf-8")),
            )
        ]
        self.assertEqual([], offenders, "an entry point restarts itself; it should not need to")


if __name__ == "__main__":
    unittest.main()
