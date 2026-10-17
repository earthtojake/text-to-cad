"""A child a parent's body calls is one build, wherever it happens (STORE.md §9a).

Every decorated function goes through the one pipeline: decoded from its stored result
when the store holds one for its inputs as they are, else run -- serially, in the
caller's process, as a build of its own with scopes of its own. So a child built inside
its parent is the child built alone (same tree, same closure), a parent is the same build
whether its child was decoded or run, a child's data file is the child's input and not its
parent's, a child runs once per run however often it is called, and its failure reaches the
body as itself and fails the run.
"""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import executors  # noqa: E402

CHILD = """\
from pathlib import Path

from cadgen import step
from cadgen import build123d as bd


@step
def child():
    size = float(Path(__file__).with_name("size.txt").read_text(encoding="utf-8"))
    return bd.Box(size, 3.0, 2.0)
"""

PARENT = """\
from cadgen import step
from cadgen import build123d as bd
from child import child


@step
def parent():
    piece = child()
    again = child()
    return bd.Compound(children=[bd.Pos(8, 0, 0) * piece, bd.Pos(-8, 0, 0) * again], label="parent")
"""

GRAND = """\
from cadgen import step
from cadgen import build123d as bd
from child import child
from parent import parent


@step
def grand():
    return bd.Compound(children=[parent(), bd.Pos(0, 20, 0) * child()], label="grand")
"""


DYN_CHILD = """\
import importlib
from cadgen import step
from cadgen import build123d as bd


@step
def child():
    plug = importlib.import_module("plug")
    return bd.Box(plug.VALUE, 3.0, 2.0)
"""

DYN_PARENT = """\
import importlib
from cadgen import step
from cadgen import build123d as bd
from dyn_child import child


@step
def parent():
    piece = child()
    plug = importlib.import_module("plug")
    return bd.Compound(children=[bd.Pos(plug.VALUE * 4, 0, 0) * piece], label="parent")
"""


class SerialChildrenCase(unittest.TestCase):
    """A child, its parent and a grandparent in one folder, each run as ``python x.py``
    with no daemon and a store of its own."""

    def setUp(self):
        temporary = generated_cad_directory(prefix="serial-children-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "size.txt").write_text("4.0", encoding="utf-8")
        for name, source in (("child", CHILD), ("parent", PARENT), ("grand", GRAND)):
            (self.root / f"{name}.py").write_text(source, encoding="utf-8")
        self.child, self.parent, self.grand = (self.root / f"{name}.py" for name in ("child", "parent", "grand"))
        self.stores = 0
        self.use_store(self.root / "store")
        self.events: list[dict] = []
        executors.set_event_sink(self.events.append)
        self.addCleanup(executors.set_event_sink, None)

    def use_store(self, store: Path) -> None:
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(store), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)

    def fresh_store(self) -> None:
        self.stores += 1
        self.use_store(self.root / f"store-{self.stores}")

    def build(self, script: Path, *flags: str) -> tuple[int, str]:
        from cadgen.cli._run_model import run_model_argv

        self.events.clear()
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = run_model_argv([str(script), *flags])
        return code, err.getvalue()

    def done(self) -> list[str]:
        return [Path(e["model"]).stem for e in self.events if e.get("state") == "done"]

    def record(self, script: Path) -> dict:
        from cadgen.store.records import read_record

        record = read_record(script)
        self.assertIsNotNone(record, f"{script.name} has no record")
        return record

    def current(self) -> list[str]:
        return [Path(e["model"]).stem for e in self.events if e.get("state") == "current"]


