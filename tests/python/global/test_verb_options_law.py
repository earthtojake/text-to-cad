"""cadgen's law 22: a verb's option is about the picture or the path, never the model.

`export` converts a document into files: a document in, destinations out. What a file holds
-- its parts, their placement, colours and motion -- is what the code built, so neither the
command, the root function nor a document's handle (`Document.export`, what a model call returns)
takes an option that selects a part or a state. A posed or partial file is a function in the
model's code (`cad.ap242.posed`, a part's own model). This pins the surface where such an option
would come back: the parser `cad export` runs and the Python signatures. The verbs moved from
the decorated function (`Model`) to the handle deliberately: the function is the declaration and
its id; the document a call returns is what a verb reads. Nothing here needs the CAD kernel.
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
from cad_server.cli.export import build_parser  # noqa: E402
from cad.engine.api import Document  # noqa: E402
from cad.engine.model import Model  # noqa: E402

LAW = ("law 22 (packages/cad/README.md): \"A verb's option is about the picture or the path, never the "
       "model. `export` takes a document and destinations: what the file holds, its parts and their "
       "placement, colours and motion, is what the code built, so no option selects a part or a state. "
       "[...] Anything that changes what a document is, is a function in the model's code.\"")


class ExportTakesADocumentAndDestinations(unittest.TestCase):
    def test_the_command_takes_src_dst_and_json_alone(self) -> None:
        parser = build_parser()
        found = {(action.dest, tuple(action.option_strings), action.nargs) for action in parser._actions
                 if not isinstance(action, argparse._HelpAction)}
        self.assertEqual(found, {("source", (), None), ("destinations", (), "+"), ("json", ("--json",), 0)},
                         f"`cad export` takes SRC DST [DST ...] [--json] alone; {LAW}")

    def test_the_function_takes_a_source_destinations_and_its_seams_alone(self) -> None:
        parameters = inspect.signature(cad.export).parameters.values()
        self.assertEqual([(p.name, p.kind, p.default) for p in parameters], [
            ("source", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
            ("destinations", inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.empty),
            ("log", inspect.Parameter.KEYWORD_ONLY, None),
            ("daemon", inspect.Parameter.KEYWORD_ONLY, True),
            ("progress", inspect.Parameter.KEYWORD_ONLY, None),
        ], f"cad.export is (source, *destinations, log=None, daemon=True, progress=None); {LAW}")

    def test_a_handle_exports_its_document_to_destinations_alone(self) -> None:
        parameters = inspect.signature(Document.export).parameters.values()
        self.assertEqual([(p.name, p.kind) for p in parameters], [
            ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ("destinations", inspect.Parameter.VAR_POSITIONAL),
        ], f"Document.export is (*destinations); {LAW}")
        self.assertFalse(hasattr(Model, "export") or hasattr(Model, "snapshot"),
                         "the decorated function declares; the handle a call returns is what a verb reads")


class SnapshotTakesThePictureAlone(unittest.TestCase):
    PICTURE = ("display", "camera", "grid", "pose", "width", "height", "size_profile", "daemon",
               "annotation", "measurements")

    def test_snapshot_refuses_browser_options_before_opening_a_source(self) -> None:
        from cad_server.engine.cli import parser_for
        from cad.engine.snapshot import SnapshotRefused, job_pictures

        for option, value in (("preview", True), ("animation", "swing"), ("fps", 30)):
            with self.subTest(option=option):
                with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
                    cad.snapshot("missing.xbf", "picture.png", **{option: value})
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as refused:
                    parser_for("snapshot").parse_args(["missing.xbf", "picture.png", f"--{option}"])
                self.assertEqual(refused.exception.code, 2)
                with self.assertRaisesRegex(SnapshotRefused, f"has no {option}"):
                    job_pictures({"input": "missing.xbf", option: value, "outputs": ["picture.png"]})

    def test_a_handle_s_snapshot_takes_the_verb_s_picture_options_by_name(self) -> None:
        verb = inspect.signature(cad.snapshot).parameters
        parameters = list(inspect.signature(Document.snapshot).parameters.values())
        self.assertEqual([(p.name, p.kind) for p in parameters[:2]], [
            ("self", inspect.Parameter.POSITIONAL_OR_KEYWORD), ("out", inspect.Parameter.POSITIONAL_OR_KEYWORD)])
        self.assertEqual([(p.name, p.kind, p.default) for p in parameters[2:]],
                         [(name, inspect.Parameter.KEYWORD_ONLY, verb[name].default) for name in self.PICTURE],
                         f"Document.snapshot(out, ...) spells out the snapshot verb's options, each about the picture; {LAW}")
        self.assertEqual(set(verb) - {"source", "out", "job", "progress"}, set(self.PICTURE),
                         "the verb takes no option Document.snapshot leaves out but its job and its progress seam")
        self.assertEqual(inspect.signature(cad.inspect).parameters["progress"].default, None,
                         "inspect's progress is a seam about where the measurement is, never about the model")


if __name__ == "__main__":
    unittest.main()
