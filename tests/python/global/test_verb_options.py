"""The options `export` and `snapshot` take, pinned where one would be added.

`export` takes a document and destinations, an STL's, a 3MF's or a GLB's mesh tolerance and angle, and a
robot description's zero state: the parser `cad <type> export` runs and the Python signatures (`cad.export`,
`Document.export`). `snapshot` takes the picture's options, the same on the verb and on a document's handle.
The verbs moved from the decorated function (`Model`) to the handle deliberately: the function is the
declaration and its id; the document a call returns is what a verb reads. Nothing here needs the CAD kernel.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import inspect
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

import cad  # noqa: E402
import cad.engine.api  # noqa: E402
from cad_server.cli.document_types import build_parser as _build_parser  # noqa: E402


def build_parser():
    """``cad xbf export``'s parser: the engine's export verb, which every type's export takes."""
    return _build_parser("xbf", "export")
from cad.engine.api import Document  # noqa: E402
from cad.engine.model import Model  # noqa: E402


class ExportTakesADocumentAndDestinations(unittest.TestCase):
    def test_the_command_takes_src_dst_its_tolerance_its_angle_its_zero_and_json(self) -> None:
        parser = build_parser()
        found = {(action.dest, tuple(action.option_strings), action.nargs) for action in parser._actions
                 if not isinstance(action, argparse._HelpAction)}
        self.assertEqual(found, {("source", (), None), ("destinations", (), "+"), ("tolerance", ("--tolerance",), None),
                                 ("angle", ("--angle",), None), ("zero", ("--zero",), None), ("json", ("--json",), 0)},
                         "`cad <type> export` takes SRC DST [DST ...] [--tolerance MM] [--angle DEG] [--zero STATE] "
                         "[--json]")

    def test_the_function_takes_a_source_destinations_and_its_seams(self) -> None:
        parameters = inspect.signature(cad.engine.api.export).parameters.values()
        self.assertEqual([(p.name, p.kind, p.default) for p in parameters], [
            ("source", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
            ("destinations", inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.empty),
            ("tolerance", inspect.Parameter.KEYWORD_ONLY, None),
            ("angle", inspect.Parameter.KEYWORD_ONLY, None),
            ("zero", inspect.Parameter.KEYWORD_ONLY, None),
            ("log", inspect.Parameter.KEYWORD_ONLY, None),
            ("daemon", inspect.Parameter.KEYWORD_ONLY, True),
            ("progress", inspect.Parameter.KEYWORD_ONLY, None),
        ], "cad.export is (source, *destinations, tolerance=None, angle=None, zero=None, log=None, daemon=True, "
           "progress=None)")

    def test_a_handle_exports_its_document_to_destinations(self) -> None:
        parameters = inspect.signature(Document.export).parameters.values()
        self.assertEqual([(p.name, p.kind) for p in parameters], [
            ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ("destinations", inspect.Parameter.VAR_POSITIONAL),
            ("tolerance", inspect.Parameter.KEYWORD_ONLY),
            ("angle", inspect.Parameter.KEYWORD_ONLY),
            ("zero", inspect.Parameter.KEYWORD_ONLY),
        ], "Document.export is (*destinations, tolerance=None, angle=None, zero=None)")
        self.assertFalse(hasattr(Model, "export") or hasattr(Model, "snapshot"),
                         "the decorated function declares; the handle a call returns is what a verb reads")


class SnapshotTakesThePicture(unittest.TestCase):
    PICTURE = ("display", "camera", "grid", "preview", "pose", "width", "height", "size_profile", "daemon",
               "annotation", "measurements")

    def test_snapshot_refuses_browser_options_before_opening_a_source(self) -> None:
        from cad_server.engine.cli import parser_for
        from cad.engine.snapshot import SnapshotRefused, job_pictures

        for option, value in (("animation", "swing"), ("fps", 30)):
            with self.subTest(option=option):
                with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
                    cad.engine.api.snapshot("missing.xbf", "picture.png", **{option: value})
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as refused:
                    parser_for("snapshot").parse_args(["missing.xbf", "picture.png", f"--{option}"])
                self.assertEqual(refused.exception.code, 2)
                with self.assertRaisesRegex(SnapshotRefused, f"has no {option}"):
                    job_pictures({"input": "missing.xbf", option: value, "outputs": ["picture.png"]})

    def test_a_handle_s_snapshot_takes_the_verb_s_picture_options_by_name(self) -> None:
        verb = inspect.signature(cad.engine.api.snapshot).parameters
        parameters = list(inspect.signature(Document.snapshot).parameters.values())
        self.assertEqual([(p.name, p.kind) for p in parameters[:2]], [
            ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD), ("out", inspect.Parameter.POSITIONAL_OR_KEYWORD)])
        self.assertEqual([(p.name, p.kind, p.default) for p in parameters[2:]],
                         [(name, inspect.Parameter.KEYWORD_ONLY, verb[name].default) for name in self.PICTURE],
                         "Document.snapshot(out, ...) spells out the snapshot verb's options")
        self.assertEqual(set(verb) - {"source", "out", "job", "progress"}, set(self.PICTURE),
                         "the verb takes no option Document.snapshot leaves out but its job and its progress seam")
        self.assertEqual(inspect.signature(cad.engine.api.inspect).parameters["progress"].default, None,
                         "inspect's progress is a seam about where the measurement is")


if __name__ == "__main__":
    unittest.main()