class SerialChildren(SerialChildrenCase):
    def test_a_child_built_inside_its_parent_is_the_child_built_alone(self):
        code, err = self.build(self.child)
        self.assertEqual(code, 0, err)
        alone = self.record(self.child)
        self.fresh_store()
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.done()), ["child", "parent"])
        nested = self.record(self.child)
        self.assertEqual(nested["tree"], alone["tree"])
        self.assertEqual(nested["closure"]["hash"], alone["closure"]["hash"])
        self.assertEqual(sorted(nested["closure"]["files"]), sorted(alone["closure"]["files"]))
        self.assertIn("size.txt", nested["closure"]["files"])
        self.assertTrue((self.root / "child.step").is_file(), "the child built inside its parent wrote no STEP")

    def test_a_parent_is_the_same_build_whether_its_child_was_run_or_decoded(self):
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.done()), ["child", "parent"])
        miss, document = self.record(self.parent), (self.root / "parent.step").read_bytes()
        # --force rebuilds the root only: the child is current, so it is decoded.
        code, err = self.build(self.parent, "--force")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.done(), ["parent"])
        self.assertEqual(self.current(), ["child"])
        hit = self.record(self.parent)
        self.assertEqual(hit["tree"], miss["tree"])
        self.assertEqual(hit["closure"]["hash"], miss["closure"]["hash"])
        self.assertEqual(hit["children"], miss["children"])
        self.assertEqual((self.root / "parent.step").read_bytes(), document)

    def test_a_childs_data_file_is_its_own_input_and_the_parent_follows_the_child(self):
        from cadgen.store.gate import stale

        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        parent, child = self.record(self.parent), self.record(self.child)
        self.assertNotIn("size.txt", parent["closure"]["files"])
        self.assertIn("size.txt", child["closure"]["files"])
        self.assertEqual({c["model"] for c in parent["children"]}, {f"{self.child}::child"})
        self.assertEqual({c["key"] for c in parent["children"]}, {child["key"]})
        (self.root / "size.txt").write_text("6.0", encoding="utf-8")
        self.assertEqual(stale(self.child).reason(), "closure changed: size.txt")
        verdict = stale(self.parent)
        self.assertTrue(verdict.stale)
        self.assertFalse(next(c for c in verdict.clauses if c["clause"] == 2)["stale"], "the parent's own closure is unchanged")
        self.assertRegex(verdict.reason(), r"^child stale: child\.py")
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.done()), ["child", "parent"])
        self.assertNotEqual(self.record(self.parent)["tree"], parent["tree"])
        self.assertFalse(stale(self.parent).stale)

    def test_a_child_runs_once_per_run_however_often_it_is_called(self):
        code, err = self.build(self.grand)
        self.assertEqual(code, 0, err)
        # grand calls child and parent, and parent calls child twice: one build of each.
        self.assertEqual(sorted(self.done()), ["child", "grand", "parent"])
        self.assertEqual({c["model"] for c in self.record(self.grand)["children"]},
                         {f"{self.parent}::parent", f"{self.child}::child"})
        self.assertEqual({c["model"] for c in self.record(self.parent)["children"]}, {f"{self.child}::child"})
        parents = {Path(e["model"]).stem: e.get("parent") for e in self.events if e.get("state") == "done"}
        self.assertEqual(Path(parents["child"]).name, "parent.py", "the child's build is reported under its first caller")
        self.assertEqual(Path(parents["parent"]).name, "grand.py")

    def test_a_child_has_one_tree_and_key_with_the_memo_cold_hot_or_off(self):
        """The kernel memo's hits change no identity: a cold run, a hot one (a second run in
        this process, every construction a hit) and one with hits off (``CADGEN_KERNEL_MEMO=0``)
        store the same tree under the same key."""
        code, err = self.build(self.child)
        self.assertEqual(code, 0, err)
        cold = self.record(self.child)
        code, err = self.build(self.child, "--force")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.done(), ["child"], "--force ran the body again, hot")
        hot = self.record(self.child)
        self.fresh_store()
        with mock.patch.dict(os.environ, {"CADGEN_KERNEL_MEMO": "0"}):
            code, err = self.build(self.child)
        self.assertEqual(code, 0, err)
        off = self.record(self.child)
        self.assertEqual((hot["tree"], hot["key"]), (cold["tree"], cold["key"]))
        self.assertEqual((off["tree"], off["key"]), (cold["tree"], cold["key"]))

    def test_a_childs_failure_reaches_the_body_as_itself_and_fails_the_run(self):
        self.child.write_text(
            "from cadgen import step\n\n\n@step\ndef child():\n    raise ValueError('the size is wrong on purpose')\n",
            encoding="utf-8",
        )
        self.parent.write_text(
            "from cadgen import step\nfrom cadgen import build123d as bd\nfrom child import child\n\n\n"
            "@step\ndef parent():\n    try:\n        child()\n    except ValueError as exc:\n"
            "        raise RuntimeError(f'caught {type(exc).__name__}: {exc}')\n    return bd.Box(1, 1, 1)\n",
            encoding="utf-8",
        )
        code, err = self.build(self.parent)
        self.assertNotEqual(code, 0)
        self.assertIn("caught ValueError: the size is wrong on purpose", err)
        self.assertEqual([Path(e["model"]).stem for e in self.events if e.get("state") == "failed"], ["child", "parent"])

    def test_a_model_may_not_depend_on_itself(self):
        (self.root / "left.py").write_text(
            "from cadgen import step\nfrom cadgen import build123d as bd\n\n\n@step\ndef left():\n"
            "    from right import right\n    return right()\n", encoding="utf-8")
        (self.root / "right.py").write_text(
            "from cadgen import step\nfrom cadgen import build123d as bd\n\n\n@step\ndef right():\n"
            "    from left import left\n    return left()\n", encoding="utf-8")
        code, err = self.build(self.root / "left.py")
        self.assertNotEqual(code, 0)
        self.assertIn("a model may not depend on itself", err)


