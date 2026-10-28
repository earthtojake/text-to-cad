"""Serving a document: its structure, one plain buffer per part in the wire format, the
same buffer whichever way it is meshed, a document read again after another process
rebuilt it, a model's declared xbf served as a file following its bytes alone, and the cap on
the buffers held; an inspection's read, which meshes nothing; each part's facts, measured once by
its key, in batches, on the pool's queue for facts."""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import tempfile
import textwrap
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import numpy as np

from cadgen.engine import build as engine_build
from cadgen.engine import mesh, serve
from cadgen.engine.serve import FACT, FACT_BYTES, MESH, Server

MODEL = """
import build123d as bd
from cadgen.engine import xbf

SIZE = {size}


@xbf("XBF/post.xbf")
def post():
    return bd.fillet((bd.Box(SIZE, 4, 10) - bd.Cylinder(1, 20)).edges().filter_by(bd.Axis.Z), 0.5)


@xbf("XBF/rack.xbf")
def rack():
    left = post().shape
    right = post().shape.moved(bd.Location((20, 0, 0)))
    right.label = "right"
    return bd.Compound(children=[left, right, bd.Pos(10, 0, -6) * bd.Box(30, 6, 2)], label="rack")
"""


class ServeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-serve-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "rack.py"
        self.write(4)
        self.server = Server(port=0, mesh_mode="inline")  # a test asks for the pool itself
        self.server.start()
        self.addCleanup(self.server.stop)
        self.ident = self.server.add(self.folder / "XBF/rack.xbf")

    def write(self, size: int) -> None:
        self.script.write_text(textwrap.dedent(MODEL.format(size=size)), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))
        reports = engine_build.build(self.script, ["rack"], cwd=self.folder)
        self.assertTrue(reports[-1]["ok"], reports)

    def get(self, path: str, method: str = "GET") -> bytes:
        request = urllib.request.Request(self.server.url + path, method=method)
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()

    def structure(self) -> dict:
        return json.loads(self.get(f"/api/doc/{self.ident}"))

    def test_a_part_is_one_plain_buffer_with_face_and_edge_ranges(self) -> None:
        structure = self.structure()
        self.assertEqual([i["path"] for i in structure["instances"]], ["rack/post", "rack/right", "rack/part2"])
        self.assertEqual(len(structure["prototypes"]), 2, "the post placed twice is one prototype")
        post = structure["prototypes"][structure["instances"][0]["prototype"]]
        data = self.get(f"/api/doc/{self.ident}/part/{post['key']}")
        self.assertEqual(data[:4], b"XBM2")
        part = mesh.Mesh.from_bytes(data)
        self.assertEqual(part.positions.dtype, np.float32)
        self.assertEqual(part.indices.dtype, np.uint32)
        # The face table tiles the index buffer, in order, every index a vertex.
        self.assertEqual(int(part.faces[:, 2].sum()), len(part.indices))
        self.assertTrue(np.array_equal(part.faces[1:, 1], np.cumsum(part.faces[:-1, 2])))
        self.assertLess(int(part.indices.max()), len(part.positions))
        # Ordinals are the ones the element names are kept by.
        self.assertEqual({str(o) for o in part.faces[:, 0]}, set(post["faceNames"]))
        self.assertEqual(int(part.edges[:, 2].sum()), len(part.edge_points))
        self.assertTrue(len(part.edges))

    def test_a_version_wait_that_is_no_number_is_refused_and_a_negative_one_waits_not_at_all(self) -> None:
        version = self.structure()["version"]
        for wait in ("nan", "inf", "-inf"):
            with self.subTest(wait=wait), self.assertRaises(urllib.error.HTTPError) as refused:
                self.get(f"/api/doc/{self.ident}/version?after={version}&wait={wait}")
            self.assertEqual(refused.exception.code, 400)
        with mock.patch.object(self.server, "wait", wraps=self.server.wait) as waited:
            answer = json.loads(self.get(f"/api/doc/{self.ident}/version?after={version}&wait=-5"))
        self.assertEqual(answer["version"], version)
        self.assertEqual(waited.call_args.args[2], 0.0, "a negative wait waits not at all")

    def test_a_version_wait_on_a_model_deleted_meanwhile_ends_not_found(self) -> None:
        # A page waits on a model's next version; `cadgen delete` forgets the model: the wait ends 404,
        # as every read of it does now, never as the server's own failure.
        held = self.server.document(self.ident)
        model = "a0000000-0000-5000-8000-00000000000d"
        self.server.register_model(model, "rack", lambda: (dict(held.structure), dict(held.shapes)), 1)
        version = json.loads(self.get(f"/api/doc/{model}/version"))["version"]
        answered: list = []

        def wait() -> None:
            try:
                self.get(f"/api/doc/{model}/version?after={version}&wait=10")
                answered.append(200)
            except urllib.error.HTTPError as error:
                answered.append(error.code)

        waiter = threading.Thread(target=wait)
        waiter.start()
        deadline = time.monotonic() + 10
        while model not in self.server.watchers and time.monotonic() < deadline:
            time.sleep(0.01)
        self.server.forget_model(model)
        waiter.join(15)
        self.assertEqual(answered, [404])

    def test_inline_and_processes_mesh_the_same_buffers(self) -> None:
        keys = [p["key"] for p in self.structure()["prototypes"]]
        first = json.loads(self.get(f"/api/doc/{self.ident}/mesh?mode=inline&drop=1", "POST"))
        self.assertEqual(first["meshed"], 2)
        inline = {key: self.server.cache.get(key) for key in keys}
        again = json.loads(self.get(f"/api/doc/{self.ident}/mesh?mode=processes&drop=1", "POST"))
        self.assertEqual((again["meshed"], again["mode"]), (2, "processes"))
        for key in keys:
            self.assertEqual(self.server.cache.get(key), inline[key])
        held = json.loads(self.get(f"/api/doc/{self.ident}/mesh", "POST"))
        self.assertEqual(held["meshed"], 0, "a part held is not meshed again")

    def test_a_served_document_is_read_again_after_a_rebuild(self) -> None:
        before = self.structure()
        self.write(6)
        after = self.structure()
        self.assertNotEqual(after["version"], before["version"])
        post = lambda s: s["prototypes"][s["instances"][0]["prototype"]]["key"]  # noqa: E731
        self.assertNotEqual(post(after), post(before), "the post's geometry changed")
        self.assertEqual(after["prototypes"][after["instances"][2]["prototype"]]["key"],
                         before["prototypes"][before["instances"][2]["prototype"]]["key"], "the base did not")


