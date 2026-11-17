"""A GSL model's ``field`` (``GET /api/v1/documents/gsl/<id>/field`` and ``.../field/textures/<name>``) against
a real launched server, and the route's rules (``cad_server.viewer.fields``).

A model is opened by its absolute path, as every file is. Its field is what the page draws it from: a shader
library omega's ``gsl`` writes of it (stood in for here, except in ``Shades``, which runs a ``gsl`` that has the
question), kept by the model's bytes and the bytes of what it imports, so an edit saved under the same path is
the next answer's new key and the same bytes are answered without asking ``gsl`` again. Every model is written
fresh into a temporary folder; the cache is the test's own (``CAD_CACHE_DIR``).
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cad_server.viewer import handler as handler_module
from cad_server.viewer.compressed import Coded
from cad_server.viewer.fields import FieldAnswers
from cad_server.viewer.http_app import create_cad_app

BALL = "@scene(40)\nr = 8.0;\nr.min = 2.0;\nr.max = 15.0;\nball = length(p) - r;\nreturn ball;\n"
NOISE = bytes(range(256)) * 16


class Shader:
    """omega's ``gsl`` stood in for: an answer in the shape ``gsl eval``'s ``shader`` gives, with a texture written
    beside it, or a refusal in gsl's words."""

    def __init__(self, refuses: str = "") -> None:
        self.calls, self.refuses = 0, refuses

    def __call__(self, model: Path, out_dir: Path) -> dict:
        from cad.omega._shader import ShaderRefused

        self.calls += 1
        if self.refuses:
            raise ShaderRefused(self.refuses)
        (out_dir / "noiseTex.bin").write_bytes(NOISE)
        text = model.read_text(encoding="utf-8")
        return {"target": "glsl-es300", "code": f"// {len(text)} bytes of GSL\nfloat gsl_field_stub;\n",
                "entry": {"field": "gsl_field", "march": "gsl_march"}, "uniformBlock": "gsl_Host_block_0Fragment",
                "blockBytes": 16, "uniforms": [{"name": "time", "type": "f32", "offset": 0, "value": [0]}],
                "sliders": [{"name": "r", "uniform": "gsl_param_2_5", "type": "f32", "offset": 4, "value": 8,
                             "min": 2, "max": 15}],
                "textures": [{"uniform": "_group_0_binding_1_fs", "kind": "noise3d", "format": "rgba8unorm",
                              "filter": "nearest", "size": [16, 16, 4], "file": "noiseTex.bin"}],
                "bodies": [{"name": "ball", "index": 1}], "region": [-20, -20, -20, 20, 20, 20]}


