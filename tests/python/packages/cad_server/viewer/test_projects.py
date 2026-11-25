"""Projects: a folder a person opened as one, its record in the state folder, the documents in it, and the
routes the home and every page's Project list read them by."""

from __future__ import annotations

import base64
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cad.engine.ids import derived_id, file_id, model_id
from cad_server.engine.registry import Folder, Registry
from cad_server.viewer import handler as handler_module
from cad_server.viewer import projects as projects_module
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.projects import Projects, Refused, walk
from cad_server.viewer.recents import RecentStore

STL = b"solid t\nendsolid t\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def slashed(path) -> str:
    return str(path).replace(os.sep, "/")


class ProjectsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))  # as the projects spell it (ids.canonical)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.projects = Projects(Folder(self.state))
        self.work = self.tmp / "work"
        for name in ("heart_tag.stl", "STEP/heart_tag.step", "STEP/old/gift.step", "src/heart_tag.py", "notes.txt",
                     ".git/x.step", "node_modules/y.stl", "build/z.stl", ".hidden.stl", "lib/inner/part.stl"):
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_bytes(STL)

    def test_a_folder_opened_is_one_record_and_opened_again_is_that_one(self) -> None:
        record, made = self.projects.add(str(self.work))
        self.assertTrue(made)
        self.assertEqual((record["id"], record["root"]), (derived_id(self.work), str(self.work)))
        self.assertEqual(sorted(os.listdir(self.state / "projects")), [f"{record['id']}.json"])
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

    def test_removing_a_project_forgets_its_record_alone(self) -> None:
        record, _ = self.projects.add(str(self.work))
        self.assertTrue(self.projects.remove(record["id"]))
        self.assertEqual(self.projects.list(), [])
        self.assertTrue((self.work / "heart_tag.stl").is_file(), "nothing on disk changes")
        self.assertFalse(self.projects.remove(record["id"]))
        self.assertFalse(self.projects.remove("not an id"))

    def test_a_record_this_schema_does_not_read_is_none(self) -> None:
        record, _ = self.projects.add(str(self.work))
        path = self.state / "projects" / f"{record['id']}.json"
        for text in ("{", "[]", json.dumps({**record, "schema": 99}), json.dumps({**record, "root": "relative"}),
                     json.dumps({**record, "schema": 1, "id": model_id(self.work / "a.py", "a")})):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                self.assertEqual(self.projects.list(), [])

    def test_the_walk_lists_cad_files_by_folder_past_hidden_build_and_nested_project_folders(self) -> None:
        found, truncated = walk(str(self.work))
        self.assertEqual(found, [slashed(self.work / name) for name in (
            "heart_tag.stl", "lib/inner/part.stl", "STEP/heart_tag.step", "STEP/old/gift.step")])
        self.assertFalse(truncated)
        found, _ = walk(str(self.work), skip=(str(self.work / "STEP"),))
        self.assertEqual(found, [slashed(self.work / name) for name in ("heart_tag.stl", "lib/inner/part.stl")])

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
        self.assertEqual(walk(str(self.work))[0], walk(str(self.work), skip=(str(self.work / "lib" / "again"),))[0])

    def test_a_projects_documents_are_its_models_then_its_files_with_their_records(self) -> None:
        store = RecentStore(self.state)
        inner, _ = self.projects.add(str(self.work / "lib"))  # opened first: a project inside the one opened next
        record, _ = self.projects.add(str(self.work))
        script = self.work / "src" / "heart_tag.py"
        for name in ("heart_tag", "blank"):
            store.registry.put({"id": model_id(script, name), "kind": "model", "root": str(script.parent), "home": script.name,
                                "entry": name, "namespace": str(script.parent), "name": name, "built": 1_700_000_000.0})
        store.opened(str(self.work / "heart_tag.stl"))
        store.pin(str(self.work / "heart_tag.stl"), True)
        listed = self.projects.documents(record, store.entries())
        self.assertEqual((listed["id"], listed["name"], listed["root"], listed["missing"], listed["truncated"]),
                         (record["id"], "work", slashed(self.work), False, False))
        documents = listed["documents"]
        self.assertEqual([(row["name"], row["record"]) for row in documents], [
            ("blank", "model"), ("heart_tag", "model"), ("heart_tag.stl", "file"), ("heart_tag.step", "file"), ("gift.step", "file")])
        self.assertEqual({row["project"] for row in documents}, {record["id"]})
        self.assertTrue(documents[2]["pinned"], "a file's row is its record's where it has one")
        self.assertEqual((documents[3]["id"], documents[3]["opened"]), (file_id(self.work / "STEP" / "heart_tag.step"), None))
        # The project inside it has its own.
        self.assertEqual([row["name"] for row in self.projects.documents(inner, store.entries())["documents"]], ["part.stl"])

    def test_a_file_a_page_opened_is_listed_whatever_the_walk_found(self) -> None:
        store = RecentStore(self.state)
        record, _ = self.projects.add(str(self.work))
        gone = self.work / "gone.stl"
        gone.write_bytes(STL)
        for path in (self.work / "build" / "z.stl", self.work / ".git" / "x.step", gone, self.work / "heart_tag.stl"):
            store.opened(str(path))
        gone.unlink()
        rows = self.projects.documents(record, store.entries())["documents"]
        self.assertEqual([row["name"] for row in rows], ["heart_tag.stl", "part.stl", "heart_tag.step", "gift.step",
                                                         "x.step", "z.stl", "gone.stl"], "the walk's, then the opened ones by path")
        self.assertEqual([row["name"] for row in rows if row["missing"]], ["gone.stl"])
        self.assertNotIn("y.stl", [row["name"] for row in rows], "a build folder's file no page opened is not listed")

    def test_a_walk_is_kept_a_moment_then_walked_again(self) -> None:
        record, _ = self.projects.add(str(self.work))
        first = self.projects.documents(record, [])
        (self.work / "new.stl").write_bytes(STL)
        self.assertEqual(self.projects.documents(record, [])["documents"], first["documents"])
        with mock.patch.object(projects_module, "WALK_KEPT_SECONDS", 0.0):
            self.assertIn("new.stl", [row["name"] for row in self.projects.documents(record, [])["documents"]])

    def test_readers_at_once_cost_one_walk(self) -> None:
        record, _ = self.projects.add(str(self.work))
        entered, release, walks = threading.Event(), threading.Event(), []

        def slow(root, **options):
            walks.append(root)
            entered.set()
            release.wait(10)
            return walk(root, **options)

        with mock.patch.object(projects_module, "walk", slow):
            readers = [threading.Thread(target=self.projects.documents, args=(record, [])) for _ in range(4)]
            for reader in readers:
                reader.start()
            self.assertTrue(entered.wait(10))
            release.set()
            for reader in readers:
                reader.join(10)
        self.assertEqual(len(walks), 1, "the readers that arrived while it was walked took its answer")

    def test_a_record_from_before_created_was_kept_stays_without_it(self) -> None:
        store = RecentStore(self.state)
        path = self.work / "heart_tag.stl"
        store.registry.put({"id": file_id(path), "kind": "file", "root": str(path.parent), "home": path.name,
                            "namespace": str(path.parent), "name": path.name, "opened": 1_000_000_000.0})
        store.opened(str(path))
        self.assertNotIn("created", store.registry.get(file_id(path)))


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

    def test_a_folder_opened_lists_with_its_documents_and_removed_is_gone(self) -> None:
        self.assertEqual(self.request("GET", "/api/v1/projects"), (200, {"projects": []}))
        status, opened = self.request("POST", "/api/v1/projects", {"path": str(self.work)})
        self.assertEqual((status, opened["made"], opened["project"]["name"]), (201, True, "work"))
        ident = opened["project"]["id"]
        self.assertEqual(set(opened["project"]), {"id", "name", "root", "created", "opened", "missing"})
        self.assertEqual(self.request("POST", "/api/v1/projects", {"path": str(self.work / "STL")})[0:1], (200,))
        status, listed = self.request("GET", "/api/v1/projects")
        [project] = listed["projects"]
        self.assertEqual((status, project["id"], [row["path"] for row in project["documents"]]),
                         (200, ident, [slashed(self.work / "STL" / "tag.stl")]))
        self.assertEqual(self.request("GET", f"/api/v1/projects/{ident}")[1], project)
        # A file listed is known by its id, opened by a page or not.
        [row] = project["documents"]
        self.assertEqual(self.request("GET", f"/api/v1/documents/{row['id']}")[1]["entry"]["project"]["id"], ident)
        self.assertEqual(self.request("DELETE", f"/api/v1/projects/{ident}"), (200, {"projects": []}))
        self.assertEqual(self.request("DELETE", f"/api/v1/projects/{ident}")[0], 404)
        self.assertEqual(self.request("GET", f"/api/v1/projects/{ident}")[0], 404)
        self.assertEqual(self.request("GET", "/api/v1/projects/not-an-id")[0], 404)
        self.assertTrue((self.work / "STL" / "tag.stl").is_file())

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
        self.assertEqual((status, envelope["entry"]["project"]), (200, {"id": ident, "name": "work", "root": slashed(self.work)}))
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
        listed = lambda: {row["name"]: row for row in self.request("GET", f"/api/v1/projects/{ident}")[1]["documents"]}
        # Walked through the link: listed where it was reached, the project's, as a file stored in the folder is.
        self.assertEqual((listed()["bolt.stl"]["path"], listed()["bolt.stl"]["project"]), (slashed(reached), ident))
        # Its page, by its id (as the home opens a row) and by the path it was reached by, says the project too.
        bolt = listed()["bolt.stl"]["id"]
        self.assertEqual(self.request("GET", f"/api/v1/documents/{bolt}")[1]["entry"]["project"]["id"], ident)
        status, found = self.request("GET", f"/api/v1/documents?path={slashed(reached)}")
        self.assertEqual((status, [row["entry"]["project"]["id"] for row in found["documents"]]), (200, [ident]))
        # Opened by the page, which names it where it is: its record keeps the path it was reached by, and its Recents
        # row says the project.
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open",
                                                                      "path": str(shared / "bolt.stl")})[0], 200)
        self.assertEqual(Registry(self.tmp / "state").get(bolt)["reached"], str(reached))
        [row] = [row for row in self.request("GET", "/api/v1/documents")[1]["documents"] if row["name"] == "bolt.stl"]
        self.assertEqual(row["project"], ident)
        self.assertEqual(self.request("GET", f"/api/v1/documents/{row['id']}")[1]["entry"]["project"]["id"], ident)
        # Opened, it is still one row of the project's, its record's, where it was reached.
        rows = [row for row in self.request("GET", f"/api/v1/projects/{ident}")[1]["documents"] if row["name"] == "bolt.stl"]
        self.assertEqual([(row["path"], row["opened"] is not None) for row in rows], [(slashed(reached), True)])
        # Named where it is, outside the folder, it is still the file the project reaches: the project's.
        status, found = self.request("GET", f"/api/v1/documents?path={slashed(shared / 'bolt.stl')}")
        self.assertEqual([row["entry"]["project"]["id"] for row in found["documents"]], [ident])
        # Its link gone, it is where it is: standalone.
        os.unlink(self.work / "vendor")
        self.assertIsNone(self.request("GET", f"/api/v1/documents/{bolt}")[1]["entry"]["project"])

    def test_the_home_pictures_a_projects_file_before_a_page_opens_it_and_recents_still_lists_opened_files(self) -> None:
        self.request("POST", "/api/v1/projects", {"path": str(self.work)})
        tag = self.work / "STL" / "tag.stl"
        status, rows = self.request("PATCH", "/api/v1/documents", {"action": "thumbnail", "path": str(tag),
                                                                   "png": base64.b64encode(PNG).decode("ascii")})
        self.assertEqual((status, rows["documents"]), (200, []), "pictured, not opened: not in Recents")
        [project] = self.request("GET", "/api/v1/projects")[1]["projects"]
        [row] = project["documents"]
        self.assertTrue(row["thumbnail"], "its picture is kept on a record of its own")
        self.assertEqual((row["opened"], row["created"]), (None, None), "no page opened it: no time of either")
        # Opened, it is in Recents, made then, its picture kept.
        [opened] = self.request("PATCH", "/api/v1/documents", {"action": "open", "path": str(tag)})[1]["documents"]
        self.assertEqual((opened["created"], opened["thumbnail"]), (opened["opened"], row["thumbnail"]))
        # A file that is no CAD file there gets no record, nor does one in no project that no page opened.
        for path in (self.work / "gone.stl", self.loose):
            self.request("PATCH", "/api/v1/documents", {"action": "thumbnail", "path": str(path),
                                                        "png": base64.b64encode(PNG).decode("ascii")})
        self.assertEqual([record["name"] for record in Registry(self.tmp / "state").list()], ["tag.stl"])

    def test_projects_are_listed_latest_activity_first(self) -> None:
        other = self.tmp / "other"
        other.mkdir()
        (other / "a.stl").write_bytes(STL)
        os.utime(other / "a.stl", (1_000_000_000, 1_000_000_000))
        os.utime(self.work / "STL" / "tag.stl", (1_000_000_000, 1_000_000_000))
        self.app.projects.clock = lambda: 1_100_000_000.0
        self.request("POST", "/api/v1/projects", {"path": str(self.work)})
        self.app.projects.clock = lambda: 1_200_000_000.0
        self.request("POST", "/api/v1/projects", {"path": str(other)})
        self.assertEqual([project["name"] for project in self.request("GET", "/api/v1/projects")[1]["projects"]], ["other", "work"])
        os.utime(self.work / "STL" / "tag.stl")  # written now
        with mock.patch.object(projects_module, "WALK_KEPT_SECONDS", 0.0):
            self.assertEqual([project["name"] for project in self.request("GET", "/api/v1/projects")[1]["projects"]], ["work", "other"])


if __name__ == "__main__":
    unittest.main()