SHELF = """
import build123d as bd
from cadgen.engine import paint, step, xbf

SIZE = {size}


@xbf("XBF/shelf.xbf")
@step("shelf.step")
def shelf():
    post = bd.fillet(bd.Box(SIZE, 4, 10).edges().filter_by(bd.Axis.Z), 0.5)
    post.label = "post"
    left = post.moved(bd.Location((0, 0, 0)))
    right = post.moved(bd.Location((20, 0, 0)))
    right.label = "right"
    right.color = bd.Color(0.8, 0.1, 0.1)
    board = bd.Pos(10, 0, -6) * bd.Box(30, 6, 2)
    board = paint(board, board.faces().sort_by(bd.Axis.Z)[-1], "#1a33e6")
    board.label = "board"
    board.color = bd.Color(0.3, 0.6, 0.2)
    unnamed = bd.Pos(0, 10, 0) * bd.Sphere(2)
    repainted = board.moved(bd.Location((0, 0, -4)))
    repainted.label = "repainted"
    repainted.color = bd.Color(0.9, 0.9, 0.1)
    tier = bd.Compound(children=[board, repainted, unnamed], label="tier")
    return bd.Compound(children=[left, right, tier], label="shelf")
"""


class DeclaredFileTest(unittest.TestCase):
    """A model's declared xbf served as a file: the structure made from the build's tree is the
    file's, and a page waiting on the file's version is answered when the model's run rewrites
    it, from the file, with nothing of the model consulted."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-declared-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "shelf.py"
        self.path = self.folder / "XBF/shelf.xbf"

    def build(self, size: int) -> list:
        self.script.write_text(textwrap.dedent(SHELF.format(size=size)), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))
        reports = engine_build.build(self.script, ["shelf"], cwd=self.folder)
        self.assertTrue(reports[-1]["ok"], reports)
        return reports

    def test_the_structure_made_from_the_tree_is_the_files(self) -> None:
        from cadgen.engine import document

        self.build(4)
        made = document.tree_structure(document.saved(self.path), self.path)
        read = document.Loaded(self.path).structure()
        self.assertEqual(json.loads(json.dumps(made)), json.loads(json.dumps(read)))
        self.assertTrue(any(p["faceColors"] for p in read["prototypes"]), "a painted face is in it")
        self.assertTrue(any(i["color"] for i in read["instances"]), "an instance's own colour is in it")

    def test_a_declared_xbf_served_as_a_file_follows_its_bytes_and_consults_no_model(self) -> None:
        from unittest import mock

        from cadgen.engine import document

        self.build(4)
        server = Server(port=0, mesh_mode="inline")
        self.addCleanup(server.stop)
        ident = server.add(self.path)
        before = server.document(ident)
        server.mesh_all(before, None)
        answers = []
        consulted = AssertionError("a model was consulted")
        with mock.patch.object(engine_build, "held", side_effect=consulted), \
                mock.patch.object(engine_build, "taken", side_effect=consulted), \
                mock.patch.object(engine_build, "made_by", side_effect=consulted), \
                mock.patch.object(document, "saved", side_effect=consulted):
            waiting = threading.Thread(target=lambda: answers.append(server.wait(ident, before.version, 60)))
            waiting.start()  # a page waits on the file's version while the model runs again
            parked = time.monotonic() + 60
            while ident not in server.watchers:  # it watches before the model runs
                self.assertLess(time.monotonic(), parked, "the page's wait began")
                time.sleep(0.01)
            self.build(6)
            waiting.join(60)
            self.assertFalse(waiting.is_alive(), "the page's wait was answered")
            after = answers[0]
            stat = self.path.stat()
            self.assertEqual(after.version, f"{stat.st_mtime_ns}-{stat.st_size}", "the file's own version")
            self.assertEqual(json.loads(json.dumps(after.structure)),
                             json.loads(json.dumps(document.Loaded(self.path).structure())))
            self.assertIs(server.document(ident), after, "the file, unchanged since, is not read again")
            kept = {p["key"] for p in before.structure["prototypes"]} & {p["key"] for p in after.structure["prototypes"]}
            self.assertTrue(kept, "the parts the edit left alone keep their keys")
            self.assertTrue(all(server.cache.get(key) is not None for key in kept), "and their tessellations")


class ServedStepTest(unittest.TestCase):
    """A STEP served is read in a reader process, never in the server's: its structure and each
    part's shape bytes are what the server keeps. The read is held by the file's bytes -- served
    again, touched or copied, it is not parsed again -- and a STEP rewritten while it is served is
    read again in the background, the old version served until the new one is in."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-step-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        script = self.folder / "shelf.py"
        script.write_text(textwrap.dedent(SHELF.format(size=4)), encoding="utf-8")
        reports = engine_build.build(script, ["shelf"], cwd=self.folder)
        self.assertTrue(reports[-1]["ok"], reports)
        self.step = self.folder / "shelf.step"
        self.server = Server(port=0, mesh_mode="inline")
        self.addCleanup(self.server.stop)

    def test_a_step_is_read_by_a_reader_process_and_held_by_its_bytes(self) -> None:
        from cadgen.engine import document

        ident = self.server.add(self.step)
        served = self.server.document(ident)
        self.assertNotIn(served.structure["read"]["process"], (0, os.getpid()))
        self.assertTrue(all(isinstance(shape, bytes) for shape in served.shapes.values()), "only shape bytes are kept")
        # The document is the engine's reading of the file: what a read in this process makes of it.
        read, kept = (json.loads(json.dumps(structure)) for structure in (document.Loaded(self.step).structure(), served.structure))
        names = lambda structure: sorted((p["name"], p["color"], (p["material"] or {}).get("name"))  # noqa: E731
                                         for p in structure["prototypes"])
        self.assertEqual(names(kept), names(read))
        self.assertEqual(kept["instances"], read["instances"])
        # Served again, from another path, or touched: the same read.
        copy = self.folder / "copy.step"
        shutil.copyfile(self.step, copy)
        self.assertEqual(self.server.add(self.step), ident)
        self.assertEqual(self.server.document(self.server.add(copy)).structure["read"], served.structure["read"])
        later = time.time_ns() + 5_000_000_000
        os.utime(self.step, ns=(later, later))
        touched = self.server.wait(ident, served.version, 60)
        self.assertNotEqual(touched.version, served.version)
        self.assertEqual(touched.structure["read"], served.structure["read"])
        self.assertEqual(sorted(touched.shapes), sorted(served.shapes), "its parts' keys are the bytes'")
        # Other bytes are read again, in a reader of their own.
        self.step.write_bytes(self.step.read_bytes() + b"\n")
        rewritten = self.server.wait(ident, touched.version, 60)
        self.assertNotEqual(rewritten.structure["read"]["process"], served.structure["read"]["process"])

    def test_a_steps_import_says_its_stages_while_it_runs_and_nothing_once_it_is_in(self) -> None:
        from cadgen.engine import serve
        from cadgen.engine.addresses import document_id

        ident = document_id(self.step)
        heard: list[dict] = []
        done = threading.Event()

        def listen() -> None:  # what a page polling the version route would hear, as it moves
            while not done.is_set():
                frame = self.server.build_of(ident)["building"]
                if frame is not None and (not heard or heard[-1] != frame):
                    heard.append(frame)
                done.wait(0.01)

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()
        try:
            self.assertEqual(self.server.add(self.step), ident)
        finally:
            done.set()
            listener.join()
        self.assertTrue(heard, "the import said where it was")
        # The engine's one progress event (``progress.py``), of kind ``import``: the read first.
        self.assertEqual([(frame["kind"], frame["stage"], frame["job"], frame["outputs"]) for frame in heard[:1]],
                         [("import", "read", "shelf.step", [])])
        self.assertTrue(heard[0]["detail"].startswith("shelf.step ("), heard[0])
        self.assertEqual((heard[0]["done"], heard[0]["total"]), (0, None))
        self.assertTrue(all(frame["stage"] in ("read", "collect") for frame in heard), heard)
        after = self.server.build_of(ident)
        self.assertEqual((after["building"], after["failed"]), (None, None), "nothing once the document is in")
        self.assertGreaterEqual(after["progress"], 2, "each stage, and the end, moved the count")
        # The reader counts the parts it collects (the counts the server turns into frames).
        counts = self.folder / "counts.json"
        read = serve._read_foreign(str(self.step), "0" * 40, str(counts))
        self.assertEqual(json.loads(counts.read_text(encoding="utf-8")), {"done": len(read["shapes"]), "total": len(read["shapes"])})
        self.assertEqual(serve._import_counts(str(self.folder / "none.json")), None)

    def test_a_step_that_will_not_read_keeps_the_version_served_until_it_changes(self) -> None:
        ident = self.server.add(self.step)
        served = self.server.document(ident)
        self.step.write_text("not a step file\n", encoding="utf-8")
        stat = self.step.stat()
        self.server._reread(ident, served, (stat.st_mtime_ns, stat.st_size))  # as a version ask starts it
        self.assertIs(self.server.document(ident), served, "the page keeps the version it has")
        self.assertNotIn(ident, self.server.rereading, "and nothing reads the file again until it changes")


