"""An OpenSCAD program's ``mesh`` (``GET /api/v1/documents/scad/<id>/mesh``) against a real launched server, and
the route's rules (``cad_server.viewer.scads``).

A program is opened by its absolute path, as every file is. Its mesh is the binary STL OpenSCAD renders of it
(the stand-in OpenSCAD here, ``tests/python/support/openscad_stub``; the real one in the openscad suite),
kept by the program's bytes and its includes', so an edit saved under the same path is the next answer's new
key, and the same bytes are answered without rendering again; its ``source`` stays the program's text. The
cache is the test file's own (``CAD_CACHE_DIR``).
"""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import openscad_stub

from cad.openscad._program import OpenscadMissing
from cad.openscad._render import ProgramRefused, RenderUnavailable
from cad_server.viewer import handler as handler_module
from cad_server.viewer import scads as route
from cad_server.viewer.http_app import _KIND_ROUTES, create_cad_app
from cad_server.viewer.kinds import EXPORTS, RENDERED_KINDS
from cad_server.viewer.scads import ScadAnswers


class Render:
    """OpenSCAD's render stood in for: a mesh file named for the program's bytes, or a failure."""

    def __init__(self, fails: Exception | None = None, hold: threading.Event | None = None) -> None:
        self.calls, self.fails, self.hold = 0, fails, hold

    def __call__(self, program: Path) -> tuple[Path, str]:
        self.calls += 1
        if self.hold is not None:
            self.hold.wait(10)
        if self.fails is not None:
            raise self.fails
        key = program.read_text(encoding="utf-8").strip().replace(" ", "-")
        mesh = program.parent / "kept" / key / "mesh.stl"
        mesh.parent.mkdir(parents=True, exist_ok=True)
        mesh.write_bytes(b"OpenSCAD Model".ljust(80, b"\0") + (0).to_bytes(4, "little") + key.encode())
        return mesh, key