class HitsHealTheTree(SerialChildrenCase):
    """A current model's hit heals what its children owe, restores a child brought back
    to a state already built, and records one closure whether its child ran or was
    decoded (STORE.md §3, §4)."""

    def test_a_run_of_the_root_heals_what_a_grandchild_owes(self):
        code, err = self.build(self.grand)
        self.assertEqual(code, 0, err)
        written = (self.root / "child.step").read_bytes()
        (self.root / "child.step").unlink()
        code, err = self.build(self.grand)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.done(), [], "a missing file ran a body")
        self.assertIn("child.step is missing; writing it again", err)
        self.assertEqual((self.root / "child.step").read_bytes(), written)
        self.assertEqual(self.current(), ["child", "parent", "grand"], "the tree is healed children first")

    def test_a_child_brought_back_to_a_state_already_built_makes_its_parent_a_hit(self):
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        first = {name: self.record(path)["key"] for name, path in (("child", self.child), ("parent", self.parent))}
        files = {name: (self.root / f"{name}.step").read_bytes() for name in first}
        (self.root / "size.txt").write_text("5.0", encoding="utf-8")
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.done()), ["child", "parent"])
        self.assertNotEqual(self.record(self.child)["key"], first["child"])
        # Back: the child's stored result answers for its source as it is now, so the
        # parent stands too (clause 3); its hit restores the child, and no body runs.
        (self.root / "size.txt").write_text("4.0", encoding="utf-8")
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.done(), [], "the revert ran a body")
        self.assertEqual(self.current(), ["child", "parent"])
        self.assertIn("restored", err)
        saved = [e for e in self.events if e.get("saved")]
        self.assertTrue(saved and all(isinstance(e.get("elapsed"), float) for e in saved),
                        "a restored model's saved event carries an elapsed too")
        for name, path in (("child", self.child), ("parent", self.parent)):
            self.assertEqual(self.record(path)["key"], first[name], f"{name} is not at its first key")
            self.assertEqual((self.root / f"{name}.step").read_bytes(), files[name], f"{name}.step is not the first build's")
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual((self.done(), self.current()), ([], ["child", "parent"]))
        self.assertNotIn("writing it again", err)

    def test_a_parent_records_one_closure_whether_its_child_ran_or_was_decoded(self):
        """A helper both bodies import dynamically: on a miss the child's scope executes it
        first, so unless that scope evicts what it ran first, the parent's import finds it
        loaded, executes nothing, and the parent's closure misses what a hit run -- the
        child decoded, the parent importing the helper itself -- records."""
        (self.root / "plug.py").write_text("VALUE = 3.0\n", encoding="utf-8")
        child, parent = self.root / "dyn_child.py", self.root / "dyn_parent.py"
        child.write_text(DYN_CHILD, encoding="utf-8")
        parent.write_text(DYN_PARENT, encoding="utf-8")
        code, err = self.build(parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.done()), ["dyn_child", "dyn_parent"])
        miss = self.record(parent)["closure"]
        code, err = self.build(parent, "--force")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.done(), self.current()), (["dyn_parent"], ["dyn_child"]))
        hit = self.record(parent)["closure"]
        self.assertIn("plug.py", miss["files"])
        self.assertEqual((sorted(miss["files"]), miss["hash"]), (sorted(hit["files"]), hit["hash"]))