class ServerUrlTest(unittest.TestCase):
    def test_a_wildcard_bind_reports_a_loopback_url_and_keeps_its_bind(self) -> None:
        # `cadgen viewer --host 0.0.0.0` printed and opened http://0.0.0.0:<port>, which Chrome
        # refuses. A stand-in listener answers the bind: binding 0.0.0.0 in a test would expose a port.
        from types import SimpleNamespace

        binds = []

        def listener(server, host, port):
            binds.append(host)
            return SimpleNamespace(server_address=(host, 4242))

        for host, url in (("0.0.0.0", "http://127.0.0.1:4242"), ("127.0.0.1", "http://127.0.0.1:4242"),
                          ("::", "http://[::1]:4242"), ("::1", "http://[::1]:4242")):
            server = Server(host=host, mesh_mode="inline", http_factory=listener)
            self.addCleanup(server.mesher.stop)
            self.assertEqual(server.url, url, host)
        self.assertEqual(binds, ["0.0.0.0", "127.0.0.1", "::", "::1"], "the bind is the address asked for")


class NamedKeyTest(unittest.TestCase):
    """A part's key is what its geometry makes, wherever the part was read: an xbf that names
    another part's key for its own geometry is not served under that key, so a document served
    beside it keeps its own mesh and volume; a document's own keys survive its file."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-named-key-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def save(self, name: str, result, key: str | None = None) -> tuple[Path, list[str]]:
        """``result`` saved as ``name``.xbf, its parts keyed as a build keys them, or all
        named ``key``; with the keys its parts' geometry makes."""
        from cadgen.engine import document

        tree = document.collect(result, name)
        made = []
        for part in tree.parts:
            part.shape = document.direct(part.shape)
            made.append(document.geometry_key(part.shape))
            part.key = key or made[-1]
        path = self.folder / f"{name}.xbf"
        document.save(document.to_xcaf(tree), path, compare=False)
        return path, made

    def test_a_file_cannot_lend_its_part_another_parts_key(self) -> None:
        import build123d as bd

        from cadgen.engine import document

        own = bd.Box(10, 10, 10)
        spokes = bd.Compound([bd.Pos(7 * at, 0, 0) * bd.Rot(0, 0, 13 * at) * bd.Cylinder(2, 6) for at in range(4)])
        drilled = bd.Box(5, 5, 5) - bd.Rot(30, 20, 10) * bd.Cylinder(1.5, 20)
        own.label, spokes.label, drilled.label = "own", "spokes", "drilled"
        users, keys = self.save("user", bd.Compound(children=[own, spokes, drilled], label="user"))
        named, _ = self.save("named", bd.Box(40, 40, 2), key=keys[0])
        self.assertEqual([p.key for p in document.Loaded(users).prototypes], keys,
                         "a document's keys, parts placed inside them too, survive its file")
        [stranger] = document.Loaded(named).prototypes
        self.assertNotEqual(stranger.key, keys[0], "the key a file names is not taken on its word")

        server = Server(port=0, mesh_mode="inline")
        server.start()
        self.addCleanup(server.stop)

        def get(path: str) -> bytes:
            with urllib.request.urlopen(server.url + path, timeout=120) as answer:
                return answer.read()

        other = server.add(named)
        for prototype in json.loads(get(f"/api/doc/{other}"))["prototypes"]:
            get(f"/api/doc/{other}/part/{prototype['key']}")  # the stranger's meshes and facts held first
            get(f"/api/doc/{other}/part/{prototype['key']}/volume")
        mine = server.add(users)
        self.assertEqual(get(f"/api/doc/{mine}/part/{keys[0]}"), mesh.mesh_shape(mesh.shape_bytes(own.wrapped)).to_bytes())
        self.assertAlmostEqual(json.loads(get(f"/api/doc/{mine}/part/{keys[0]}/volume"))["volume"], 1000.0, places=6)