class FieldRules(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.model = self.folder / "ball.gsl"
        self.model.write_text(BALL, encoding="utf-8")
        cache = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def answered(self, answers: FieldAnswers, **options):
        status, body, key = answers.response(str(self.model), **options)
        return status, json.loads(body.data) if isinstance(body, Coded) else body, key

    def test_the_field_is_what_gsl_wrote_of_the_model_and_is_kept_by_its_bytes(self) -> None:
        shader = Shader()
        answers = FieldAnswers(shader=shader, hold_seconds=30)
        status, field, key = self.answered(answers)
        self.assertEqual(status, 200, field)
        self.assertRegex(key, r"^[0-9a-f]{64}$")
        self.assertEqual((field["schema"], field["key"], field["target"]), (1, key, "glsl-es300"))
        self.assertEqual(field["entry"], {"field": "gsl_field", "march": "gsl_march"})
        self.assertEqual(field["sliders"][0]["name"], "r")
        # A texture is named, never a path on this computer: the page reads it from the route beside this one.
        self.assertEqual(field["textures"], [{"uniform": "_group_0_binding_1_fs", "kind": "noise3d",
                                              "format": "rgba8unorm", "filter": "nearest", "size": [16, 16, 4],
                                              "name": "noiseTex.bin"}])
        # The same bytes are the same answer, gsl not asked again: in this engine, and in the next one.
        self.assertEqual(self.answered(answers)[2], key)
        self.assertEqual(self.answered(FieldAnswers(shader=shader, hold_seconds=30))[1], field)
        self.assertEqual(shader.calls, 1)
        # An edit is another key and another answer.
        self.model.write_text(BALL.replace("8.0", "9.0"), encoding="utf-8")
        status, edited, other = self.answered(answers)
        self.assertEqual(status, 200)
        self.assertNotEqual(other, key)
        self.assertEqual(shader.calls, 2)

    def test_a_request_naming_the_key_it_has_is_answered_304(self) -> None:
        answers = FieldAnswers(shader=Shader(), hold_seconds=30)
        _, _, key = self.answered(answers)
        self.assertEqual(self.answered(answers, if_none_match=f'"{key}"')[0], 304)
        self.assertEqual(self.answered(answers, if_none_match='"another"')[0], 200)

    def test_a_field_that_takes_longer_than_the_hold_is_answered_202_and_then_as_made(self) -> None:
        release = threading.Event()
        inner = Shader()

        def slow(model: Path, out_dir: Path) -> dict:
            release.wait(30)
            return inner(model, out_dir)

        answers = FieldAnswers(shader=slow, hold_seconds=0.05, retry_ms=250)
        status, body, key = self.answered(answers)
        self.assertEqual((status, body), (202, {"state": "compiling", "retryMs": 250}))
        self.assertEqual(self.answered(answers)[0], 202)  # the same work, joined
        release.set()
        answers.hold_seconds = 30
        status, field, again = self.answered(answers)
        self.assertEqual((status, again), (200, key))
        self.assertEqual(inner.calls, 1)

    def test_a_model_gsl_refuses_is_a_400_in_gsl_s_words_kept_until_the_model_changes(self) -> None:
        shader = Shader(refuses="3:8: undefined identifier: nothing_named_this")
        answers = FieldAnswers(shader=shader, hold_seconds=30)
        status, body, key = self.answered(answers)
        self.assertEqual(status, 400)
        self.assertIn("nothing_named_this", body["error"])
        self.assertEqual(self.answered(answers)[0], 400)
        self.assertEqual(shader.calls, 1)

    def test_a_bug_is_a_400_that_is_not_kept_and_is_reported(self) -> None:
        crashes: list[BaseException] = []

        def broken(model: Path, out_dir: Path) -> dict:
            raise KeyError("region")

        answers = FieldAnswers(shader=broken, hold_seconds=30, on_crash=crashes.append)
        self.assertEqual(self.answered(answers)[0], 400)
        self.assertEqual(self.answered(answers)[0], 400)
        self.assertEqual(len(crashes), 2)

    def test_a_texture_is_the_file_gsl_wrote_for_this_key_and_no_other_name_is_read(self) -> None:
        answers = FieldAnswers(shader=Shader(), hold_seconds=30)
        self.assertIsNone(answers.texture(str(self.model), "noiseTex.bin"), "nothing before the field is made")
        self.answered(answers)
        found = answers.texture(str(self.model), "noiseTex.bin")
        self.assertIsNotNone(found)
        self.assertEqual(Path(found).read_bytes(), NOISE)
        for name in ("other.bin", "../payload.json", "payload.json", "", "noiseTex.bin/..", "/etc/hosts"):
            self.assertIsNone(answers.texture(str(self.model), name), name)

    def test_a_file_that_is_no_gsl_and_one_that_is_gone_are_refused(self) -> None:
        answers = FieldAnswers(shader=Shader(), hold_seconds=30)
        other = self.folder / "part.stl"
        other.write_bytes(b"solid")
        with self.assertRaisesRegex(ValueError, "a .gsl's"):
            answers.response(str(other))
        self.assertEqual(answers.response(str(self.folder / "gone.gsl"))[0], 404)


class FieldRoute(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.model = self.folder / "ball.gsl"
        self.model.write_text(BALL, encoding="utf-8")
        cache = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)
        app = create_cad_app(host="127.0.0.1", port=0, dist_dir="")
        self.shader = Shader()
        app.fields = FieldAnswers(shader=self.shader, hold_seconds=30)
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

    def opened(self) -> str:
        status, _, body = self.request("POST", "/api/v1/documents", {"path": str(self.model)})
        self.assertEqual(status, 201, body[:400])
        reply = json.loads(body)
        self.assertEqual(reply["kind"], "gsl")
        return reply["api"]

    def test_a_gsl_model_opens_as_a_document_whose_field_and_source_are_read(self) -> None:
        api = self.opened()
        status, headers, body = self.request("GET", f"{api}/field")
        self.assertEqual(status, 200, body[:400])
        field = json.loads(body)
        self.assertEqual(headers.get("etag"), f'"{field["key"]}"')
        self.assertIn("gsl_field_stub", field["code"])
        self.assertEqual(self.request("GET", f"{api}/field", headers={"if-none-match": headers["etag"]})[0], 304)
        status, _, source = self.request("GET", f"{api}/source")
        self.assertEqual((status, source.decode()), (200, BALL))

    def test_a_texture_is_read_as_bytes_beside_the_field_and_another_name_is_a_404(self) -> None:
        api = self.opened()
        field = json.loads(self.request("GET", f"{api}/field")[2])
        name = field["textures"][0]["name"]
        status, headers, body = self.request("GET", f"{api}/field/textures/{name}")
        self.assertEqual((status, body), (200, NOISE))
        self.assertEqual(headers.get("content-type"), "application/octet-stream")
        self.assertEqual(self.request("GET", f"{api}/field/textures/payload.json")[0], 404)
        self.assertEqual(self.request("GET", f"{api}/field/textures/..%2Fpayload.json")[0], 404)

    def test_a_refused_model_is_a_400_that_says_why_and_how(self) -> None:
        self.shader.refuses = "3:8: undefined identifier: nothing_named_this"
        status, _, body = self.request("GET", f"{self.opened()}/field")
        self.assertEqual(status, 400)
        reply = json.loads(body)
        self.assertIn("nothing_named_this", reply["error"])
        self.assertTrue(reply.get("hint"))

    def test_the_kind_says_what_it_answers_and_another_route_names_them(self) -> None:
        status, _, body = self.request("GET", f"{self.opened()}/plot")
        self.assertEqual(status, 404)
        self.assertIn("field", json.loads(body).get("hint", "") + json.loads(body).get("error", ""))


HAS_OMEGA = importlib.util.find_spec("omega_core") is not None


def _gsl_shades() -> bool:
    """Whether the ``gsl`` cad would run answers ``eval``'s ``shader``: asked once, of a request it must refuse."""
    if not HAS_OMEGA:
        return False
    try:
        import omega_core

        from cad.omega._program import find_gsl

        with omega_core.Session(program=str(find_gsl())) as session:
            try:
                session.request({"op": "shader", "code": "return 1.0;"})
            except omega_core.EvalError as error:
                return "target" in str(error)
    except Exception:  # noqa: BLE001 - no gsl to ask is no gsl that shades
        return False
    return False


@unittest.skipUnless(_gsl_shades(), "needs a gsl whose eval has shader (omega-core 0.1.2 or later: set CAD_GSL)")
class Shades(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def test_gsl_writes_a_glsl_library_its_block_and_its_sliders_of_a_model(self) -> None:
        from cad.omega._shader import payload

        model = self.folder / "ball.gsl"
        model.write_text(BALL, encoding="utf-8")
        out = self.folder / "out"
        out.mkdir()
        found = payload(model, out)
        self.assertEqual(found["target"], "glsl-es300")
        self.assertIn("gsl_march(", found["code"])
        self.assertNotIn("#version", found["code"])
        self.assertEqual([(s["name"], s["value"], s["min"], s["max"], s["offset"]) for s in found["sliders"]],
                         [("r", 8, 2, 15, 4)])
        self.assertEqual(found["region"], [-20, -20, -20, 20, 20, 20])
        self.assertEqual(found["textures"], [])

    def test_a_model_gsl_refuses_is_refused_in_its_words(self) -> None:
        from cad.omega._shader import ShaderRefused, payload

        model = self.folder / "broken.gsl"
        model.write_text("@scene(40)\nreturn nothing_named_this(p);\n", encoding="utf-8")
        with self.assertRaisesRegex(ShaderRefused, "nothing_named_this"):
            payload(model, self.folder)


@unittest.skipUnless(HAS_OMEGA, "needs omega-core (cad[omega]: macOS and Linux)")
class OlderGsl(unittest.TestCase):
    def test_a_gsl_with_no_shader_is_refused_with_what_to_do(self) -> None:
        import omega_core

        from cad.omega import _shader

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(_shader, "_asked", side_effect=omega_core.EvalError(
                    'op "shader": one of eval, extremum, certify, bounds, surface, volume, describe or render')):
            model = Path(folder) / "ball.gsl"
            model.write_text(BALL, encoding="utf-8")
            with self.assertRaisesRegex(_shader.ShaderRefused, "CAD_GSL"):
                _shader.payload(model, Path(folder))


if __name__ == "__main__":
    unittest.main()