class QueuedExports(SerialChildrenCase):
    """A call's files are queued as its result is recorded and finished by the run that
    owns the command, children first: a child's STEP is written while its parent's body
    goes on, the command's result is printed once every file is written, and an export
    that fails fails the command, keeps the file on disk and is owed to the next run,
    which exports it without running the body (STORE.md §3, *Exports*; §9a)."""

    def test_a_childs_file_lands_after_its_done_and_before_the_result_is_printed(self):
        from cadgen.cli._run_model import run_model_argv

        class Stdout(io.StringIO):
            """Notes, as the result line is printed, how many files had been saved."""

            def write(self, text):
                if text.startswith('{"ok":'):
                    saved_first.append(len([e for e in self.events if e.get("saved")]))
                return super().write(text)

        saved_first: list[int] = []
        out = Stdout()
        out.events = self.events
        self.events.clear()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(run_model_argv([str(self.grand), "--json"]), 0, err.getvalue())
        events = list(self.events)
        for name in ("child", "parent", "grand"):
            done = next(i for i, e in enumerate(events) if e.get("state") == "done" and Path(e["model"]).stem == name)
            saved = next(i for i, e in enumerate(events) if e.get("saved") and Path(e["model"]).stem == name)
            self.assertLess(done, saved, f"{name}: its result is recorded before its file is written")
            self.assertIn("elapsed", events[saved], f"{name}: its saved event carries the build clock's elapsed")
            self.assertGreaterEqual(events[saved]["elapsed"], events[done]["elapsed"],
                                    f"{name}: its saved event reads the clock its done event reads")
            self.assertTrue((self.root / f"{name}.step").is_file())
        order = [Path(e["model"]).stem for e in events if e.get("saved")]
        self.assertEqual(order, ["child", "parent", "grand"], "children's files land first, as queued")
        self.assertEqual(saved_first, [3], "the result line follows the last file written")

    def test_verbose_names_the_moment_each_file_landed_in_the_order_they_did(self):
        code, err = self.build(self.parent, "--verbose")
        self.assertEqual(code, 0, err)
        landed = [line.split()[3] for line in err.splitlines() if line.startswith("[cadgen] STEP saved ")]
        self.assertEqual(landed, ["child.step", "parent.step"], "children's files land first, as queued")

    def test_a_failed_export_fails_the_command_and_the_next_run_writes_the_file_without_a_run(self):
        from cadgen.store import exports

        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        before = {name: (self.root / f"{name}.step").read_bytes() for name in ("child", "parent")}
        (self.root / "size.txt").write_text("5.0", encoding="utf-8")
        writer = exports.export_step

        def failing(tree, out, **kwargs):
            if Path(out).name == "child.step":
                raise RuntimeError("the export failed on purpose")
            return writer(tree, out, **kwargs)

        with mock.patch.object(exports, "export_step", side_effect=failing):
            code, err = self.build(self.parent)
        self.assertNotEqual(code, 0)
        self.assertIn("the export failed on purpose", err)
        self.assertEqual(sorted(self.done()), ["child", "parent"], "both bodies ran before the export failed")
        self.assertEqual((self.root / "child.step").read_bytes(), before["child"], "the file on disk stays")
        self.assertNotEqual((self.root / "parent.step").read_bytes(), before["parent"], "the other export landed")
        self.assertEqual(self.record(self.child)["outputs"][str(self.root / "child.step")]["sha256"], "",
                         "the record owes the file")
        code, err = self.build(self.parent)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.done(), [], "nothing ran again")
        self.assertIn("child.step was never written; writing it again", err)
        self.assertNotEqual((self.root / "child.step").read_bytes(), before["child"])
        self.assertEqual(self.record(self.child)["outputs"][str(self.root / "child.step")]["sha256"],
                         __import__("hashlib").sha256((self.root / "child.step").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