PLATE = "a0000000-0000-5000-8000-0000000000aa"
IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def registered(server: Server, parts: dict[str, bytes], version: int = 1) -> list[int]:
    """A model document of ``parts`` (each key's shape bytes) registered with ``server`` as a build
    registers one, a part placed once each; the versions its worker was asked for, as it is asked."""
    keys = list(parts)
    structure = {"name": "plate", "version": f"v{version}", "path": PLATE, "id": PLATE, "tree": {"name": "plate"},
                 "prototypes": [{"key": key, "name": key} for key in keys],
                 "instances": [{"prototype": at, "path": f"plate/{key}", "matrix": IDENTITY} for at, key in enumerate(keys)]}
    asked: list[int] = []

    def load() -> tuple:
        asked.append(version)
        return structure, dict(parts)

    server.register_model(PLATE, "plate", load, version)
    return asked


def kernel_facts(data: bytes) -> dict:
    """What the kernel's measure stands in for here: a part's facts made of its bytes alone."""
    return {"volume": float(len(data)), "solids": 1, "box": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, float(len(data))]}}


class InspectionReadTest(unittest.TestCase):
    """What ``cadgen inspect`` reads through the engine's door (``Server.read``): a structure that
    sends no part to the mesher, and each part's facts measured once by its geometry key -- an edit
    measures only the parts whose key is new. Measuring is lazy: a build of a document no inspection
    measured reads and measures nothing; once one has, each later build's new parts are measured
    before anyone asks."""

    def setUp(self) -> None:
        self.server = Server(port=0, mesh_mode="inline")
        self.server.start()
        self.addCleanup(self.server.stop)
        self.kernel = mock.patch("cadgen.engine.mesh.measured", side_effect=kernel_facts).start()
        self.addCleanup(mock.patch.stopall)

    def read(self, route: str):
        status, body = self.server.read(f"/api/doc/{PLATE}{route}")
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_an_inspection_s_structure_meshes_nothing_where_a_page_s_meshes_every_part(self) -> None:
        registered(self.server, {"k1": b"one", "k2": b"two"})
        with mock.patch.object(self.server, "_submit") as meshing:
            self.assertEqual([p["key"] for p in self.read("")["prototypes"]], ["k1", "k2"])
            self.assertEqual(sorted(self.read("/volumes")), ["k1", "k2"])
            meshing.assert_not_called()
            with urllib.request.urlopen(f"{self.server.url}/api/doc/{PLATE}", timeout=60) as page:
                self.assertEqual(page.status, 200)
        self.assertEqual(sorted(call.args[0] for call in meshing.call_args_list), ["k1", "k2"], "pages still prefetch")

    def test_a_part_is_measured_once_by_its_key_and_an_edit_measures_only_the_new_one(self) -> None:
        registered(self.server, {"k1": b"one", "k2": b"three"})
        self.assertEqual(self.read("/volumes"), {"k1": kernel_facts(b"one"), "k2": kernel_facts(b"three")})
        self.assertEqual(self.read("/volumes?keys=k2"), {"k2": kernel_facts(b"three")})
        self.assertEqual(self.read("/part/k1/volume"), kernel_facts(b"one"))
        self.assertEqual(self.kernel.call_count, 2, "each part measured once, however often it is asked")
        registered(self.server, {"k1": b"one", "k3": b"seven"}, version=2)  # the next build: k2 became k3
        self.assertEqual(sorted(self.read("/volumes")), ["k1", "k3"])
        self.assertEqual([call.args[0] for call in self.kernel.call_args_list], [b"one", b"three", b"seven"])
        refused = self.server.read(f"/api/doc/{PLATE}/volumes?keys=k1,nope")
        self.assertEqual(refused[0], 404)
        held = self.server.holding()
        self.server.facts.put("k9", kernel_facts(b"nine"))
        self.assertGreater(self.server.holding(), held, "the facts are held under the budget")
        self.server.trim(0)
        self.assertEqual((self.server.facts.size, self.server.facts.get("k1")), (0, None), "and evicted under it")

    def test_only_an_inspected_document_is_measured_after_its_build_and_only_its_new_keys(self) -> None:
        asked = registered(self.server, {"k1": b"one"})
        self.read("")  # a structure (``--query structure``) asks for no facts: no inspection of them
        self.assertIsNone(self.server.measure_later([PLATE]), "no inspection measured it: left alone")
        self.assertEqual((asked, self.kernel.call_count), ([1], 0), "read once, by the structure; measured never")
        self.assertEqual(sorted(self.read("/volumes")), ["k1"])  # the first inspection measures what it asks
        self.assertEqual(self.kernel.call_count, 1)
        asked = registered(self.server, {"k1": b"one", "k2": b"three"}, version=2)
        later = self.server.measure_later([PLATE])
        later.join(60)
        self.assertEqual(asked, [2], "read at its new version, once")
        self.assertEqual([call.args[0] for call in self.kernel.call_args_list], [b"one", b"three"], "k2 alone, at once")
        self.assertEqual(sorted(self.read("/volumes")), ["k1", "k2"])
        self.assertEqual(self.kernel.call_count, 2, "the inspection after the build finds both measured")

    def test_a_build_s_documents_wait_for_its_worker_to_settle_and_are_measured_once(self) -> None:
        # A program calls its models one after another: what its builds made is read once the worker
        # settles (the daemon's word), never between two of its builds.
        registered(self.server, {"k1": b"one"})
        self.read("/part/k1/volume")  # inspected: its facts asked for
        asked = registered(self.server, {"k1": b"one", "k2": b"three"}, version=2)
        settled = threading.Event()
        later = self.server.measure_later([PLATE], settled=settled.is_set)
        self.assertIsNone(self.server.measure_later([PLATE], settled=settled.is_set), "one waits for it already")
        self.assertEqual(asked, [], "nothing is read while the worker has not settled")
        settled.set()
        later.join(60)
        self.assertEqual((asked, self.kernel.call_count), ([2], 2))


