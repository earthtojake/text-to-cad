"""Regression tests for deterministic source-closure capture.

The closure must be complete in every process shape: when a generator unloads
modules from ``sys.modules`` mid-run, when several targets build sequentially in
one process, and after a failed build in a long-lived (warm) process. It must
also never contain the running runtime's own files (cadgen, CLI launchers).
"""

import json
import unittest
from pathlib import Path

import cadgen
from cadgen._internal import generation as cad_generation
from tests.python.support.tmp_root import temporary_directory

_CADGEN_ROOT = Path(cadgen.__file__).resolve().parent

_HELPER = "SIZE_MM = 10.0\n"

_DRAWING_PRELUDE = [
    "from cadgen import build123d as bd",
    "def _make_drawing():",
    "    with bd.BuildSketch() as cut:",
    "        bd.Rectangle(10, 5)",
    "    return cut.sketch",
]


def _closure(root: Path, name: str) -> list[str]:
    # A drawing is a model in the graph: its closure is in its model record
    # (STORE.md §3), keyed by the script like any @step model's.
    from cadgen.store.records import read_record

    record = read_record(root / f"{name}.py")
    if not record:
        raise AssertionError(f"no record for {name}.py under {root}")
    return sorted((record.get("closure") or {}).get("files") or [])


class ClosureCaptureTests(unittest.TestCase):
    def test_module_unloaded_mid_run_is_still_recorded(self) -> None:
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "geom_helper.py").write_text(_HELPER, encoding="utf-8")
            (root / "popper.py").write_text(
                "\n".join(
                    [
                        "import sys",
                        "import geom_helper",
                        *_DRAWING_PRELUDE,
                        "from cadgen import dxf",
                        "@dxf",
                        "def drawing():",
                        "    size = geom_helper.SIZE_MM",
                        "    sys.modules.pop('geom_helper', None)",
                        "    return _make_drawing()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            cad_generation.generate_dxf_targets([str(root / "popper.py")])

            self.assertIn("geom_helper.py", _closure(root, "popper"))

    def test_multi_target_run_records_shared_helper_for_every_target(self) -> None:
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "geom_helper.py").write_text(_HELPER, encoding="utf-8")
            for name in ("first", "second"):
                (root / f"{name}.py").write_text(
                    "\n".join(
                        [
                            "import geom_helper",
                            *_DRAWING_PRELUDE,
                            "from cadgen import dxf",
                            "@dxf",
                            "def drawing():",
                            "    assert geom_helper.SIZE_MM > 0",
                            "    return _make_drawing()",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            cad_generation.generate_dxf_targets(
                [str(root / "first.py"), str(root / "second.py")]
            )

            self.assertIn("geom_helper.py", _closure(root, "first"))
            self.assertIn("geom_helper.py", _closure(root, "second"))

    def test_failed_build_does_not_poison_the_next_capture(self) -> None:
        # Warm-process shape: a failing build followed by a fixed build in the SAME
        # interpreter must still record the full closure.
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "geom_helper.py").write_text(_HELPER, encoding="utf-8")
            script = root / "flaky.py"
            failing = "\n".join(
                [
                    "import geom_helper",
                    *_DRAWING_PRELUDE,
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    if geom_helper.SIZE_MM > 0:",
                    "        raise RuntimeError('boom')",
                    "    return _make_drawing()",
                    "",
                ]
            )
            fixed = "\n".join(
                [
                    "import geom_helper",
                    *_DRAWING_PRELUDE,
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    assert geom_helper.SIZE_MM > 0",
                    "    return _make_drawing()",
                    "",
                ]
            )
            script.write_text(failing, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "boom"):
                cad_generation.generate_dxf_targets([str(script)])

            script.write_text(fixed, encoding="utf-8")
            cad_generation.generate_dxf_targets([str(script)])

            self.assertIn("geom_helper.py", _closure(root, "flaky"))

    def test_runtime_files_never_enter_closures(self) -> None:
        # A drawing that path-loads its sibling .py through cadgen.sources must
        # record the sibling but never the running runtime's own files.
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "part.py").write_text(
                "WIDTH_MM = 12.0\n\ndef model():\n    return {'shape': object()}\n",
                encoding="utf-8",
            )
            (root / "part_drawing.py").write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "from cadgen.sources import load_source_module",
                        "_step = load_source_module(Path(__file__).with_name('part.py'))",
                        "from cadgen import build123d as bd",
                        "from cadgen import dxf",
                        "@dxf",
                        "def drawing():",
                        "    assert _step.WIDTH_MM > 0",
                        "    with bd.BuildSketch() as cut:",
                        "        bd.Rectangle(10, 5)",
                        "    return cut.sketch",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            cad_generation.generate_dxf_targets([str(root / "part_drawing.py")])

            closure = _closure(root, "part_drawing")
            self.assertIn("part.py", closure)
            for entry in closure:
                resolved = (root / entry).resolve()
                self.assertFalse(
                    resolved.is_relative_to(_CADGEN_ROOT),
                    f"runtime file leaked into closure: {entry}",
                )
                self.assertNotIn("__main__", entry)


if __name__ == "__main__":
    unittest.main()
