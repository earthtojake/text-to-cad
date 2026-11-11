"""A picture the engine cannot draw for want of an OpenGL context (``snapshot.NO_GL``) is drawn by the
calling process where it can draw (``drawable_here``), and the engine's failure stands where it cannot;
any other failure stands either way. A held document's picture is drawn here from an xbf the engine
exported. The engine's refusal is injected: no OpenGL context is made. The faces a picture lacks, which the
mesher left without triangles, are said in one line however many parts have them."""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from cad.engine import api, snapshot

ID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PNG = b"\x89PNG\r\n\x1a\nnot drawn by OCCT"


def _report() -> dict:
    return {"width": 8, "height": 6, "displayMode": "solid", "preview": False, "timings": {}}


def _no_gl(**extra: object) -> dict:
    return {"failed": "Unavailable: no X display for OpenGL", "type": snapshot.NO_GL, **extra}


class NoOpenGlInTheEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cad-snapshot-no-gl-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.document = self.folder / "robot.stl"
        self.document.write_bytes(b"")  # never read: the engine answers, and this process's drawing is injected
        self.out = self.folder / "robot.png"

    def picture(self, answer: dict, here: str | None) -> tuple[mock.Mock, str]:
        drawn = mock.Mock(return_value=(PNG, _report()))
        said = io.StringIO()
        with mock.patch("cad.engine.client.request", return_value=answer), \
                mock.patch.object(snapshot, "drawable_here", return_value=here), \
                mock.patch("cad.engine.render.service.draw_here", drawn), redirect_stderr(said):
            snapshot.snapshot(self.document, self.out)
        return drawn, said.getvalue()

    def test_a_file_the_engine_cannot_draw_is_drawn_here_where_this_process_can(self) -> None:
        drawn, said = self.picture(_no_gl(), None)
        drawn.assert_called_once()
        self.assertEqual(self.document, drawn.call_args.args[0])
        self.assertEqual(PNG, self.out.read_bytes())
        self.assertIn("this process draws the picture instead", said)

    def test_the_engine_s_failure_stands_where_this_process_cannot_draw(self) -> None:
        with self.assertRaises(api.EngineError) as caught:
            self.picture(_no_gl(), "no X display for OpenGL")
        self.assertTrue(snapshot.no_gl(caught.exception))
        self.assertFalse(self.out.exists())

    def test_any_other_failure_stands_and_asks_nothing_of_this_process(self) -> None:
        here = mock.Mock(return_value=None)
        with mock.patch("cad.engine.client.request", return_value={"failed": "MemoryError: out", "type": "MemoryError"}), \
                mock.patch.object(snapshot, "drawable_here", here), self.assertRaises(api.EngineError):
            snapshot.snapshot(self.document, self.out)
        here.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_a_held_document_is_exported_by_the_engine_and_drawn_here(self) -> None:
        def exported(source: str, out: Path, **_options: object) -> None:
            self.assertEqual(ID, source)
            Path(out).write_bytes(b"xbf")  # never read: this process's drawing is injected

        for name, draw in (("snapshot", lambda: api.snapshot(ID, self.out)),
                           ("a job's picture", lambda: snapshot._occt(Path(ID), self.out, snapshot.Still(size=(8, 6)), True, None,
                                                                         0.0))):
            with self.subTest(name):
                self.out.unlink(missing_ok=True)
                drawn = mock.Mock(return_value=(PNG, _report()))
                with mock.patch.object(api, "_exported", side_effect=api._failed(_no_gl())), \
                        mock.patch.object(api, "export", side_effect=exported) as export, \
                        mock.patch.object(snapshot, "drawable_here", return_value=None), \
                        mock.patch("cad.engine.render.service.draw_here", drawn), redirect_stderr(io.StringIO()):
                    found = draw()
                export.assert_called_once()
                self.assertEqual(".xbf", drawn.call_args.args[0].suffix)
                self.assertEqual(ID, (found.report if isinstance(found, api.Drawn) else found)["document"])
                self.assertEqual(PNG, self.out.read_bytes())

if __name__ == "__main__":
    unittest.main()


class UnmeshedFaces(unittest.TestCase):
    def test_the_faces_the_mesher_left_are_one_warning_naming_the_first_parts(self) -> None:
        said = io.StringIO()
        with redirect_stderr(said):
            snapshot._warn({"SOLID": [6, 74], "screw:1": [1], "screw:2": [1], "Wrist": [91], "nut": [3]})
            snapshot._warn({})
        self.assertEqual(said.getvalue().splitlines(), [
            "warning: the mesher left 6 faces of 5 parts without triangles, so the picture does not draw them: "
            "SOLID (6, 74); screw:1 (1); screw:2 (1); Wrist (91); and 1 more part"])