class PoolFactsTest(unittest.TestCase):
    """The daemon's server measures a document's parts on its pool, in batches of about
    ``FACT_BYTES`` -- spread over the pool a page warmed, else over ``FACT_PROCESSES_COLD`` -- in the
    facts queue; a part asked while its batch waits is not measured again."""

    def setUp(self) -> None:
        self.server = Server(port=0, isolated=True)
        self.addCleanup(self.server.stop)
        self.server.mesher.workers = 4  # the fake pool's capacity, independent of the test host
        self.batches: list[tuple] = []

        def run(fn, *args, priority):
            future: concurrent.futures.Future = concurrent.futures.Future()
            self.batches.append((fn, args[0], priority, future))
            return future

        self.run = mock.patch.object(self.server.mesher, "run", side_effect=run).start()
        self.addCleanup(mock.patch.stopall)

    def test_a_pending_batch_is_shared_and_each_key_is_measured_once(self) -> None:
        registered(self.server, {"big": b"b" * (2 * FACT_BYTES), "mid": b"m" * FACT_BYTES, "small": b"s" * 10})
        doc = self.server.document(PLATE)
        self.assertEqual(self.server.measure(doc, wait=False), {}, "nothing measured yet")
        # No page warmed the pool: the batches start two processes at most, never the whole pool.
        self.assertEqual([(fn, priority) for fn, _batch, priority, _future in self.batches],
                         [(serve._measured, FACT)] * serve.FACT_PROCESSES_COLD)
        self.assertEqual(sorted(key for _fn, batch, _p, _f in self.batches for key, _data in batch), ["big", "mid", "small"])
        answers: list = []
        asking = threading.Thread(target=lambda: answers.append(self.server.measure(doc)))
        asking.start()
        self.assertEqual(self.server.measure(doc, wait=False), {}, "pending work is shared")
        self.assertEqual(len(self.batches), serve.FACT_PROCESSES_COLD)
        for _fn, batch, _priority, future in self.batches:  # the pool answers each batch
            future.set_result([(key, kernel_facts(data)) for key, data in batch])
        asking.join(30)
        self.assertEqual(answers, [{key: kernel_facts(data) for key, data in doc.shapes.items()}])
        self.assertEqual(self.server.measure(doc, ["small"]), {"small": kernel_facts(b"s" * 10)})
        self.assertEqual(len(self.batches), serve.FACT_PROCESSES_COLD)
        # A pool a page warmed takes them spread over all its processes.
        registered(self.server, {"a": b"a" * FACT_BYTES, "b": b"b" * FACT_BYTES, "c": b"c" * FACT_BYTES}, version=2)
        with mock.patch.object(type(self.server.mesher), "warm", new_callable=mock.PropertyMock, return_value=True):
            self.server.measure(self.server.document(PLATE), wait=False)
        self.assertEqual([len(batch) for _fn, batch, _p, _f in self.batches[serve.FACT_PROCESSES_COLD:]], [1, 1, 1])

    def test_a_waiting_read_is_told_each_part_as_its_batch_comes_in(self) -> None:
        # The summary's count is the engine's: nothing until the pool answers a batch, then each part
        # of it; parts held already, at once.
        registered(self.server, {"big": b"b" * (2 * FACT_BYTES), "mid": b"m" * FACT_BYTES, "small": b"s" * 10})
        doc = self.server.document(PLATE)
        self.server.measure(doc, wait=False)  # the batches handed to the pool: [big], [mid, small]
        told: list[tuple] = []
        changed = threading.Condition()

        def counted(done: int, total: int, key: str) -> None:
            with changed:
                told.append((done, total, key))
                changed.notify_all()

        def told_by(count: int) -> list[tuple]:
            with changed:
                self.assertTrue(changed.wait_for(lambda: len(told) >= count, timeout=30), told)
                return list(told)

        answers: list = []
        asking = threading.Thread(target=lambda: answers.append(self.server.measure(doc, counted=counted)))
        asking.start()
        (_fn, first, _p, settle_first), (_fn, second, _p, settle_second) = self.batches
        self.assertEqual(told, [], "nothing is in yet")
        settle_first.set_result([(key, kernel_facts(data)) for key, data in first])
        self.assertEqual(told_by(1), [(1, 3, "big")])
        settle_second.set_result([(key, kernel_facts(data)) for key, data in second])
        found = told_by(3)
        asking.join(30)
        self.assertEqual(([done for done, _total, _key in found], {key for _done, _total, key in found}),
                         ([1, 2, 3], {"big", "mid", "small"}))
        self.assertEqual(sorted(answers[0]), ["big", "mid", "small"])
        told.clear()
        self.server.measure(doc, counted=counted)
        self.assertEqual(told, [(3, 3, "small")], "every part held: the whole count at once")

    def test_a_document_s_parts_are_dealt_into_batches_of_about_fact_bytes(self) -> None:
        parts = [("a", b"x" * (3 * FACT_BYTES)), ("b", b"x" * FACT_BYTES), ("c", b"x" * FACT_BYTES), ("d", b"x" * 10)]
        self.assertEqual([[key for key, _data in batch] for batch in serve._batches(parts, 8)], [["a"], ["b"], ["c"], ["d"]])
        self.assertEqual([[key for key, _data in batch] for batch in serve._batches(parts, 2)], [["a"], ["b", "c", "d"]])
        light = [(f"p{at}", b"x" * 100) for at in range(30)]
        self.assertEqual(len(serve._batches(light, 8)), 1, "a light document is one job")


