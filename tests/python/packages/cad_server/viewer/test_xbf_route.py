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
from cad.engine.ids import file_id
from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

MODEL = """
import build123d as bd
from cad.engine import step, model
from bd_materials import metals


@model("XBF/block.xbf")
def block():
    return bd.Box(10, 6, 4) - bd.Cylinder(1, 10)


@model("XBF/pair.xbf")
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

# A model whose document an export writes as another .xbf, a file of its own.
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
from cad import model


@model("arm.xbf")
def arm():
    return bd.Box(4, 4, 20)

if __name__ == "__main__":
    arm()
"""


# A model whose .xbf is its default, hub.xbf beside its script, which the person exports as another xbf too.
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

    def test_an_xbf_is_a_model_served_by_the_engine_and_read_through_the_viewer(self) -> None:
        # The row's format is its file's; the document is a model's, opened from an .xbf: a copy of a model's, a file
        # of its own.
        self.assertEqual(catalog_entry(str(self.document))["kind"], "xbf")
        copied = self.base / "copied" / "block.xbf"
        copied.parent.mkdir(exist_ok=True)
        shutil.copyfile(self.document, copied)
        served = self.open(copied)
        self.assertEqual(served, {"id": served["id"], "kind": "model", "api": f"/api/v1/documents/model/{served['id']}"})
        # Its envelope says what it is and where its reads are: a model's file, which exports itself as its original.
        status, envelope = self.get(f"/api/v1/documents/{served['id']}")
        self.assertEqual((status, envelope["kind"], envelope["api"], envelope["held"]), (200, "model", served["api"], True))
        self.assertEqual((envelope["source"]["type"], envelope["producers"], envelope["exports"][-1]),
                         ("file", [], "original"))
        # Its row in Recents, and the list of one kind, say model; the kind an .xbf had answers as model's.
        status, listed = self.get(f"/api/v1/documents?path={quote(str(copied), safe='')}")
        self.assertEqual((status, [row["kind"] for row in listed["documents"]]), (200, ["model"]))
        for kind in ("model", "xbf"):
            status, listed = self.get(f"/api/v1/documents/{kind}?path={quote(str(copied), safe='')}")
            self.assertEqual((status, [row["id"] for row in listed["documents"]]), (200, [served["id"]]))
        # A model's own .xbf opened by its path is the model, live while its worker holds the build: its id is the
        # file's, its source the script, its parameters the model's to set.
        own = self.open(self.document)
        self.assertEqual(own["id"], file_id(self.document))
        status, envelope = self.get(f"/api/v1/documents/{own['id']}")
        self.assertEqual((status, envelope["kind"], envelope["state"], envelope["source"]["type"],
                          envelope["source"]["path"]), (200, "model", "live", "script", str(self.base / "models.py")))
        self.assertNotEqual(self.post(own["api"] + "/parameters", {"values": {}})[0], 404)
        status, server = self.get("/api/v1/server")
        self.assertEqual((status, "model" in server["kinds"]["reads"], "xbf" in server["kinds"]["reads"],
                          server["kinds"]["exports"]["xbf"][-1]), (200, True, True, "original"))
        # The released route, documents/xbf/<id>, still answers: the same bodies as the model's (what the meshing
        # still running says of each part aside, which either read may meet).
        older = f"/api/v1/documents/xbf/{served['id']}"

        def settled(route: str) -> tuple[int, dict]:
            status, found = self.get(route)
            for prototype in found.get("prototypes", ()):
                for said in ("unmeshed", "unmeshedCheck"):
                    prototype.pop(said, None)
            return status, found

        self.assertEqual(settled(older + "/structure"), settled(served["api"] + "/structure"))
        self.assertEqual(self.request(older + "/source")[::2], (200, copied.read_bytes()))
        self.assertEqual(self.request(older + "/measure")[0], 200)
        # A copied .xbf is a model's no live worker holds: its parameters are refused as any such model's are.
        status, refused = self.post(served["api"] + "/parameters", {"values": {}})
        self.assertEqual((status, refused["code"]), (409, "no_worker"))
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
        self.assertEqual((status, refused["error"]), (404, f"{served['id']} is a model"))
        # Asked again, the same document.
        self.assertEqual(self.open(copied), served)

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
        self.assertEqual((rows["block.xbf"]["parts"], rows["pair.xbf"]["parts"]), (1, 2))
        # An xbf the engine wrote -- a model's own; an export, a file of its own -- counted from the document it wrote
        # it from: never read for it, and no page has opened it.
        (self.base / "trio.py").write_text(textwrap.dedent(TRIO), encoding="utf-8")
        done = engine_daemon.run([sys.executable, "trio.py"], cwd=self.base, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        [trio] = [row["id"] for row in self.get("/api/v1/documents")[1]["documents"] if row["name"] == "trio.xbf"]
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
            self.assertEqual((row["record"], row["parts"], row["opened"]), ("file", parts, None), folder)
        self.assertFalse(self.held(exported), "the engine never read it")
        self.assertNotIn(str(exported).replace(os.sep, "/"), [row["path"] for row in self.get("/api/v1/documents")[1]["documents"]],
                         "counted, not opened: not in Recents")
        # Any other xbf, once the engine has read it for a page: one a page opened, its entry made before the read.
        folder = self.base / "counted"
        folder.mkdir()
        opened, pictured = folder / "opened.xbf", folder / "pictured.xbf"
        for copy in (opened, pictured):
            shutil.copyfile(self.base / "XBF" / "pair.xbf", copy)
        self.assertEqual(self.send("PATCH", "/api/v1/documents", {"action": "open", "path": str(opened)})[0], 200)
        self.assertIsNone(self.row(opened)["parts"], "not read yet: no count")
        self.open(opened)
        self.assertEqual(self.row(opened)["parts"], 2)
        # A project's file no page opened, read by the engine: its count is the cache's note, with no entry, and
        # so is its picture.
        status, project = self.send("POST", "/api/v1/projects", {"path": str(folder)})
        self.assertEqual(status, 201, project)
        listed = lambda: {row["name"]: row for row in self.get(f"/api/v1/projects/{project['project']['id']}")[1]["documents"]}
        self.assertIsNone(listed()["pictured.xbf"]["parts"], "no read: no count")
        self.open(pictured)
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode("ascii")
        self.send("PATCH", "/api/v1/documents", {"action": "thumbnail", "path": str(pictured), "png": png})
        row = listed()["pictured.xbf"]
        self.assertEqual((row["parts"], row["opened"], row["thumbnail"] is not None, listed()["opened.xbf"]["parts"]),
                         (2, None, True, 2))
        self.assertEqual(self.request(f"/api/v1/documents/{row['id']}/thumbnail")[0], 200)
        # Written since: its count and its picture are of another version, so none until the engine reads it again.
        later = time.time_ns() + 5_000_000_000
        os.utime(pictured, ns=(later, later))
        self.assertEqual((listed()["pictured.xbf"]["parts"], listed()["pictured.xbf"]["thumbnail"]), (None, None))
        self.assertEqual(self.request(f"/api/v1/documents/{row['id']}/thumbnail")[0], 404)

    def test_a_model_is_its_xbf_one_card_and_an_export_or_a_copy_is_a_card_of_its_own(self) -> None:
        folder = self.base / "cards"
        folder.mkdir()
        (folder / "arm.py").write_text(textwrap.dedent(ARM), encoding="utf-8")
        (folder / "hub.py").write_text(textwrap.dedent(HUB), encoding="utf-8")
        run = lambda *words: engine_daemon.run([sys.executable, *words], cwd=folder, env=self.env)
        for script in ("arm.py", "hub.py"):
            done = run(script)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        arm, hub, exported = folder / "arm.xbf", folder / "hub.xbf", folder / "share" / "hub-v1.xbf"
        exported.parent.mkdir()
        [ident] = [row["id"] for row in self.get("/api/v1/documents")[1]["documents"] if row["name"] == "hub.xbf"]
        self.assertEqual(ident, file_id(hub), "a model's id is its .xbf's")
        # The person's exports of a model, an .xbf and a STEP, and a copy of a model's own .xbf.
        for target in (exported, folder / "hub.step"):
            done = run("-m", "cad_server.cli", "model", "export", ident, str(target))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        shutil.copyfile(arm, folder / "arm-copy.xbf")
        status, project = self.send("POST", "/api/v1/projects", {"path": str(folder)})
        self.assertEqual(status, 201, project)

        def listed(path: str = "") -> dict:
            found = self.get(f"/api/v1/projects/{project['project']['id']}?path={path}")[1]
            return {row["name"]: row for row in found["documents"]}

        posix = lambda path: str(path).replace(os.sep, "/")
        self.assertEqual(sorted(listed()), ["arm-copy.xbf", "arm.xbf", "hub.step", "hub.xbf"],
                         "each model once, its .xbf its row; a copied .xbf is a file of its own")
        self.assertEqual((listed()["arm.xbf"]["id"], listed()["arm.xbf"]["path"], listed()["arm.xbf"]["parts"]),
                         (file_id(arm), posix(arm), 1))
        self.assertEqual((listed()["hub.xbf"]["kind"], listed()["hub.xbf"]["parts"]), ("model", 2))
        self.assertEqual((listed("share")["hub-v1.xbf"]["kind"], listed("share")["hub-v1.xbf"]["parts"]), ("model", 2),
                         "an exported .xbf too, in its own folder")
        # Opened on a page, a model's .xbf is the one row it has in Recents: one card there as well.
        for path in (arm, hub, exported):
            self.assertEqual(self.send("PATCH", "/api/v1/documents", {"action": "open", "path": str(path)})[0], 200)
        recents = [row["path"] for row in self.get("/api/v1/documents")[1]["documents"]]
        self.assertEqual([recents.count(str(path)) for path in (arm, hub, exported)], [1, 1, 1])
        # Edited by hand: still its row, its count no longer known; the next run takes it by its key and counts
        # nothing, and a run that builds it counts it again.
        later = time.time_ns() + 5_000_000_000
        os.utime(arm, ns=(later, later))
        self.assertEqual((sorted(listed()), listed()["arm.xbf"]["parts"]),
                         (["arm-copy.xbf", "arm.xbf", "hub.step", "hub.xbf"], None))
        # Removed from the home's lists: its .xbf stays on disk, and its folder lists it as before.
        self.assertEqual(self.send("PATCH", "/api/v1/documents", {"action": "remove", "path": listed()["arm.xbf"]["id"]})[0], 200)
        self.assertNotIn(str(arm), [row["path"] for row in self.get("/api/v1/documents")[1]["documents"]])
        self.assertEqual(sorted(listed()), ["arm-copy.xbf", "arm.xbf", "hub.step", "hub.xbf"])
        self.assertTrue(arm.is_file())

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
