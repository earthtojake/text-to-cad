"""Which release an environment runs as its interpreter starts (``_cad_release``, at the wheel's root, imported by
``cad.pth``): its own packages, or the stored release its pointer names.

That module is the one part of cad's update an update cannot replace, so these tests pin what it does as it really
runs: a real virtual environment with a stand-in cad installed (``tests/python/support/release_environment.py``),
stored releases beside it, pointers written by hand, and the environment's own interpreter started in a subprocess to
say which code runs, what its import path is, and what the module kept. Never imported here to be run: in this
process it ran long ago, from this checkout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from tests.python.support.paths import SOURCE_PATH
from tests.python.support.release_environment import (LEFT_OUT, PROBE, RECORD, SECONDS, Environment,
                                                      child_environment, pointer_name, write)
from tests.python.support.tmp_root import temporary_directory


class Bootstrap(unittest.TestCase):
    """One environment for the class; each test its own state folder and stored release, and cad installed afresh."""

    @classmethod
    def setUpClass(cls) -> None:
        scratch = temporary_directory(prefix="cad-release-")
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name).resolve()
        cls.env = Environment(cls.root / "env")
        cls.count = 0
        cls.baseline = cls.env.probe(state=cls.root / "no-state")

    def setUp(self) -> None:
        self.fresh()

    def fresh(self) -> None:
        """A state folder and a stored release of their own, and cad installed again."""
        type(self).count += 1
        self.folder = self.root / f"case-{self.count}"
        self.state = self.folder / "state"
        self.stored = self.env.store(self.folder / "releases" / f"1.0.1-{self.env.tag}")
        self.env.install()

    # --- what a process says ---------------------------------------------------------------------------------------

    def at(self, found: dict[str, Any]) -> int:
        here = os.path.normcase(found["here"])
        return next(at for at, entry in enumerate(found["path"]) if os.path.normcase(os.path.abspath(entry)) == here)

    def assertOwn(self, found: dict[str, Any], why: str = "") -> None:
        """The environment's own packages ran, its import path untouched, and nothing was held."""
        self.assertEqual((found["cad"], found["lazy"], found["stored"], found["held"]), ("own", "own", None, False), why)
        self.assertEqual(found["path"], self.baseline["path"], why)
        self.assertEqual((found["own_only"], found["stored_only"], found["stored_pth"]), (True, False, False), why)

    def assertTaken(self, found: dict[str, Any], baseline: dict[str, Any] | None = None) -> None:
        """The stored release ran in the place of the environment's own packages: replaced at the same index, the
        environment's own packages gone from the path, its ``.pth`` files read, its marker held. ``baseline``: what a
        process started the same way says with no pointer."""
        stored, baseline = self.stored, baseline or self.baseline
        at = self.at(baseline)
        self.assertEqual((found["cad"], found["lazy"], found["stored"], found["held"]),
                         ("stored", "stored", str(stored), True))
        self.assertEqual(found["path"], [*baseline["path"][:at], str(stored), *baseline["path"][at + 1:]],
                         "in the place of the environment's own packages, not before them")
        self.assertEqual((found["own_only"], found["stored_only"], found["stored_pth"]), (False, True, True))
        self.assertEqual(found["prefix"], baseline["prefix"], "sys.prefix stays the environment's")

    def assertSilent(self, state: Path | None = None, **options: Any) -> None:
        """An interpreter of the environment that runs nothing ends well and prints nothing."""
        found = self.env.run("-c", "pass", state=state or self.state, **options)
        self.assertEqual((found.returncode, found.stdout, found.stderr), (0, "", ""))

    # --- the cases ---------------------------------------------------------------------------------------------------

    def test_with_no_pointer_the_environment_runs_its_own_packages_and_the_path_is_untouched(self) -> None:
        found = self.env.probe(state=self.state)
        self.assertOwn(found)
        self.assertTrue(os.path.samefile(found["here"], self.env.packages))
        self.assertSilent()

    def test_a_pointer_runs_the_stored_release_in_place_of_the_environment_s_packages(self) -> None:
        self.env.point(self.state, self.stored)
        self.assertTaken(self.env.probe(state=self.state))
        self.assertSilent()

    def test_each_reason_a_pointer_is_not_taken_leaves_the_environment_running_its_own_packages_silently(self) -> None:
        env = self.env

        def keyed(**changes: Any) -> Callable[[Bootstrap], None]:
            return lambda test: env.point(test.state, test.stored, **changes)

        def then(change: Callable[[Bootstrap], Any]) -> Callable[[Bootstrap], None]:
            def apply(test: Bootstrap) -> None:
                env.point(test.state, test.stored)
                change(test)
            return apply

        def text(content: str | bytes) -> Callable[[Bootstrap], None]:
            def apply(test: Bootstrap) -> None:
                target = env.pointer_path(test.state)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
            return apply

        def stamp_moved(test: Bootstrap) -> None:
            kept = env.record.stat()
            os.utime(env.record, ns=(kept.st_atime_ns, kept.st_mtime_ns + 1_000_000_000))

        def size_changed(test: Bootstrap) -> None:
            kept = env.record.stat()
            with open(env.record, "a", encoding="utf-8") as record:
                record.write("one more line,,\n")
            os.utime(env.record, ns=(kept.st_atime_ns, kept.st_mtime_ns))

        def marker_a_folder(test: Bootstrap) -> None:
            (test.stored / "cad-store.json").unlink()
            (test.stored / "cad-store.json").mkdir()

        def pointer_a_folder(test: Bootstrap) -> None:
            env.pointer_path(test.state).mkdir(parents=True)

        def store_a_file(test: Bootstrap) -> None:
            shutil.rmtree(test.state)
            write(test.state / "store", "not a folder")

        def state_a_file(test: Bootstrap) -> None:
            shutil.rmtree(test.state)
            write(test.state, "not a folder")

        cases: dict[str, Callable[[Bootstrap], None]] = {
            "pointer 2": keyed(pointer=2), "pointer 0": keyed(pointer=0), "pointer '1'": keyed(pointer="1"),
            "another interpreter": keyed(python="cpython-27"), "python null": keyed(python=None),
            "another environment's prefix": keyed(prefix=os.path.normcase(str(self.root))),
            "prefix not resolved as the rule says": keyed(prefix=str(env.prefix) + os.sep + "."),
            "the RECORD gone": then(lambda test: env.record.unlink()),
            "the RECORD's time changed": then(stamp_moved),
            "the RECORD's size changed": then(size_changed),
            "record names another file": keyed(record=RECORD.replace("RECORD", "METADATA")),
            "record not a string": keyed(record=5),
            "stamp not a list": keyed(stamp="now"), "stamp of one number": keyed(stamp=[0]),
            "stamp null": keyed(stamp=None),
            "the stored folder gone": keyed(path=str(self.root / "gone")),
            "the stored folder without its marker": then(lambda test: (test.stored / "cad-store.json").unlink()),
            "the marker a folder": then(marker_a_folder),
            "path a number": keyed(path=5), "path null": keyed(path=None), "path a list": keyed(path=[str(self.stored)]),
            "path an object": keyed(path={"path": str(self.stored)}), "path true": keyed(path=True),
            "not JSON": text("{not json"), "empty": text(""), "not UTF-8": text(b"\xff\xfe{\x00"),
            "a list": text("[1, 2]"), "a number": text("1"), "null": text("null"), "a string": text('"pointer"'),
            "the pointer a folder": pointer_a_folder,
            "the store a file": then(store_a_file),
            "the state folder a file": then(state_a_file),
            "the state folder gone": then(lambda test: shutil.rmtree(test.state)),
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                self.fresh()
                case(self)
                self.assertOwn(self.env.probe(state=self.state), name)
                self.assertSilent()

    def test_a_pointer_in_another_state_folder_is_not_this_one_s(self) -> None:
        self.env.point(self.state, self.stored)
        other = self.folder / "other-state"
        self.assertOwn(self.env.probe(state=other))
        self.assertSilent(other)

    def test_a_reinstall_always_runs_what_it_installed(self) -> None:
        """Installing cad again writes its RECORD anew: the pointer of the install before means nothing."""
        self.env.point(self.state, self.stored)
        self.assertTaken(self.env.probe(state=self.state))
        with open(self.env.record, "a", encoding="utf-8") as record:
            record.write("cad/new.py,,\n")
        self.assertOwn(self.env.probe(state=self.state), "new content")
        self.fresh()
        self.env.point(self.state, self.stored)
        kept = self.env.record.stat()
        self.env.install()  # the same bytes, written again
        os.utime(self.env.record, ns=(kept.st_atime_ns, kept.st_mtime_ns + 1_000_000_000))
        self.assertOwn(self.env.probe(state=self.state), "the same content written again, later")
        self.assertSilent()

    def test_imported_late_under_a_cad_already_loaded_it_changes_nothing(self) -> None:
        """Started with ``-S`` no ``.pth`` line runs: the environment's packages folder is put on the path by hand,
        with a pointer for the prefix such a process has (no ``site``: the base interpreter's), so that only the cad
        already loaded keeps the module from taking it -- as it does take it with none loaded."""
        said = self.env.run("-S", "-c", "import sys; print(sys.prefix)", state=self.state)
        prefix = said.stdout.strip()
        stamp = self.env.record.stat()
        write(self.env.pointer_path(self.state, prefix), json.dumps({
            "pointer": 1, "python": self.env.tag, "prefix": os.path.normcase(os.path.realpath(prefix)),
            "record": RECORD, "stamp": [stamp.st_mtime_ns, stamp.st_size], "path": str(self.stored)}))
        for first, expected in (("import cad", [None, True, True, "own"]),
                                ("", [str(self.stored), False, False, "stored"])):
            with self.subTest(first=first or "nothing of cad's"):
                code = textwrap.dedent(f"""
                    import json, sys
                    sys.path.append({str(self.env.packages)!r})
                    {first}
                    before = list(sys.path)
                    import _cad_release
                    import cad
                    print(json.dumps([_cad_release.STORED, _cad_release.HELD is None, sys.path == before, cad.WHO]))
                """)
                found = self.env.run("-S", "-c", code, state=self.state)
                self.assertEqual((found.returncode, found.stderr), (0, ""))
                self.assertEqual(json.loads(found.stdout), expected)

    def test_every_way_of_starting_the_interpreter_takes_it_but_one_that_reads_no_pth(self) -> None:
        self.env.point(self.state, self.stored)
        self.assertTaken(self.env.probe(state=self.state))
        self.assertTaken(self.env.probe("-I", state=self.state), self.env.probe("-I", state=self.folder / "none"))
        found = self.env.run("-m", "cad_server", state=self.state)
        self.assertEqual((found.returncode, found.stdout.strip(), found.stderr), (0, "cad_server stored", ""))
        # A console script: a file its launcher has the environment's interpreter run.
        script = write(Path(self.env.python).parent / "cad-stand-in-script.py",
                       "import sys\nfrom cad_server import main\nsys.exit(main())\n")
        self.addCleanup(script.unlink)
        found = self.env.run(str(script), state=self.state)
        self.assertEqual((found.returncode, found.stdout.strip(), found.stderr), (0, "cad_server stored", ""))
        found = self.env.probe("-S", state=self.state)
        self.assertEqual((found["stored"], found["held"], found["cad"]), (None, False, None),
                         "no site: no .pth line, no pointer, and no packages of the environment's at all")

    def test_a_process_it_starts_by_its_own_interpreter_takes_it_too_with_no_pythonpath(self) -> None:
        self.env.point(self.state, self.stored)
        code = textwrap.dedent(f"""
            import json, os, subprocess, sys
            child = subprocess.run([sys.executable, "-c", {PROBE!r}], capture_output=True, text=True)
            print(json.dumps([os.environ.get("PYTHONPATH"), child.returncode, child.stderr, json.loads(child.stdout)]))
        """)
        found = self.env.run("-c", code, state=self.state)
        self.assertEqual((found.returncode, found.stderr), (0, ""))
        pythonpath, code, said, child = json.loads(found.stdout)
        self.assertEqual((pythonpath, code, said), (None, 0, ""))
        self.assertTaken(child)

    def holder(self) -> subprocess.Popen:
        """A process of the environment that took the pointer and lives until its standard input closes."""
        self.env.point(self.state, self.stored)
        child = subprocess.Popen([self.env.python, "-c", "import sys, _cad_release as r; print(r.STORED, flush=True); "
                                  "sys.stdin.readline()"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                 env=child_environment(self.state), cwd=self.env.prefix)
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.wait, SECONDS)
        self.addCleanup(child.stdin.close)
        self.assertEqual(child.stdout.readline().strip(), str(self.stored))
        return child

    def ended(self, child: subprocess.Popen) -> None:
        child.stdin.close()
        self.assertEqual(child.wait(SECONDS), 0)
        child.stdout.close()

    @unittest.skipIf(os.name == "nt", "POSIX holds the marker by a lock; Windows by the open file, tested below")
    def test_a_process_that_took_it_holds_its_marker_until_it_ends(self) -> None:
        import fcntl

        child = self.holder()
        with open(self.stored / "cad-store.json", "rb") as marker:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(marker, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.ended(child)
            fcntl.flock(marker, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @unittest.skipIf(os.name != "nt", "Windows refuses the folder's rename while a file in it is open")
    def test_a_process_that_took_it_keeps_its_folder_from_being_renamed_until_it_ends(self) -> None:
        import time

        child = self.holder()
        aside = self.stored.with_name(self.stored.name + "-aside")
        with self.assertRaises(PermissionError):
            os.rename(self.stored, aside)
        self.ended(child)
        deadline = time.monotonic() + SECONDS  # a scanner may read the folder a moment after the process ends
        while True:
            try:
                os.rename(self.stored, aside)
                break
            except PermissionError:
                if time.monotonic() > deadline:
                    raise
        os.rename(aside, self.stored)

    @unittest.skipIf(os.name == "nt", "a lock only the store takes, to remove a release: POSIX's")
    def test_a_marker_locked_by_the_store_is_not_taken_and_the_start_does_not_wait(self) -> None:
        import fcntl

        self.env.point(self.state, self.stored)
        with open(self.stored / "cad-store.json", "rb") as marker:
            fcntl.flock(marker, fcntl.LOCK_EX)
            self.assertOwn(self.env.probe(state=self.state))  # bounded by ``SECONDS``: a wait here would hang
            self.assertSilent()
        self.assertTaken(self.env.probe(state=self.state))

    @unittest.skipIf(os.name == "nt", "a symbolic link to a folder needs a privilege on Windows")
    def test_the_environment_reached_through_a_symbolic_link_finds_its_pointer(self) -> None:
        link = self.folder / "linked-env"
        os.symlink(self.env.prefix, link, target_is_directory=True)
        python = str(link / Path(self.env.python).relative_to(self.env.prefix))
        self.env.point(self.state, self.stored)
        found = self.env.probe(state=self.state, python=python)
        self.assertEqual((found["cad"], found["stored"], found["held"]), ("stored", str(self.stored), True))
        self.assertTrue(found["prefix"].startswith(str(link)), "the environment as the link names it")

    def test_a_pointer_that_will_not_open_is_tried_again_a_moment_later_then_left(self) -> None:
        """On Windows a file cannot be opened for the moment another is renamed over it, so a pointer that exists but
        will not open is read again a few milliseconds apart, then taken for none; one that is not there is none at
        once. Counted by a ``.pth`` read before ``cad.pth`` that notes each ``time.sleep``: no clock is read."""
        counter = write(self.env.packages / "sleeps.py", (
            "import time\n\nwaits = []\nsleep = time.sleep\n\n\ndef noted(seconds):\n    waits.append(seconds)\n"
            "    sleep(seconds)\n\n\ntime.sleep = noted\n"))
        line = write(self.env.packages / "a-count-sleeps.pth", "import sleeps\n")
        self.addCleanup(counter.unlink)
        self.addCleanup(line.unlink)
        code = "import json, sys; print(json.dumps(sys.modules['sleeps'].waits))"
        self.env.pointer_path(self.state).mkdir(parents=True)  # there, and no file to open: an OSError of its own
        found = self.env.run("-c", code, state=self.state)
        self.assertEqual((found.returncode, found.stderr, json.loads(found.stdout)), (0, "", [0.0, 0.002, 0.01, 0.05]))
        own = self.env.probe(state=self.state)
        self.assertEqual((own["cad"], own["stored"], own["held"]), ("own", None, False))
        self.assertSilent()
        found = self.env.run("-c", code, state=self.folder / "no-pointer")
        self.assertEqual((found.returncode, found.stderr, json.loads(found.stdout)), (0, "", []), "none: no wait")

    def test_imported_from_a_folder_not_on_the_import_path_it_takes_nothing_and_holds_nothing(self) -> None:
        """Its marker opened and closed again: the folder it would put in its own place is not on the path."""
        said = self.env.run("-S", "-c", "import sys; print(sys.prefix)", state=self.state)
        prefix = said.stdout.strip()
        stamp = self.env.record.stat()
        write(self.env.pointer_path(self.state, prefix), json.dumps({
            "pointer": 1, "python": self.env.tag, "prefix": os.path.normcase(os.path.realpath(prefix)),
            "record": RECORD, "stamp": [stamp.st_mtime_ns, stamp.st_size], "path": str(self.stored)}))
        code = textwrap.dedent(f"""
            import importlib.util, json, os, sys
            spec = importlib.util.spec_from_file_location("_cad_release", {str(self.env.packages / "_cad_release.py")!r})
            module = importlib.util.module_from_spec(spec)
            sys.modules["_cad_release"] = module
            before = list(sys.path)
            spec.loader.exec_module(module)
            stored = {str(self.stored)!r}
            if os.name == "nt":
                os.rename(stored, stored + "-aside")  # refused while a file in it is open
                os.rename(stored + "-aside", stored)
            else:
                import fcntl
                with open(os.path.join(stored, "cad-store.json"), "rb") as marker:
                    fcntl.flock(marker, fcntl.LOCK_EX | fcntl.LOCK_NB)  # refused while it is held, here too
            print(json.dumps([module.STORED, module.HELD, sys.path == before]))
        """)
        found = self.env.run("-S", "-c", code, state=self.state)
        self.assertEqual((found.returncode, found.stderr), (0, ""))
        self.assertEqual(json.loads(found.stdout), [None, None, True])

    def test_with_no_state_folder_named_the_pointer_is_in_the_platform_s_place(self) -> None:
        home = self.folder / "home"
        home.mkdir()
        homes = {"HOME": str(home), "USERPROFILE": str(home)}
        if sys.platform == "darwin":
            places = {"no XDG_STATE_HOME": ({}, home / "Library" / "Application Support" / "cad"),
                      "XDG_STATE_HOME, which macOS ignores": ({"XDG_STATE_HOME": str(self.folder / "xdg")},
                                                               home / "Library" / "Application Support" / "cad")}
        else:
            places = {"no XDG_STATE_HOME": ({}, home / ".local" / "state" / "cad"),
                      "XDG_STATE_HOME": ({"XDG_STATE_HOME": str(self.folder / "xdg")}, self.folder / "xdg" / "cad")}
        for name, (extra, state) in places.items():
            with self.subTest(place=name):
                self.env.point(state, self.stored)
                self.assertTaken(self.env.probe(state=None, env=child_environment(None, **homes, **extra)))
                self.env.pointer_path(state).unlink()
                self.assertOwn(self.env.probe(state=None, env=child_environment(None, **homes, **extra)))


class Contract(unittest.TestCase):
    """What the reader reads, pinned. ``_cad_release`` ships once in every environment cad is installed into and is
    never replaced by an update, so every name and rule here is read by releases already on people's computers: none
    of them may ever change, and the store, which writes what it reads, must keep to them."""

    @classmethod
    def setUpClass(cls) -> None:
        scratch = temporary_directory(prefix="cad-release-contract-")
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name).resolve()
        cls.env = Environment(cls.root / "env")

    def test_the_names_the_state_folder_s_rule_the_pointer_s_name_and_its_six_keys(self) -> None:
        import _cad_release

        from cad.engine import places
        from cad_server._internal import store

        self.assertEqual((_cad_release.STORE, _cad_release.MARKER), ("store", "cad-store.json"))
        self.assertEqual((store.FOLDER, store.MARKER), (_cad_release.STORE, _cad_release.MARKER))

        # Where the pointer is: <state folder>/store/pointer-<crc32 of the environment's folder>.json, as the reader
        # running in the environment computes it, and as the store does for that environment.
        state = self.root / "state"
        said = self.env.run("-c", "import _cad_release; print(_cad_release.pointer())", state=state)
        self.assertEqual((said.returncode, said.stderr), (0, ""))
        expected = state / "store" / pointer_name(self.env.prefix)
        self.assertEqual(said.stdout.strip(), str(expected))
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(state)}):
            self.assertEqual(store.pointer_path(self.env.prefix), expected)
            self.assertEqual(_cad_release.pointer(str(self.env.prefix)), str(expected))
            self.assertEqual(Path(store.root()), Path(places.state_dir()) / "store")
        self.assertEqual(store.environment(self.env.prefix), os.path.normcase(os.path.realpath(self.env.prefix)))
        self.assertEqual(_cad_release.environment(str(self.env.prefix)), store.environment(self.env.prefix))

        # The state folder: CAD_STATE_DIR, else the platform's place for state.
        home = self.root / "home"
        default = (home / "Library" / "Application Support" / "cad" if sys.platform == "darwin"
                   else home / ".local" / "state" / "cad")
        xdg = default if sys.platform == "darwin" else self.root / "xdg" / "cad"
        for variables, expected_state in (({"CAD_STATE_DIR": str(state)}, state), ({}, default),
                                          ({"XDG_STATE_HOME": str(self.root / "xdg")}, xdg),
                                          ({"CAD_STATE_DIR": "", "XDG_STATE_HOME": ""}, default)):
            with self.subTest(variables=variables):
                said = self.env.run("-c", "import _cad_release; print(_cad_release.state())", state=None,
                                    env=child_environment(None, HOME=str(home), USERPROFILE=str(home), **variables))
                self.assertEqual(said.stdout.strip(), str(expected_state), said.stderr)

        # The six keys: each one matters, and nothing else is read.
        stored = self.env.store(state / "store" / f"1.0.1-{self.env.tag}")
        self.env.point(state, stored, release="1.0.1", previous=None, at=0, anything={"else": [1]})
        self.assertEqual(self.env.probe(state=state)["stored"], str(stored), "keys it does not read are left alone")
        for key in ("pointer", "python", "prefix", "record", "stamp", "path"):
            with self.subTest(left_out=key):
                self.env.point(state, stored, **{key: LEFT_OUT})
                found = self.env.probe(state=state)
                self.assertEqual((found["stored"], found["cad"]), (None, "own"))
        # JSON's true is Python's 1, so the reader takes ``"pointer": true`` as the format's 1: pinned as it is.
        self.env.point(state, stored, pointer=True)
        self.assertEqual(self.env.probe(state=state)["stored"], str(stored))

    def test_the_state_folder_s_rule_is_the_library_s_own(self) -> None:
        """``_cad_release.state`` repeats ``cad.engine.places.state_dir``'s rule, since nothing of cad's may be
        imported as an interpreter starts: the two must name one folder under every setting, read by a process whose
        variables and home they really are."""
        code = ("import json, _cad_release; from cad.engine import places; "
                "print(json.dumps([_cad_release.state(), str(places.state_dir())]))")
        home = self.root / "home-for-places"
        settings = {"CAD_STATE_DIR": {"CAD_STATE_DIR": str(self.root / "named")},
                    "CAD_STATE_DIR and XDG_STATE_HOME": {"CAD_STATE_DIR": str(self.root / "named"),
                                                         "XDG_STATE_HOME": str(self.root / "xdg")},
                    "XDG_STATE_HOME": {"XDG_STATE_HOME": str(self.root / "xdg")},
                    "neither": {},
                    "both empty": {"CAD_STATE_DIR": "", "XDG_STATE_HOME": ""}}
        for name, variables in settings.items():
            with self.subTest(setting=name):
                env = child_environment(None, HOME=str(home), USERPROFILE=str(home), PYTHONPATH=SOURCE_PATH,
                                        **variables)
                found = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                                       timeout=SECONDS, cwd=self.root)
                self.assertEqual(found.returncode, 0, found.stderr)
                bootstrap, library = json.loads(found.stdout)
                self.assertEqual(bootstrap, library)
        # A folder named with a trailing separator is spelled two ways and is one folder: the pointer the same file.
        env = child_environment(None, PYTHONPATH=SOURCE_PATH, CAD_STATE_DIR=str(self.root / "named") + os.sep)
        found = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=SECONDS)
        bootstrap, library = json.loads(found.stdout)
        self.assertEqual(os.path.normpath(bootstrap), library)


if __name__ == "__main__":
    unittest.main()