class PoolQueueTest(unittest.TestCase):
    """The pool's queues: a fact someone waits on goes before every mesh still waiting, measurements after a
    build use the same priority, and the pool is handed one
    job per process at a time."""

    def test_facts_wait_for_running_jobs_only_and_precede_every_queued_mesh(self) -> None:
        handed: list[tuple[str, concurrent.futures.Future]] = []
        changed = threading.Condition()

        class Pool:  # a ProcessPoolExecutor that runs nothing: the test settles each job it is handed
            def __init__(self, *args, **kwargs) -> None:
                self._broken = False

            def submit(self, fn, *args):
                future: concurrent.futures.Future = concurrent.futures.Future()
                with changed:
                    handed.append((fn, future))
                    changed.notify_all()
                return future

            def shutdown(self, *args, **kwargs) -> None:
                pass

        def handed_by(count: int) -> None:
            with changed:
                self.assertTrue(changed.wait_for(lambda: len(handed) >= count, timeout=30), [name for name, _ in handed])

        with mock.patch.object(serve.concurrent.futures, "ProcessPoolExecutor", Pool):
            mesher = serve.Mesher("processes", workers=1)
            self.addCleanup(mesher.stop)
            running = mesher.run("mesh 1", priority=MESH)
            handed_by(1)  # the one process is busy: everything after waits in its queue
            jobs = {name: mesher.run(name, priority=priority) for name, priority in
                    (("mesh 2", MESH), ("mesh 3", MESH), ("fact 1", FACT), ("fact 2", FACT))}
            for done in range(1, 5):
                handed[done - 1][1].set_result(done)
                handed_by(done + 1)
            handed[4][1].set_result(5)
        self.assertEqual([name for name, _future in handed], ["mesh 1", "fact 1", "fact 2", "mesh 2", "mesh 3"])
        self.assertEqual((running.result(1), jobs["fact 1"].result(1), jobs["mesh 3"].result(1)), (1, 2, 5))


