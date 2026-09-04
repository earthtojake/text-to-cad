"""The three mesh format doors: `cadgen stl|3mf|glb build` (design/format-doors.md).

What a door owns is the mapping from argv to ONE engine call — the tessellation
itself belongs to `cadgen._internal.mesh_export` and is tested against real
geometry elsewhere. So these pin the mapping: each door's format string, `OUT`
omitted meaning the model's declarations, an explicit `OUT`, the tolerance
overrides, `--force`, and the Result the CLI prints.

Derivation rules (which flags exist at all) are pinned in
test_cli_from_function.py, and the parser⇄signature identity in
test_public_surface.py; nothing here re-asserts either.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


def native(posix_path: str) -> str:
    """A path the doors printed back: pathlib hands it out in the NATIVE
    spelling, so expectations are built the same way instead of hardcoding the
    POSIX separator."""
    return str(Path(posix_path))

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.cli import glb_build, stl_build, threemf_build  # noqa: E402

# The engine payload for one written STL, in the shape export_cad_target returns.
_WROTE_STL = {
    "ok": True,
    "files": [
        {
            "format": "stl",
            "path": "/abs/sample.stl",
            "skipped": False,
            "meshTolerance": None,
            "meshAngularTolerance": None,
        }
    ],
}

DOORS = (
    ("stl", stl_build, "cadgen.stl"),
    ("3mf", threemf_build, "cadgen.threemf"),
    ("glb", glb_build, "cadgen.glb"),
)


@contextlib.contextmanager
def _engine(payload: dict = _WROTE_STL):
    """Stand in for the shared engine at its one call site."""
    with mock.patch(
        "cadgen.step_export_target.export_cad_target", return_value=payload
    ) as export:
        yield export


class DoorArguments(unittest.TestCase):
    """What a door asks the engine for. The printed Result is DoorResults' job,
    so these keep it out of the test log."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        import tempfile

        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        # DOCUMENTS-ONLY: a door resolves its target as a document that exists,
        # so the mapping under test starts from a real file.
        self.document = root / "sample.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")

    def test_each_door_names_exactly_its_own_format(self):
        for fmt, module, _ in DOORS:
            with self.subTest(format=fmt), _engine() as export:
                self.assertEqual(0, module.main([str(self.document)]))
            self.assertEqual([(fmt, None)], export.call_args.args[1])

    def test_a_bare_target_asks_for_the_declarations(self):
        # `OUT` omitted is None all the way to the engine, where it means EVERY
        # variant of this format the DOCUMENT's sidecar declares.
        with _engine() as export:
            self.assertEqual(0, stl_build.main([str(self.document)]))
        self.assertEqual(self.document, export.call_args.args[0])
        self.assertEqual([("stl", None)], export.call_args.args[1])

    def test_an_explicit_out_is_one_ad_hoc_export(self):
        with _engine() as export:
            self.assertEqual(0, stl_build.main([str(self.document), "meshes/sample.stl"]))
        self.assertEqual([("stl", Path("meshes/sample.stl"))], export.call_args.args[1])

    def test_a_model_script_is_refused_by_naming_the_run(self):
        stderr = io.StringIO()
        with _engine(), contextlib.redirect_stderr(stderr):
            self.assertEqual(1, stl_build.main(["parts/sample.py"]))
        # The teaching error prints the path in the NATIVE spelling, so that is
        # what a Windows reader can paste back into a shell.
        self.assertIn(f"python {os.path.join('parts', 'sample.py')}", stderr.getvalue())

    def test_tolerances_force_and_verbose_reach_the_engine(self):
        with _engine() as export:
            self.assertEqual(
                0,
                glb_build.main(
                    [
                        str(self.document),
                        "--mesh-tolerance",
                        "0.2",
                        "--mesh-angular-tolerance",
                        "0.25",
                        "--force",
                        "--verbose",
                    ]
                ),
            )
        kwargs = export.call_args.kwargs
        self.assertEqual(0.2, kwargs["mesh_tolerance"])
        self.assertEqual(0.25, kwargs["mesh_angular_tolerance"])
        self.assertTrue(kwargs["force"])
        self.assertTrue(kwargs["verbose"])

    def test_the_defaults_ask_for_nothing_extra(self):
        with _engine() as export:
            self.assertEqual(0, stl_build.main([str(self.document)]))
        kwargs = export.call_args.kwargs
        self.assertIsNone(kwargs["mesh_tolerance"])
        self.assertIsNone(kwargs["mesh_angular_tolerance"])
        self.assertNotIn("kinematics", kwargs)
        self.assertFalse(kwargs["force"])
        self.assertFalse(kwargs["verbose"])

    def test_a_target_is_required(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            stl_build.main([])
        self.assertEqual(2, cm.exception.code)

    def test_a_third_positional_is_rejected(self):
        # A door exports ONE model to ONE destination; `--stl a --3mf b` was the
        # retired export CLI's job and is three commands now.
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            stl_build.main([str(self.document), "b.stl", "c.stl"])
        self.assertEqual(2, cm.exception.code)


class DoorResults(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = root / "sample.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")

    def test_human_lines_distinguish_written_from_current(self):
        payload = {
            "ok": True,
            "files": [
                {
                    "format": "stl",
                    "path": "/abs/draft.stl",
                    "skipped": True,
                    "meshTolerance": 0.008,
                    "meshAngularTolerance": None,
                },
                {
                    "format": "stl",
                    "path": "/abs/print.stl",
                    "skipped": False,
                    "meshTolerance": 0.0004,
                    "meshAngularTolerance": None,
                },
            ],
        }
        out = io.StringIO()
        with _engine(payload), contextlib.redirect_stdout(out):
            self.assertEqual(0, stl_build.main([str(self.document)]))
        self.assertEqual(
            [
                f"current STL: {native('/abs/draft.stl')}",
                f"wrote STL: {native('/abs/print.stl')}",
            ],
            out.getvalue().splitlines(),
        )

    def test_json_carries_the_effective_tolerance_pair(self):
        payload = {
            "ok": True,
            "files": [
                {
                    "format": "3mf",
                    "path": "/abs/sample.3mf",
                    "skipped": False,
                    "meshTolerance": 0.005,
                    "meshAngularTolerance": 0.35,
                }
            ],
        }
        out = io.StringIO()
        with _engine(payload), contextlib.redirect_stdout(out):
            self.assertEqual(0, threemf_build.main([str(self.document), "--json"]))
        self.assertEqual(
            {
                "ok": True,
                "files": [
                    {
                        "path": native("/abs/sample.3mf"),
                        "fmt": "3mf",
                        "skipped": False,
                        "mesh_tolerance": 0.005,
                        "mesh_angular_tolerance": 0.35,
                    }
                ],
            },
            json.loads(out.getvalue()),
        )

    def test_an_engine_error_is_reported_not_raised(self):
        err = io.StringIO()
        with mock.patch(
            "cadgen.step_export_target.export_cad_target",
            side_effect=ValueError("stl OUT must end with .stl: sample.bin"),
        ), contextlib.redirect_stderr(err):
            self.assertEqual(1, stl_build.main([str(self.document), "sample.bin"]))
        self.assertIn("stl OUT must end with .stl", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class DoorImports(unittest.TestCase):
    def test_a_door_module_imports_without_the_cad_stack(self):
        # A door is reached before any freshness gate has run; waking OCP here
        # would cost seconds on a model that turns out to be current.
        for _, module, namespace in DOORS:
            with self.subTest(namespace=namespace):
                code = (
                    f"import sys, {module.__name__}, {namespace};"
                    "print('OCP.OCP' in sys.modules);"
                    "print('cadgen._internal.step_scene' in sys.modules);"
                    "print('common' in sys.modules)"
                )
                proc = subprocess.run(
                    [sys.executable, "-c", code], capture_output=True, text=True
                )
                self.assertEqual("", proc.stderr)
                self.assertEqual(["False", "False", "False"], proc.stdout.split())


if __name__ == "__main__":
    unittest.main()
