"""Projects: a folder a person opened as one, its entry in the library, the page of one folder of it, and the
routes the home and every page's Project list read them by."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from urllib.parse import quote

from cad.engine.ids import derived_id, file_id
from cad_server.engine.library import Library, Notes
from cad_server.viewer import folders as folders_module
from cad_server.viewer import handler as handler_module
from cad_server.viewer import projects as projects_module
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.projects import NoFolder, Projects, Refused, has_cad_below, scan, walk

STL = b"solid t\nendsolid t\n"


def slashed(path) -> str:
    return str(path).replace(os.sep, "/")


class ProjectsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))  # as the projects spell it (ids.canonical)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.library = Library(self.state, self.tmp / "cache")
        self.notes = Notes(self.tmp / "cache")
        self.projects = Projects(self.library)
        self.work = self.tmp / "work"
        for name in ("heart_tag.stl", "STEP/heart_tag.step", "STEP/old/gift.step", "src/heart_tag.py", "notes.txt",
                     ".git/x.step", "node_modules/y.stl", "build/z.stl", ".hidden.stl", "lib/inner/part.stl"):
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_bytes(STL)

    def test_a_folder_opened_is_one_entry_and_opened_again_is_that_one(self) -> None:
        record, made = self.projects.add(str(self.work))
        self.assertTrue(made)
        self.assertEqual((record["id"], record["root"]), (derived_id(self.work), str(self.work)))
        self.assertEqual(list(self.library.read()["projects"]), [record["id"]])
        again, made = self.projects.add(str(self.work))
        self.assertFalse(made)
        self.assertEqual((again["id"], again["created"]), (record["id"], record["created"]))
        self.assertGreaterEqual(again["opened"], record["opened"])
        # Nothing is written to the folder.
        self.assertFalse(any(path.name.endswith(".json") or path.name == "cad.toml" for path in self.work.rglob("*")))

    def test_a_folder_inside_a_project_is_that_project_and_one_around_it_is_its_own(self) -> None:
        record, _ = self.projects.add(str(self.work))
        inner, made = self.projects.add(str(self.work / "STEP" / "old"))
        self.assertFalse(made, "projects do not nest by accident")
        self.assertEqual(inner["id"], record["id"])
        outer, made = self.projects.add(str(self.tmp))
        self.assertTrue(made)
        self.assertEqual(len(self.projects.list()), 2)
        # A document belongs to the nearest project above it.
        self.assertEqual(self.projects.of(str(self.work / "STEP" / "heart_tag.step"))["id"], record["id"])
        self.assertEqual(self.projects.of(str(self.tmp / "loose.stl"))["id"], outer["id"])
        self.assertIsNone(self.projects.of(str(self.state.parent.parent / "elsewhere.stl")))
        self.assertIsNone(self.projects.of(None))
        # A sibling whose name starts with the project's is not in it.
        self.assertIsNone(self.projects.of(str(self.work) + "-old/a.stl", [record]))

    def test_the_home_folder_a_folder_above_it_and_a_disks_root_are_no_project(self) -> None:
        home = self.tmp / "home" / "sam"
        home.mkdir(parents=True)
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            for folder in (home, home.parent, Path(os.path.abspath(os.sep))):
                with self.subTest(folder=folder), self.assertRaises(Refused) as refused:
                    self.projects.add(str(folder))
                self.assertIn("one project", refused.exception.hint)
            (home / "cad").mkdir()
            self.assertTrue(self.projects.add(str(home / "cad"))[1], "a folder inside the home folder is one")
        with self.assertRaises(FileNotFoundError):
            self.projects.add(str(self.work / "heart_tag.stl"))
        for path in ("work", "~/work", None, ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.projects.add(path)

    def test_removing_a_project_forgets_its_entry_alone(self) -> None:
        record, _ = self.projects.add(str(self.work))
        self.assertTrue(self.projects.remove(record["id"]))
        self.assertEqual(self.projects.list(), [])
        self.assertTrue((self.work / "heart_tag.stl").is_file(), "nothing on disk changes")
        self.assertFalse(self.projects.remove(record["id"]))
        self.assertFalse(self.projects.remove("not an id"))

    def test_the_walk_lists_cad_files_by_folder_past_hidden_and_build_folders(self) -> None:
        found, truncated = walk(str(self.work))
        self.assertEqual(found, [slashed(self.work / name) for name in (
            "heart_tag.stl", "lib/inner/part.stl", "STEP/heart_tag.step", "STEP/old/gift.step")])
        self.assertFalse(truncated)

    def test_the_walk_stops_at_its_bounds_and_says_so(self) -> None:
        # Breadth first: a walk cut short keeps the shallower files.
        self.assertEqual(walk(str(self.work), limit=2), ([slashed(self.work / "heart_tag.stl"),
                                                         slashed(self.work / "STEP/heart_tag.step")], True))
        self.assertEqual(walk(str(self.work), depth=0), ([slashed(self.work / "heart_tag.stl")], True))
        ticks = iter([0.0, 0.0, 5.0, 5.0, 5.0, 5.0])
        self.assertEqual(walk(str(self.work), seconds=1.0, clock=lambda: next(ticks)),
                         ([slashed(self.work / "heart_tag.stl")], True))

    def test_one_folder_of_many_entries_is_read_against_the_clock(self) -> None:
        for index in range(8):
            (self.work / f"note_{index}.txt").write_bytes(b"")
        ticks = iter([0.0, 0.0, 5.0])  # the walk's start, the folder's, then late as the folder is read
        with mock.patch.object(projects_module, "WALK_CLOCK_ENTRIES", 2):
            found, truncated = walk(str(self.work), seconds=1.0, clock=lambda: next(ticks))
        self.assertTrue(truncated, "a folder too large to read in time ends the walk, which says so")
        self.assertLessEqual(set(found), {slashed(self.work / "heart_tag.stl")})

    def test_folders_are_in_order_a_name_at_a_time(self) -> None:
        for name in ("a b/x.stl", "a/b/y.stl", "a-1/z.stl"):
            (self.tmp / "order" / name).parent.mkdir(parents=True)
            (self.tmp / "order" / name).write_bytes(STL)
        self.assertEqual(walk(str(self.tmp / "order"))[0],
                         [slashed(self.tmp / "order" / name) for name in ("a/b/y.stl", "a b/x.stl", "a-1/z.stl")])

    def test_a_link_back_into_a_folder_is_walked_once(self) -> None:
        try:
            os.symlink(self.work, self.work / "lib" / "again", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this platform makes no symbolic link here")
        self.assertEqual(walk(str(self.work))[0], [slashed(self.work / name) for name in (
            "heart_tag.stl", "lib/inner/part.stl", "STEP/heart_tag.step", "STEP/old/gift.step")])
        self.assertIs(has_cad_below(str(self.work / "src"), deadline=float("inf")), False, "and a test of it ends")

    def test_a_folder_lists_its_files_and_only_the_subfolders_with_cad_below(self) -> None:
        inner, _ = self.projects.add(str(self.work / "lib"))  # a project inside it is a folder like any other
        record, _ = self.projects.add(str(self.work))
        self.assertNotEqual(inner["id"], record["id"])
        for name in ("empty/deep/notes.txt", "many/a.stl", "many/b.stl", "many/c/d.stl"):
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_bytes(STL)
        self.library.opened(self.work / "heart_tag.stl")
        self.library.pin(self.work / "heart_tag.stl", True)
        self.notes.count(self.work / "heart_tag.stl", 4)
        read: list[str] = []
        entries = folders_module._entries

        def counted(folder):
            read.append(os.path.relpath(folder, self.work).replace(os.sep, "/"))
            return entries(folder)

        with mock.patch.object(projects_module, "_entries", counted):
            listed = self.projects.folder(record, None, self.notes)
        self.assertEqual((listed["project"]["id"], listed["path"], listed["truncated"]), (record["id"], "", False))
        self.assertEqual(listed["folders"], [{"name": name, "path": name} for name in ("lib", "many", "STEP")],
                         "no src, no empty: no CAD file below; never a hidden or a build folder")
        self.assertEqual([(row["name"], row["path"], row["project"], row["pinned"], row["parts"], row["opened"] is None)
                          for row in listed["documents"]],
                         [("heart_tag.stl", slashed(self.work / "heart_tag.stl"), record["id"], True, 4, False)])
        # The test of a subfolder stops at the first CAD file it meets: of many/, its own read alone.
        self.assertEqual(sorted(read), [".", "STEP", "empty", "empty/deep", "lib", "lib/inner", "many", "src"])
        with mock.patch.object(projects_module, "WALK_KEPT_SECONDS", 0.0):
            below = self.projects.folder(record, "STEP", self.notes)
            self.assertEqual((below["path"], below["folders"], [row["name"] for row in below["documents"]]),
                             ("STEP", [{"name": "old", "path": "STEP/old"}], ["heart_tag.step"]))
            self.assertEqual((below["documents"][0]["id"], below["documents"][0]["opened"], below["documents"][0]["created"]),
                             (file_id(self.work / "STEP" / "heart_tag.step"), None, None), "no entry: no time of either")
            with self.assertRaises(NoFolder):
                self.projects.folder(record, "STEP/none", self.notes)
            for path in ("/STEP", "STEP/", "STEP//old", "./STEP", "STEP/../src", str(self.work / "STEP")):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.projects.folder(record, path, self.notes)
        # A subfolder that cannot be read to the end in time is listed, and the answer says so.
        ticks = iter([0.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
        folders, files, truncated = scan(str(self.work), seconds=1.0, clock=lambda: next(ticks))
        self.assertEqual((folders, [name for name, _ident in files], truncated),
                         (["empty", "lib", "many", "src", "STEP"], ["heart_tag.stl"], True))
        with mock.patch.object(projects_module, "LIST_LIMIT", 2):
            self.assertEqual(scan(str(self.work)), (["lib"], [], True), "of more than it lists, the first in order")

    def test_a_search_finds_the_files_below_whose_path_holds_every_word(self) -> None:
        record, _ = self.projects.add(str(self.work))
        found = self.projects.search(record, None, "STEP  Heart", self.notes)
        self.assertEqual((found["folders"], [row["path"] for row in found["documents"]], found["truncated"]),
                         ([], [slashed(self.work / "STEP" / "heart_tag.step")], False))
        self.assertEqual([row["name"] for row in self.projects.search(record, "STEP", "step", self.notes)["documents"]],
                         ["heart_tag.step", "gift.step"], "below the folder on screen, by its path below it")
        with mock.patch.object(projects_module, "WALK_KEPT_SECONDS", 0.0), \
                mock.patch.object(projects_module, "walk", lambda folder: walk(folder, limit=1)):
            cut = self.projects.search(record, "STEP", "step", self.notes)
        self.assertEqual(([row["name"] for row in cut["documents"]], cut["truncated"]), (["heart_tag.step"], True))

    def test_a_folders_read_is_kept_a_moment_then_read_again(self) -> None:
        record, _ = self.projects.add(str(self.work))
        first = self.projects.folder(record, None, self.notes)
        (self.work / "new.stl").write_bytes(STL)
        self.assertEqual(self.projects.folder(record, None, self.notes)["documents"], first["documents"])
        with mock.patch.object(projects_module, "WALK_KEPT_SECONDS", 0.0):
            self.assertIn("new.stl", [row["name"] for row in self.projects.folder(record, None, self.notes)["documents"]])

    def test_readers_at_once_cost_one_read(self) -> None:
        record, _ = self.projects.add(str(self.work))
        entered, release, scans = threading.Event(), threading.Event(), []

        def slow(folder, level):
            scans.append(folder)
            entered.set()
            release.wait(10)
            return scan(folder, level)

        with mock.patch.object(projects_module, "scan", slow):
            readers = [threading.Thread(target=self.projects.folder, args=(record, None, self.notes)) for _ in range(4)]
            for reader in readers:
                reader.start()
            self.assertTrue(entered.wait(10))
            release.set()
            for reader in readers:
                reader.join(10)
        self.assertEqual(len(scans), 1, "the readers that arrived while it was read took its answer")


class ProjectRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / "work"
        (self.work / "STL").mkdir(parents=True)
        (self.work / "STL" / "tag.stl").write_bytes(STL)
        self.loose = self.tmp / "loose.stl"
        self.loose.write_bytes(STL)
        state = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state"), "CAD_CACHE_DIR": str(self.tmp / "cache")})
        state.start()
        self.addCleanup(state.stop)
        self.app = create_cad_app(host="127.0.0.1", port=0)
        server = handler_module.serve(self.app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, method: str, path: str, body=None, *, guard=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"x-cad-viewer": "1"} if guard else {}
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
        finally:
            connection.close()

    def test_the_folder_route_answers_its_contract(self) -> None:
        self.assertEqual(self.request("GET", "/api/v1/projects"), (200, {"projects": []}))
        status, opened = self.request("POST", "/api/v1/projects", {"path": str(self.work)})
        self.assertEqual((status, opened["made"], opened["project"]["name"]), (201, True, "work"))
        ident = opened["project"]["id"]
        project = {"id": ident, "name": "work", "root": slashed(self.work), "created": opened["project"]["created"],
                   "opened": opened["project"]["opened"], "missing": False}
        self.assertEqual(opened["project"], project)
        self.assertEqual(self.request("POST", "/api/v1/projects", {"path": str(self.work / "STL")})[0:1], (200,))
        status, listed = self.request("GET", "/api/v1/projects")
        self.assertEqual((status, [{**row, "opened": project["opened"]} for row in listed["projects"]]), (200, [project]),
                         "a project's row: no documents, no count")
        # A listing: the folder's own files, and its subfolders that hold a CAD file.
        (self.work / "docs").mkdir()
        (self.work / "docs" / "readme.txt").write_text("no CAD here", encoding="utf-8")
        status, root = self.request("GET", f"/api/v1/projects/{ident}")
        self.assertEqual((status, set(root)), (200, {"project", "path", "folders", "documents", "truncated"}))
        self.assertEqual((root["project"]["id"], root["path"], root["folders"], root["documents"], root["truncated"]),
                         (ident, "", [{"name": "STL", "path": "STL"}], [], False))
        status, below = self.request("GET", f"/api/v1/projects/{ident}?path=STL")
        [row] = below["documents"]
        self.assertEqual((status, below["path"], below["folders"]), (200, "STL", []))
        tag = self.work / "STL" / "tag.stl"
        self.assertEqual(row, {"id": file_id(tag), "kind": "stl", "record": "file",
                               "api": f"/api/v1/documents/stl/{file_id(tag)}", "path": slashed(tag), "name": "tag.stl",
                               "folder": slashed(tag.parent), "namespace": slashed(tag.parent), "opened": None,
                               "updated": tag.stat().st_mtime, "created": None, "pinned": False, "missing": False,
                               "thumbnail": None, "pictured": None, "size": len(STL), "parts": None, "project": ident})
        # A file listed is known by its id, opened by a page or not, and its envelope says the folder it is in.
        self.assertEqual(self.request("GET", f"/api/v1/documents/{row['id']}")[1]["entry"]["project"],
                         {"id": ident, "name": "work", "root": slashed(self.work), "folder": "STL"})
        # A search: every file below the folder whose path holds every word, flat; a blank one is the listing.
        status, found = self.request("GET", f"/api/v1/projects/{ident}?q={quote('stl TAG')}")
        self.assertEqual((status, found["path"], found["folders"], found["documents"], found["truncated"]),
                         (200, "", [], [row], False))
        self.assertEqual(self.request("GET", f"/api/v1/projects/{ident}?q=bolt")[1]["documents"], [])
        self.assertEqual(self.request("GET", f"/api/v1/projects/{ident}?q={quote('  ')}")[1], root)
        # Its errors.
        status, none = self.request("GET", f"/api/v1/projects/{ident}?path=STL/none")
        self.assertEqual((status, none), (404, {"error": "no folder STL/none in work",
                                               "hint": "list the project's folder: leave path out"}))
        for path in ("/STL", "STL/", "../work", "STL/./x", slashed(self.work / "STL")):
            with self.subTest(path=path):
                status, refused = self.request("GET", f"/api/v1/projects/{ident}?path={quote(path, safe='')}")
                self.assertEqual((status, set(refused)), (400, {"error", "hint"}))
        self.assertEqual(self.request("PUT", f"/api/v1/projects/{ident}", {})[0], 405)
        # Removed, it is no project, and nothing in its folder changed.
        self.assertEqual(self.request("DELETE", f"/api/v1/projects/{ident}"), (200, {"projects": []}))
        self.assertEqual(self.request("DELETE", f"/api/v1/projects/{ident}")[0], 404)
        status, none = self.request("GET", f"/api/v1/projects/{ident}")
        self.assertEqual((status, none), (404, {"error": f"no project {ident}",
                                               "hint": "GET /api/v1/projects lists the projects"}))
        self.assertEqual(self.request("GET", "/api/v1/projects/not-an-id")[0], 404)
        self.assertTrue(tag.is_file())
        # Its folder gone: the project is answered missing, with nothing in it, whatever the path.
        gone = self.tmp / "gone"
        gone.mkdir()
        ident = self.request("POST", "/api/v1/projects", {"path": str(gone)})[1]["project"]["id"]
        gone.rmdir()
        status, missing = self.request("GET", f"/api/v1/projects/{ident}?path=any/where")
        self.assertEqual((status, missing["project"]["missing"], missing["folders"], missing["documents"]),
                         (200, True, [], []))

    def test_a_folder_that_is_no_project_says_why_and_what_to_open(self) -> None:
        status, refused = self.request("POST", "/api/v1/projects", {"path": os.path.abspath(os.sep)})
        self.assertEqual(status, 400)
        self.assertEqual(refused["hint"], "open the folder of one project, inside your home folder")
        self.assertEqual(self.request("POST", "/api/v1/projects", {"path": str(self.tmp / "missing")})[0], 404)
        self.assertEqual(self.request("POST", "/api/v1/projects", {"path": "work"})[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/projects", {"folder": str(self.work)})[0], 400)
        self.assertEqual(self.request("POST", "/api/v1/projects", {"path": str(self.work)}, guard=False)[0], 403,
                         "a page from another site opens none")
        self.assertEqual(self.request("DELETE", "/api/v1/projects", guard=True)[0], 405)
        self.assertEqual(self.request("PUT", f"/api/v1/projects/{derived_id(self.work)}", {})[0], 405)

    def test_rows_and_a_documents_envelope_say_the_project_it_is_in(self) -> None:
        for path in (self.work / "STL" / "tag.stl", self.loose):
            self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": str(path)})[0], 200)
        status, rows = self.request("GET", "/api/v1/documents")
        self.assertEqual({row["name"]: row["project"] for row in rows["documents"]}, {"tag.stl": None, "loose.stl": None})
        ident = self.request("POST", "/api/v1/projects", {"path": str(self.work)})[1]["project"]["id"]
        status, rows = self.request("GET", "/api/v1/documents")
        self.assertEqual({row["name"]: row["project"] for row in rows["documents"]}, {"tag.stl": ident, "loose.stl": None})
        status, envelope = self.request("GET", f"/api/v1/documents/{file_id(self.work / 'STL' / 'tag.stl')}")
        self.assertEqual((status, envelope["entry"]["project"]),
                         (200, {"id": ident, "name": "work", "root": slashed(self.work), "folder": "STL"}))
        before = envelope["revision"]
        self.assertIsNone(self.request("GET", f"/api/v1/documents/{file_id(self.loose)}")[1]["entry"]["project"])
        # A link to it is the file it names: in its project, however the page spelled its path.
        link = self.tmp / "link.stl"
        try:
            os.symlink(self.work / "STL" / "tag.stl", link)
        except (OSError, NotImplementedError):
            link = None
        if link is not None:
            status, linked = self.request("GET", f"/api/v1/documents?path={slashed(link)}")
            self.assertEqual((status, [row["entry"]["project"]["id"] for row in linked["documents"]]), (200, [ident]))
        # Removed, it is standalone again, and its row's digest says so.
        self.request("DELETE", f"/api/v1/projects/{ident}")
        status, envelope = self.request("GET", f"/api/v1/documents/{file_id(self.work / 'STL' / 'tag.stl')}")
        self.assertIsNone(envelope["entry"]["project"])
        self.assertNotEqual(envelope["revision"], before)

    def test_a_file_reached_through_a_linked_folder_inside_a_project_is_that_projects(self) -> None:
        shared = self.tmp / "shared"
        shared.mkdir()
        (shared / "bolt.stl").write_bytes(STL)
        try:
            os.symlink(shared, self.work / "vendor", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("no symbolic links here")
        reached = self.work / "vendor" / "bolt.stl"
        ident = self.request("POST", "/api/v1/projects", {"path": str(self.work)})[1]["project"]["id"]
        self.assertEqual(self.request("GET", f"/api/v1/projects/{ident}")[1]["folders"],
                         [{"name": "STL", "path": "STL"}, {"name": "vendor", "path": "vendor"}])
        listed = lambda: {row["name"]: row for row in
                          self.request("GET", f"/api/v1/projects/{ident}?path=vendor")[1]["documents"]}
        # Listed through the link: where it was reached, the project's, as a file stored in the folder is.
        self.assertEqual((listed()["bolt.stl"]["path"], listed()["bolt.stl"]["project"]), (slashed(reached), ident))
        # Its page, by its id (as the home opens a row) and by the path it was reached by, says the project too.
        bolt = listed()["bolt.stl"]["id"]
        self.assertEqual(self.request("GET", f"/api/v1/documents/{bolt}")[1]["entry"]["project"],
                         {"id": ident, "name": "work", "root": slashed(self.work), "folder": "vendor"})
        status, found = self.request("GET", f"/api/v1/documents?path={slashed(reached)}")
        self.assertEqual((status, [row["entry"]["project"]["id"] for row in found["documents"]]), (200, [ident]))
        # Opened by the page, which names it where it is: its entry keeps the path it was reached by, and its Recents
        # row says the project.
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open",
                                                                      "path": str(shared / "bolt.stl")})[0], 200)
        self.assertEqual(Library(self.tmp / "state").read()["files"][bolt]["reached"], str(reached))
        [row] = [row for row in self.request("GET", "/api/v1/documents")[1]["documents"] if row["name"] == "bolt.stl"]
        self.assertEqual(row["project"], ident)
        self.assertEqual(self.request("GET", f"/api/v1/documents/{row['id']}")[1]["entry"]["project"]["id"], ident)
        # Opened, it is still one row of the folder's, its entry's, where it was reached.
        self.assertEqual([(row["path"], row["opened"] is not None) for row in listed().values()], [(slashed(reached), True)])
        # Named where it is, outside the folder, it is still the file the project reaches: the project's.
        status, found = self.request("GET", f"/api/v1/documents?path={slashed(shared / 'bolt.stl')}")
        self.assertEqual([row["entry"]["project"]["id"] for row in found["documents"]], [ident])
        # Its link gone, it is where it is: standalone.
        os.unlink(self.work / "vendor")
        self.assertIsNone(self.request("GET", f"/api/v1/documents/{bolt}")[1]["entry"]["project"])

    def test_projects_are_listed_latest_activity_first(self) -> None:
        other = self.tmp / "other"
        other.mkdir()
        self.app.library.clock = lambda: 1_100_000_000.0
        self.request("POST", "/api/v1/projects", {"path": str(self.work)})
        self.app.library.clock = lambda: 1_200_000_000.0
        self.request("POST", "/api/v1/projects", {"path": str(other)})
        self.assertEqual([project["name"] for project in self.request("GET", "/api/v1/projects")[1]["projects"]], ["other", "work"])
        self.app.library.clock = lambda: 1_300_000_000.0  # a file of it opened by a page, now
        self.request("PATCH", "/api/v1/documents", {"action": "open", "path": str(self.work / "STL" / "tag.stl")})
        self.assertEqual([project["name"] for project in self.request("GET", "/api/v1/projects")[1]["projects"]], ["work", "other"])


if __name__ == "__main__":
    unittest.main()