class MeshRules(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tmp-scad-route-")
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name).resolve()
        self.program = self.folder / "part.scad"
        self.program.write_text("cube(10);\n", encoding="utf-8")
        cache = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def answers(self, **options) -> ScadAnswers:
        return ScadAnswers(version=lambda: "2021.01", **options)

    def test_the_mesh_is_rendered_once_per_bytes_and_kept(self) -> None:
        render = Render()
        answers = self.answers(render=render)
        status, body, key = answers.response(str(self.program))
        self.assertEqual((status, key), (200, "cube(10);"))
        self.assertEqual(body, self.folder / "kept" / "cube(10);" / "mesh.stl")
        self.assertEqual(answers.response(str(self.program)), (200, body, key))
        self.assertEqual(render.calls, 1)
        self.assertEqual(answers.response(str(self.program), if_none_match=f'"{key}"')[0], 304)
        # An edit is a new key: rendered again, the old answer never served.
        self.program.write_text("cube(20);\n", encoding="utf-8")
        status, changed, other = answers.response(str(self.program))
        self.assertEqual((status, render.calls), (200, 2))
        self.assertNotEqual((changed, other), (body, key))

    def test_a_rendered_mesh_is_a_mesh_view_the_server_renders_worked_out_from_the_registry(self) -> None:
        self.assertEqual(RENDERED_KINDS, frozenset({"scad"}))
        self.assertEqual((_KIND_ROUTES["scad"], _KIND_ROUTES["stl"], EXPORTS["scad"]), ("mesh, source", "source", []))

    def test_a_held_mesh_that_is_gone_is_rendered_again_never_a_404(self) -> None:
        render = Render()
        answers = self.answers(render=render)
        status, mesh, key = answers.response(str(self.program))
        self.assertEqual(status, 200)
        mesh.unlink()  # cad delete, a cleared cache
        status, again, other = answers.response(str(self.program))
        self.assertEqual((status, again, other, render.calls), (200, mesh, key, 2))
        self.assertTrue(again.is_file())

    def test_the_programs_own_fault_is_held_and_openscads_is_not(self) -> None:
        refused = Render(fails=ProgramRefused("OpenSCAD could not render part.scad (exit 1): ERROR: Parser error"))
        answers = self.answers(render=refused)
        status, body, _key = answers.response(str(self.program))
        self.assertEqual((status, body["error"]), (400, "OpenSCAD could not render part.scad (exit 1): ERROR: Parser error"))
        answers.response(str(self.program))
        self.assertEqual(refused.calls, 1, "the same program fails the same way: held until it changes")
        self.program.write_text("cube(11);\n", encoding="utf-8")
        answers.response(str(self.program))
        self.assertEqual(refused.calls, 2, "an edit is asked again")
        unavailable = Render(fails=RenderUnavailable("OpenSCAD did not finish rendering part.scad in 900 s"))
        answers = self.answers(render=unavailable)
        status, body, _key = answers.response(str(self.program))
        self.assertEqual((status, body["hint"]), (503, route._AGAIN))
        answers.response(str(self.program))
        self.assertEqual(unavailable.calls, 2, "not the program's fault: asked again")

    def test_the_keys_remembered_are_bounded_and_their_includes_stat_without_the_record(self) -> None:
        answers = self.answers(render=Render())
        for at in range(route.HELD + 5):
            program = self.folder / f"p{at}.scad"
            program.write_text(f"cube({at});\n", encoding="utf-8")
            answers.response(str(program))
        self.assertLessEqual(len(answers._keys), route.HELD)  # noqa: SLF001
        self.assertLessEqual(len(answers._held), route.HELD)  # noqa: SLF001
        key = answers.key(str(self.program))
        with mock.patch("cad_server._internal.scads.includes", side_effect=AssertionError("the record is read once")):
            self.assertEqual(answers.key(str(self.program)), key)

    def test_a_render_that_takes_longer_than_the_hold_is_asked_again(self) -> None:
        release = threading.Event()
        answers = self.answers(render=Render(hold=release), hold_seconds=0, retry_ms=250)
        self.assertEqual(answers.response(str(self.program))[:2], (202, {"state": "rendering", "retryMs": 250}))
        release.set()
        answers.hold_seconds = 10
        self.assertEqual(answers.response(str(self.program))[0], 200)

    def test_what_the_route_will_not_take_and_how_openscad_fails(self) -> None:
        answers = self.answers(render=Render())
        self.assertEqual(answers.response(str(self.folder / "other.scad")), (404, {"error": "Not found"}, ""))
        for ref, message in (("", "absolute path of a .scad"), ("part.scad", "absolute"),
                             (str(self.folder / "part.step"), r"part\.step is not one")):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                answers.response(ref)
        missing = Render(fails=OpenscadMissing("openscad was not found: install OpenSCAD 2021.01 or newer"))
        without = self.answers(render=missing)
        status, body, _key = without.response(str(self.program))
        self.assertEqual((status, body["hint"]), (503, "install OpenSCAD, then open the program again"))
        self.assertIn("install OpenSCAD 2021.01", body["error"])
        without.response(str(self.program))
        self.assertEqual(missing.calls, 2, "not kept: installing OpenSCAD is enough")
        # No OpenSCAD to ask a version of: said at once, nothing rendered.
        def no_openscad():
            raise OpenscadMissing("openscad was not found: install OpenSCAD 2021.01 or newer")
        status, body, key = ScadAnswers(render=Render(), version=no_openscad).response(str(self.program))
        self.assertEqual((status, key), (503, ""))
        self.assertIn("install OpenSCAD 2021.01", body["error"])

    @unittest.skipUnless(openscad_stub.RUNS, "the stand-in OpenSCAD is a shebang script, which Windows does not run")
    def test_the_engine_keeps_the_stubs_render_by_the_program_and_its_includes(self) -> None:
        from cad_server._internal import scads

        stub = openscad_stub.write_stub(self.folder / "bin")
        (self.folder / "lib.scad").write_text("module post() {}\n", encoding="utf-8")
        self.program.write_text("include <lib.scad>\ncube([20, 10, 5]);\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(stub)}):
            answers = ScadAnswers()
            status, mesh, key = answers.response(str(self.program))
            self.assertEqual(status, 200)
            self.assertEqual(mesh, scads.folder(self.program) / key / scads.MESH)
            self.assertEqual(scads.includes(self.program), [self.folder / "lib.scad"], "the includes recorded")
            stamp = mesh.stat().st_mtime_ns
            self.assertEqual(ScadAnswers().response(str(self.program)), (200, mesh, key), "a new engine: from disk")
            self.assertEqual(mesh.stat().st_mtime_ns, stamp, "not rendered again")
            # An edit to the LIBRARY alone is a new key: the program's bytes did not change, its include's did.
            (self.folder / "lib.scad").write_text("module post() { cube(1); }\n", encoding="utf-8")
            status, other, changed = answers.response(str(self.program))
            self.assertEqual(status, 200)
            self.assertNotEqual(changed, key)
            self.assertEqual(sorted(path.name for path in scads.folder(self.program).iterdir()),
                             sorted([key, changed, scads.INCLUDES]))
            # The program by another spelling of its path -- through a symlinked folder -- is the same program:
            # the same folder, the same key, and the kept mesh, not a render.
            link = self.folder / "link"
            link.symlink_to(self.folder, target_is_directory=True)
            spelled = link / "part.scad"
            self.assertEqual(scads.folder(spelled), scads.folder(self.program))
            stamp = other.stat().st_mtime_ns
            self.assertEqual(scads.rendered(spelled, "2021.01"), (other, changed))
            self.assertEqual(other.stat().st_mtime_ns, stamp, "not rendered again")
            self.assertEqual(ScadAnswers().response(str(spelled))[1:], (other, changed))


@unittest.skipUnless(openscad_stub.RUNS, "the stand-in OpenSCAD is a shebang script, which Windows does not run")
class MeshRoute(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tmp-scad-route-")
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name).resolve()
        self.program = self.folder / "part.scad"
        self.program.write_text("cube([20, 10, 5]);\n", encoding="utf-8")
        stub = openscad_stub.write_stub(self.folder / "bin")
        patched = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache"), "CAD_OPENSCAD": str(stub)})
        patched.start()
        self.addCleanup(patched.stop)
        app = create_cad_app(host="127.0.0.1", port=0, dist_dir="")
        app.scads = ScadAnswers(hold_seconds=30)
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        app.port = self.port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, method: str, target: str, body: dict | None = None, headers: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request(method, target, body=None if body is None else json.dumps(body).encode(),
                         headers={**({"x-cad-viewer": "1"} if method == "POST" else {}), **(headers or {})})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_a_program_opened_by_its_path_answers_its_mesh_and_its_source(self) -> None:
        status, _, body = self.request("POST", "/api/v1/documents", {"path": str(self.program)})
        self.assertEqual(status, 201, body[:400])
        reply = json.loads(body)
        self.assertEqual(reply["kind"], "scad")
        api = reply["api"]
        status, headers, mesh = self.request("GET", f"{api}/mesh")
        self.assertEqual(status, 200, mesh[:400])
        self.assertEqual(headers["content-type"], "model/stl")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual((mesh[:14], len(mesh)), (b"OpenSCAD Model", 84 + 12 * 50))
        tag = headers["etag"]
        self.assertEqual(self.request("GET", f"{api}/mesh", headers={"if-none-match": tag})[0], 304)
        status, head_headers, nothing = self.request("HEAD", f"{api}/mesh")
        self.assertEqual((status, head_headers["etag"], nothing), (200, tag, b""))
        status, headers, source = self.request("GET", f"{api}/source")
        self.assertEqual((status, headers["content-type"], source), (200, "text/plain; charset=utf-8", b"cube([20, 10, 5]);\n"))
        status, _, body = self.request("GET", f"{api}/plot")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["hint"], "a scad's routes are mesh, source")
        # Saved under the same path: the next read's new key.
        self.program.write_text("cube([2, 2, 2]);\n", encoding="utf-8")
        status, headers, _ = self.request("GET", f"{api}/mesh")
        self.assertEqual(status, 200)
        self.assertNotEqual(headers["etag"], tag)


if __name__ == "__main__":
    unittest.main()
