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

_FAKE_DOC_PRELUDE = [
    "import ezdxf",
    "def _make_doc():",
    "    doc = ezdxf.new('R2010')",
    "    doc.units = ezdxf.units.MM",
    "    doc.modelspace().add_lwpolyline(",
    "        [(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={'layer': 'CUT'}",
    "    )",
    "    return doc",
]


def _closure(root: Path, name: str) -> list[str]:
    descriptor_path = root / "__cadgen__" / "models" / f"{name}.dxf.py" / "drawing.json"
    return sorted(json.loads(descriptor_path.read_text(encoding="utf-8"))["sourceClosureFiles"])


class ClosureCaptureTests(unittest.TestCase):
    def test_module_unloaded_mid_run_is_still_recorded(self) -> None:
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "geom_helper.py").write_text(_HELPER, encoding="utf-8")
            (root / "popper.dxf.py").write_text(
                "\n".join(
                    [
                        "import sys",
                        "import geom_helper",
                        *_FAKE_DOC_PRELUDE,
                        "def gen_dxf():",
                        "    size = geom_helper.SIZE_MM",
                        "    sys.modules.pop('geom_helper', None)",
                        "    return {'document': _make_doc()}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            cad_generation.generate_dxf_targets([str(root / "popper.dxf.py")])

            self.assertIn("geom_helper.py", _closure(root, "popper"))

    def test_multi_target_run_records_shared_helper_for_every_target(self) -> None:
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "geom_helper.py").write_text(_HELPER, encoding="utf-8")
            for name in ("first", "second"):
                (root / f"{name}.dxf.py").write_text(
                    "\n".join(
                        [
                            "import geom_helper",
                            *_FAKE_DOC_PRELUDE,
                            "def gen_dxf():",
                            "    assert geom_helper.SIZE_MM > 0",
                            "    return {'document': _make_doc()}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            cad_generation.generate_dxf_targets(
                [str(root / "first.dxf.py"), str(root / "second.dxf.py")]
            )

            self.assertIn("geom_helper.py", _closure(root, "first"))
            self.assertIn("geom_helper.py", _closure(root, "second"))

    def test_failed_build_does_not_poison_the_next_capture(self) -> None:
        # Warm-process shape: a failing build followed by a fixed build in the SAME
        # interpreter must still record the full closure.
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "geom_helper.py").write_text(_HELPER, encoding="utf-8")
            script = root / "flaky.dxf.py"
            failing = "\n".join(
                [
                    "import geom_helper",
                    *_FAKE_DOC_PRELUDE,
                    "def gen_dxf():",
                    "    if geom_helper.SIZE_MM > 0:",
                    "        raise RuntimeError('boom')",
                    "    return {'document': _make_doc()}",
                    "",
                ]
            )
            fixed = "\n".join(
                [
                    "import geom_helper",
                    *_FAKE_DOC_PRELUDE,
                    "def gen_dxf():",
                    "    assert geom_helper.SIZE_MM > 0",
                    "    return {'document': _make_doc()}",
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
        # A drawing that path-loads its sibling .step.py through cadgen.sources must
        # record the sibling but never the running runtime's own files.
        with temporary_directory(prefix="closure") as raw_root:
            root = Path(raw_root)
            (root / "part.step.py").write_text(
                "WIDTH_MM = 12.0\n\ndef gen_step():\n    return {'shape': object()}\n",
                encoding="utf-8",
            )
            (root / "part.dxf.py").write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "from cadgen.sources import load_source_module",
                        "_step = load_source_module(Path(__file__).with_name('part.step.py'))",
                        "import ezdxf",
                        "def gen_dxf():",
                        "    assert _step.WIDTH_MM > 0",
                        "    doc = ezdxf.new('R2010')",
                        "    doc.units = ezdxf.units.MM",
                        "    doc.modelspace().add_lwpolyline(",
                        "        [(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={'layer': 'CUT'}",
                        "    )",
                        "    return {'document': doc}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            cad_generation.generate_dxf_targets([str(root / "part.dxf.py")])

            closure = _closure(root, "part")
            self.assertIn("part.step.py", closure)
            for entry in closure:
                resolved = (root / entry).resolve()
                self.assertFalse(
                    resolved.is_relative_to(_CADGEN_ROOT),
                    f"runtime file leaked into closure: {entry}",
                )
                self.assertNotIn("__main__", entry)


if __name__ == "__main__":
    unittest.main()