class MeshCacheTest(unittest.TestCase):
    def test_mesh_all_publishes_buffers_and_unmeshed_notes_before_done_callbacks_finish(self) -> None:
        from types import SimpleNamespace

        # A Future wakes result() waiters before its callbacks finish. Hold the
        # worker's cache callback there while mesh_all consumes the completed job.
        completed = concurrent.futures.Future()
        server = Server.__new__(Server)
        server.cache = serve.MeshCache()
        server.isolated = False
        server.mesher = SimpleNamespace(submit=mock.Mock(return_value=completed), mode="inline", workers=1)
        server.shape_of = lambda doc, key: doc.shapes[key]
        doc = SimpleNamespace(shapes={"part": b"shape"}, names={"part": "peg"})
        server._submit("part", b"shape", None)
        entered, release = threading.Event(), threading.Event()
        put = server.cache.put
        failures = []

        def delayed_put(key, data, unmeshed):
            if not entered.is_set():
                entered.set()
                if not release.wait(30):
                    raise RuntimeError("test did not release the worker callback")
            put(key, data, unmeshed)

        def complete():
            try:
                completed.set_result((b"mesh bytes", {2: "degenerate"}, 0.1))
            except BaseException as error:
                failures.append(error)

        with mock.patch.object(server.cache, "put", side_effect=delayed_put), \
                mock.patch.object(serve, "_triangles", return_value=4):
            worker = threading.Thread(target=complete)
            worker.start()
            try:
                self.assertTrue(entered.wait(30), "the worker reached cache publication")
                report = server.mesh_all(doc, None)
                self.assertEqual(server.cache.get("part"), b"mesh bytes")
                self.assertEqual(server.cache.unmeshed("part"), {2: "degenerate"})
                self.assertEqual((report["meshed"], report["triangles"], report["unmeshed"]), (1, 4, 1))
            finally:
                release.set()
                worker.join(30)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(server.cache.pending, {})
        server.mesher.submit.assert_called_once_with(b"shape", None)

    def test_the_least_recently_used_buffer_goes_past_the_cap(self) -> None:
        from cadgen.engine.serve import MeshCache

        cache = MeshCache(cap=30)
        cache.put("a", b"x" * 10, {3: "valid"})
        cache.put("b", b"x" * 10)
        cache.put("c", b"x" * 10)
        self.assertIsNotNone(cache.get("a"))  # a is used: b is now the least recent
        cache.put("d", b"x" * 10)
        self.assertEqual(list(cache.items), ["c", "a", "d"])
        self.assertEqual(cache.size, 30)
        self.assertEqual(cache.unmeshed("a"), {3: "valid"})
        cache.put("e", b"x" * 25)
        self.assertEqual(list(cache.items), ["e"], "past the cap, the oldest go first")
        self.assertIsNone(cache.unmeshed("a"))


if __name__ == "__main__":
    unittest.main()
