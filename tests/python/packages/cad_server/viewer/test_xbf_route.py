"""An engine document opened (``POST /api/v1/documents``) against a real launched viewer and an
engine daemon of this test's own: an ``.xbf`` and a STEP are served by the cadgen engine -- the
route asks the engine's daemon, which reads a STEP in a reader process of its own -- and the page
reads them through its kind's routes (``/api/v1/documents/<kind>/<id>/...``), never from the
engine's own vocabulary: what the CAD app's tunnel carries too. A STEP's names, colours and
materials are the engine's reading of it, and the same STEP opened again (or touched) is not
parsed again while the daemon lives. A request that names no engine document is refused in words.

The models are written into a fresh temporary folder and built there; nothing reads the sample
corpus.
"""

from __future__ import annotations

import base64
import gzip
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.scanner import catalog_entry
from cad_server.viewer.documents import EngineDocuments
from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

MODEL = """
import build123d as bd
from cad.engine import step, xbf
from bd_materials import metals


@xbf("XBF/block.xbf")
def block():
    return bd.Box(10, 6, 4) - bd.Cylinder(1, 10)


@xbf("XBF/pair.xbf")
@step(out="pair.step")
def pair():
    plate = bd.Box(10, 6, 4) - bd.Cylinder(1, 10)
    plate.label, plate.color = "plate", bd.Color(0.8, 0.1, 0.1)
    peg = bd.Pos(8, 0, 4) * bd.Cylinder(1, 6)
    peg.label, peg.material = "peg", metals.aluminum()
    return bd.Compound(children=[plate, peg], label="pair")

if __name__ == "__main__":
    block()
    pair()
"""

# A model with no file of its own, which an export writes as an xbf.
TRIO = """
import build123d as bd
from cad import model


@model
def trio():
    return bd.Compound(children=[bd.Pos(20 * at, 0, 0) * bd.Box(5, 5, 5) for at in range(3)], label="trio")

if __name__ == "__main__":
    trio()
"""


# A model whose build saves it as the .xbf beside its script.
ARM = """
import build123d as bd
from cad.engine import xbf


@xbf("arm.xbf")
def arm():
    return bd.Box(4, 4, 20)

if __name__ == "__main__":
    arm()
"""


# A model with no file of its own, which the person exports as an xbf.
HUB = """
import build123d as bd
from cad import model


@model
def hub():
    return bd.Compound(children=[bd.Box(6, 6, 2), bd.Pos(0, 0, 4) * bd.Cylinder(2, 6)], label="hub")

if __name__ == "__main__":
    hub()
"""


class XbfRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="viewer-xbf-")))
        cls.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.saved = {name: os.environ.get(name) for name in ("CAD_ENGINE_DIR", "CAD_ENGINE_MESH")}
        # The daemon this test starts is its own: its own socket folder, one part meshed at a time.
        os.environ.update({"CAD_ENGINE_DIR": str(cls.state), "CAD_ENGINE_MESH": "inline"})
        (cls.base / "models.py").write_text(textwrap.dedent(MODEL), encoding="utf-8")
        env = cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC)}, cls.addClassCleanup)
        # Built as a script runs: through this test's own engine daemon.
        done = engine_daemon.run([sys.executable, "models.py"], cwd=cls.base, env=env)
        assert done.returncode == 0, done.stderr
        cls.document = cls.base / "XBF" / "block.xbf"
        cls.step = cls.base / "pair.step"
        assert cls.step.is_file(), done.stdout + done.stderr
        from cad.engine.client import request
        launched = request({"op": "viewer", "api_only": True, "start": str(cls.base)})
        assert launched and "failed" not in launched, launched
        cls.port, cls.token = launched["port"], launched["token"]

    @classmethod
    def tearDownClass(cls) -> None:
        subprocess.run([sys.executable, "-m", "cad_server.engine", "stop"], env={**os.environ, "PYTHONPATH": str(SRC)},
                       capture_output=True, timeout=120)
        deadline = time.monotonic() + 20
        while any(cls.state.glob("*.door")) and time.monotonic() < deadline:
            time.sleep(0.05)
        for name, value in cls.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(cls.base, ignore_errors=True)
        shutil.rmtree(cls.state, ignore_errors=True)

    def test_request_process_never_imports_kernel(self):
        code = r"""
import http.client, json, sys
from urllib.parse import quote
from cad_server._internal.engine_host import http_factory
from cad.engine.serve import Server
server = Server(isolated=True, mesh_mode='inline', http_factory=http_factory)
server.start()
try:
    token = server.http.app.token
    def ask(path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.port, timeout=90)
        connection.request('POST' if body is not None else 'GET', path, body=body,
                           headers={'Authorization': 'Bearer '+token, 'x-cad-viewer': '1'})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data
    def get(path, body=None, status=200):
        answered, data = ask(path, body)
        assert answered == status, (path, answered, data)
        return data
    # Every document route a page reads, of an xbf and of a STEP, opened as the page opens them.
    for document_path in sys.argv[1:]:
        while True:
            status, data = ask('/api/v1/documents', json.dumps({'path': document_path}).encode())
            opened = json.loads(data)
            if status != 202:
                break
        assert status == 201, opened
        api = opened['api']
        document = json.loads(get(api+'/structure'))
        part = api+'/parts/'+document['prototypes'][0]['key']
        for tail in ('', '/faces/1', '/edges/1', '/vertices/1', '/groups', '/volume'):
            get(part+tail)
        get(api+'/measure')
        get(api+'/kinematics', status=404)  # no joints
        get('/api/v1/documents/'+opened['id']+'/version?after='+quote(document['version'])+'&wait=0')
        get(api+'/mesh', b'')
        get(api+'/pose', b'{"pose":{}}', status=400)
        get(api+'/source')
    get('/api/v1/server')
    assert not any(n == 'OCP' or n.startswith('OCP.') or n == 'build123d'
                   or n.startswith('build123d.') for n in sys.modules), sorted(sys.modules)
finally:
    server.stop()
"""
        done = subprocess.run([sys.executable, '-c', code, str(self.document), str(self.step)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def request(self, target: str, headers: dict | None = None) -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        try:
            connection.request("GET", target, headers={"Authorization": "Bearer " + self.token, **(headers or {})})
            response = connection.getresponse()
            return response.status, {name.lower(): value for name, value in response.getheaders()}, response.read()
        finally:
            connection.close()

    def get(self, target: str) -> tuple[int, dict]:
        status, _, body = self.request(target)
        return status, json.loads(body)

    def post(self, target: str, payload: dict) -> tuple[int, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        try:
            connection.request("POST", target, body=json.dumps(payload).encode(),
                               headers={"Authorization": "Bearer " + self.token, "x-cad-viewer": "1"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def answer(self, path: Path) -> tuple[int, dict]:
        """The page's open: ``POST /api/v1/documents``, asked again while the engine reads the file."""
        deadline = time.monotonic() + 300
        while True:
            status, answer = self.post("/api/v1/documents", {"path": str(path)})
            if status != 202:
                return status, answer
            self.assertEqual(answer["state"], "reading")
            self.assertLess(time.monotonic(), deadline, "the engine never finished reading the document")

    def open(self, path: Path) -> dict:
        status, answer = self.answer(path)
        self.assertEqual(status, 201, answer)
        return answer

    def structure(self, served: dict) -> dict:
        status, structure = self.get(served["api"] + "/structure")
        self.assertEqual(status, 200, structure)
        return structure

    def held(self, path: Path) -> bool:
        status, answer = self.get(f"/api/v1/documents?path={quote(str(path), safe='')}")
        self.assertEqual(status, 200, answer)
        return answer["documents"][0]["held"]

    def test_an_xbf_is_served_by_the_engine_and_read_through_the_viewer(self) -> None:
        self.assertEqual(catalog_entry(str(self.document))["kind"], "xbf")
        served = self.open(self.document)
        self.assertEqual(served, {"id": served["id"], "kind": "xbf", "api": f"/api/v1/documents/xbf/{served['id']}"})
        # Its envelope says what it is and where its reads are.
        status, envelope = self.get(f"/api/v1/documents/{served['id']}")
        self.assertEqual((status, envelope["kind"], envelope["api"], envelope["held"]), (200, "xbf", served["api"], True))
        # The structure, a part and the look, all under the viewer's origin: a page from it reads
        # them as its own (the engine's loopback-only answer is never relayed to it).
        status, headers, body = self.request(served["api"] + "/structure", {"Origin": "http://example.test"})
        self.assertEqual(status, 200)
        self.assertFalse([name for name in headers if name.startswith("access-control")], headers)
        structure = json.loads(body)
        self.assertEqual((structure["name"], len(structure["prototypes"])), ("block", 1))
        status, headers, part = self.request(f"{served['api']}/parts/{quote(structure['prototypes'][0]['key'], safe='')}")
        self.assertEqual((status, part[:4], headers["content-type"]), (200, b"XBM2", "application/octet-stream"))
        status, look = self.get("/api/v1/look")
        self.assertEqual((status, look["environment"]["url"]), (200, "/api/v1/look/environment"))
        status, _, image = self.request("/api/v1/look/environment")
        self.assertEqual((status, image[:10]), (200, b"#?RADIANCE"))
        # Under another kind, the same id is a 404 naming its own.
        status, refused = self.get(f"/api/v1/documents/step/{served['id']}/structure")
        self.assertEqual((status, refused["error"]), (404, f"{served['id']} is a xbf"))
        # Asked again, the same document.
        self.assertEqual(self.open(self.document), served)

    def test_a_step_is_read_by_the_engine_with_its_names_colours_and_materials(self) -> None:
        entry = catalog_entry(str(self.step))
        self.assertEqual((entry["kind"], entry["bytes"]), ("step", self.step.stat().st_size))
        structure = self.structure(self.open(self.step))
        by_name = {prototype["name"]: prototype for prototype in structure["prototypes"]}
        self.assertEqual(set(by_name), {"plate", "peg"})
        # The plate's Color(0.8, 0.1, 0.1), sRGB, held linear.
        self.assertEqual([round(value, 2) for value in by_name["plate"]["color"][:3]], [0.6, 0.01, 0.01])
        self.assertEqual((by_name["peg"]["material"]["material"]["name"], by_name["peg"]["material"]["material"]["density"]),
                         ("Alu_G6061_T6", 2700.0))
        self.assertEqual(sorted(instance["path"] for instance in structure["instances"]), ["pair/peg", "pair/plate"])
        # Read in a reader process, which the structure names: never the daemon itself.
        self.assertNotIn(structure["read"]["process"], (0, self.daemon_pid()))

    def test_a_step_opened_again_or_touched_is_not_parsed_again(self) -> None:
        copy = self.base / "again.step"
        shutil.copyfile(self.step, copy)
        self.assertFalse(self.held(copy), "the engine is asked, and asked for nothing")
        served = self.open(copy)
        self.assertTrue(self.held(copy))
        first = self.structure(served)
        # Opened again: the same document, the same read.
        self.assertEqual(self.open(copy), served)
        self.assertEqual(self.structure(served)["read"], first["read"])
        # Touched: a new version of the same bytes, read by nothing -- the parse is held by the bytes.
        later = time.time_ns() + 5_000_000_000
        os.utime(copy, ns=(later, later))
        deadline = time.monotonic() + 120
        while True:
            status, answer = self.get(f"/api/v1/documents/{served['id']}/version?after={quote(first['version'], safe='')}&wait=30")
            self.assertEqual(status, 200, answer)
            if answer["version"] != first["version"]:
                break
            self.assertLess(time.monotonic(), deadline, "the engine never noticed the file was written again")
        again = self.structure(served)
        self.assertNotEqual(again["version"], first["version"])
        self.assertEqual(again["read"], first["read"], "the same bytes are not parsed again")
        self.assertEqual([p["key"] for p in again["prototypes"]], [p["key"] for p in first["prototypes"]],
                         "nor meshed again: a part's key is made from the file's bytes")

    def test_a_row_says_how_many_parts_its_document_holds_once_the_engine_knows(self) -> None:
        # A model's, from its build: one part, and a pair of two.
        rows = {row["name"]: row for row in self.get("/api/v1/documents")[1]["documents"]}
        self.assertEqual((rows["block"]["parts"], rows["pair"]["parts"]), (1, 2))
        # An xbf the engine wrote -- a build's declared file, an export -- from the document it wrote it from: never
        # read for it, and no page has opened it.
        (self.base / "trio.py").write_text(textwrap.dedent(TRIO), encoding="utf-8")
        done = engine_daemon.run([sys.executable, "trio.py"], cwd=self.base, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        [trio] = [row["id"] for row in self.get("/api/v1/documents")[1]["documents"] if row["name"] == "trio"]
        exported = self.base / "out" / "trio.xbf"
        exported.parent.mkdir()
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "model", "export", trio, str(exported)],
                                 cwd=self.base, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for folder, name, parts in ((self.base / "XBF", "pair.xbf", 2), (exported.parent, "trio.xbf", 3)):
            status, project = self.send("POST", "/api/v1/projects", {"path": str(folder)})
            self.assertEqual(status, 201, project)
            [row] = [row for row in self.get(f"/api/v1/projects/{project['project']['id']}")[1]["documents"]
                     if row["name"] == name]
            self.assertEqual((row["parts"], row["opened"]), (parts, None), folder)
            self.assertFalse(self.held(folder / name), "the engine never read it")
        self.assertNotIn(str(exported).replace(os.sep, "/"), [row["path"] for row in self.get("/api/v1/documents")[1]["documents"]],
                         "counted, not opened: not in Recents")
        # Any other xbf, once the engine has read it for a page: one a page opened, its record made before the read.
        folder = self.base / "counted"
        folder.mkdir()
        opened, pictured = folder / "opened.xbf", folder / "pictured.xbf"
        for copy in (opened, pictured):
            shutil.copyfile(self.base / "XBF" / "pair.xbf", copy)
        self.assertEqual(self.send("PATCH", "/api/v1/documents", {"action": "open", "path": str(opened)})[0], 200)
        self.assertIsNone(self.row(opened)["parts"], "not read yet: no count")
        self.open(opened)
        self.assertEqual(self.row(opened)["parts"], 2)
        # A project's file, read by the engine before the home's picture of it made its record.
        status, project = self.send("POST", "/api/v1/projects", {"path": str(folder)})
        self.assertEqual(status, 201, project)
        listed = lambda: {row["name"]: row for row in self.get(f"/api/v1/projects/{project['project']['id']}")[1]["documents"]}
        self.assertIsNone(listed()["pictured.xbf"]["parts"], "no record, no read: no count")
        self.open(pictured)
        self.assertIsNone(listed()["pictured.xbf"]["parts"], "read, but no record to keep its count on")
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode("ascii")
        self.send("PATCH", "/api/v1/documents", {"action": "thumbnail", "path": str(pictured), "png": png})
        self.assertEqual((listed()["pictured.xbf"]["parts"], listed()["opened.xbf"]["parts"]), (2, 2))
        # Written since: its count is of another version, so none until the engine reads it again.
        later = time.time_ns() + 5_000_000_000
        os.utime(pictured, ns=(later, later))
        self.assertIsNone(listed()["pictured.xbf"]["parts"])

    def test_an_xbf_the_engine_wrote_from_a_model_is_that_models_one_card(self) -> None:
        folder = self.base / "fold"
        folder.mkdir()
        (folder / "arm.py").write_text(textwrap.dedent(ARM), encoding="utf-8")
        (folder / "hub.py").write_text(textwrap.dedent(HUB), encoding="utf-8")
        run = lambda *words: engine_daemon.run([sys.executable, *words], cwd=folder, env=self.env)
        for script in ("arm.py", "hub.py"):
            done = run(script)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        arm, hub = folder / "arm.xbf", folder / "hub.xbf"
        [ident] = [row["id"] for row in self.get("/api/v1/documents")[1]["documents"] if row["name"] == "hub"]
        # The person's exports of a model, an .xbf and a STEP, and a copy of a model's declared .xbf.
        for target in (hub, folder / "hub.step"):
            done = run("-m", "cad_server.cli", "model", "export", ident, str(target))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        shutil.copyfile(arm, folder / "arm-copy.xbf")
        status, project = self.send("POST", "/api/v1/projects", {"path": str(folder)})
        self.assertEqual(status, 201, project)
        listed = lambda: {row["name"]: row for row in self.get(f"/api/v1/projects/{project['project']['id']}")[1]["documents"]}
        posix = lambda path: str(path).replace(os.sep, "/")
        self.assertEqual(sorted(listed()), ["arm", "arm-copy.xbf", "hub", "hub.step"],
                         "each model once: the .xbf its build wrote and the .xbf exported of it are the model")
        self.assertEqual((listed()["arm"]["saved"], listed()["arm"]["parts"]), (posix(arm), 1))
        # Opened on a page, an .xbf is in Recents, where the model is too: one card there as well.
        for path in (arm, hub):
            self.assertEqual(self.send("PATCH", "/api/v1/documents", {"action": "open", "path": str(path)})[0], 200)
        recents = lambda: [row["path"] for row in self.get("/api/v1/documents")[1]["documents"]]
        self.assertNotIn(posix(arm), recents())
        self.assertNotIn(posix(hub), recents())
        # Rebuilt with a change: its build writes its declared .xbf again, which stays the model; the export it did
        # not write again holds an older document, and is a card of its own.
        for name, before, after in (("arm.py", "bd.Box(4, 4, 20)", "bd.Box(4, 4, 24)"),
                                    ("hub.py", "bd.Box(6, 6, 2)", "bd.Box(8, 8, 2)")):
            script = folder / name
            script.write_text(script.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")
            self.assertEqual(run(name).returncode, 0)
        self.assertEqual(sorted(listed()), ["arm", "arm-copy.xbf", "hub", "hub.step", "hub.xbf"])
        self.assertNotIn("of", listed()["hub.xbf"])
        self.assertIn(posix(hub), recents())
        done = run("-m", "cad_server.cli", "model", "export", ident, str(hub))  # exported again: the model now
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sorted(listed()), ["arm", "arm-copy.xbf", "hub", "hub.step"])
        # Touched by hand: no longer the file the build wrote, so a card of its own; the next run keeps it as it is
        # (the same bytes), and it is the model again.
        later = time.time_ns() + 5_000_000_000
        os.utime(arm, ns=(later, later))
        self.assertIn("arm.xbf", listed())
        self.assertNotIn("of", listed()["arm.xbf"])
        self.assertNotIn("saved", listed()["arm"])
        self.assertIn(posix(arm), recents())
        self.assertEqual(run("arm.py").returncode, 0)
        self.assertNotIn("arm.xbf", listed())
        # Rewritten by hand: its own card, until a run writes the model over it again.
        shutil.copyfile(self.base / "XBF" / "pair.xbf", arm)
        self.assertIn("arm.xbf", listed())
        self.assertEqual(run("arm.py").returncode, 0)
        self.assertNotIn("arm.xbf", listed())
        # The model deleted: its .xbf stays on disk and is listed as any file is.
        done = run("-m", "cad_server.cli", "delete", listed()["arm"]["id"], "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sorted(listed()), ["arm-copy.xbf", "arm.xbf", "hub", "hub.step"])
        self.assertTrue(arm.is_file())
        self.assertIn(posix(arm), recents())

    def row(self, path: Path) -> dict:
        """Recents' row of the file at ``path``."""
        [found] = [row for row in self.get("/api/v1/documents")[1]["documents"] if row["path"] == str(path).replace(os.sep, "/")
                   or row["path"] == str(path)]
        return found

    def send(self, method: str, target: str, payload: dict) -> tuple[int, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        try:
            connection.request(method, target, body=json.dumps(payload).encode(),
                               headers={"Authorization": "Bearer " + self.token, "x-cad-viewer": "1"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_document_routes_keep_authentication_and_do_not_relay(self):
        served = self.open(self.document)
        status, headers, _ = self.request(served["api"] + "/structure", {"Authorization": ""})
        self.assertEqual(status, 403)
        # The engine's own vocabulary is never on HTTP: its API is /api/v1.
        for target in ("/api/docs", f"/api/doc/{served['id']}", "/api/look"):
            with self.subTest(target=target):
                self.assertEqual(self.request(target)[0], 404)

    def test_the_cad_apps_tunnel_carries_an_engine_document(self) -> None:
        from cad_mcp.protocol import RequestContext
        from cad_mcp.shim import Proxy
        proxy = Proxy()
        context = RequestContext(1, {})
        # Cards, through the development switch: the tunnel is the same in a Codex tab.
        with mock.patch.dict(os.environ, {'CAD_MCP_PRESENTATION': 'inline'}):
            proxy.handle('initialize', {'protocolVersion': '2025-11-25',
                         'capabilities': {'extensions': {'io.modelcontextprotocol/ui':
                             {'mimeTypes': ['text/html;profile=mcp-app']}}}}, context)
        self.addCleanup(proxy.close)
        copy = self.base / "tunnelled.step"
        shutil.copyfile(self.step, copy)

        token = proxy.handle('tools/call', {'name': 'cad_show', 'arguments': {'source': str(copy)}}, context)['_meta']['dev.texttocad/httpToken']

        def get(url: str, payload: dict | None = None):
            method = 'GET' if payload is None else 'POST'
            body = '' if payload is None else base64.b64encode(json.dumps(payload).encode()).decode()
            reply = proxy.handle('tools/call', {'name': 'cad_http', 'arguments':
                         {'method': method, 'url': f'http://cad.invalid{url}', 'body': body,
                          'headers': {'x-cad-app': token, 'x-cad-viewer': '1'}}}, context)['structuredContent']
            body = base64.b64decode(reply.get("body") or "")
            return reply["status"], gzip.decompress(body) if reply.get("encoding") == "gzip" else body

        deadline = time.monotonic() + 300
        while True:
            status, body = get("/api/v1/documents", {"path": str(copy)})
            if status != 202:
                break
            # The tunnel holds no call long: the page is told to come back.
            self.assertEqual(json.loads(body)["state"], "reading")
            self.assertLess(time.monotonic(), deadline)
        self.assertEqual(status, 201, body)
        url = json.loads(body)["api"]
        status, body = get(url + "/structure")
        self.assertEqual(status, 200)
        structure = json.loads(body)
        self.assertEqual({prototype["name"] for prototype in structure["prototypes"]}, {"plate", "peg"})
        status, body = get(f"{url}/parts/{quote(structure['prototypes'][0]['key'], safe='')}")
        self.assertEqual((status, body[:4]), (200, b"XBM2"))

    def test_a_request_that_names_no_engine_document_is_refused_in_words(self) -> None:
        (self.base / "part.stl").write_text("solid t\nendsolid t\n", encoding="utf-8")
        (self.base / "garbage.step").write_text("not a step file\n", encoding="utf-8")
        for payload, status, words in (({}, 400, "a document opened is"),
                                       ({"path": str(self.base / "gone.xbf")}, 404, "no CAD file at")):
            with self.subTest(payload=payload):
                answered, body = self.post("/api/v1/documents", payload)
                self.assertEqual(answered, status)
                self.assertIn(words, body["error"])
        # A mesh is a document of its own kind, never the engine's: its engine reads are refused by name.
        stl = self.post("/api/v1/documents", {"path": str(self.base / "part.stl")})[1]
        status, body = self.get(f"/api/v1/documents/xbf/{stl['id']}/structure")
        self.assertEqual((status, body["error"]), (404, f"{stl['id']} is a stl"))
        # A file the engine cannot read: refused in the engine's words, once it has tried.
        status, body = self.answer(self.base / "garbage.step")
        self.assertEqual(status, 400, body)
        self.assertIn("garbage.step", body["error"])

    # --- helpers ---------------------------------------------------------------------------

    def daemon_pid(self) -> int:
        from cad.engine.client import request

        return int((request({"op": "status"}, start=False) or {}).get("pid") or 0)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
