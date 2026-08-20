"""The Python<->Node builder bridge.

Every test here spawns a REAL node child running a REAL script that imports the REAL
``implicitjs/glb/progressStream.js`` helper through ``NODE_PATH``. That is deliberate: the
three things this module actually promises -- that bare specifiers resolve through the
exports map, that NDJSON reaches the lock holder, and that no child outlives the lock -- are
all properties of a separate process, and a mocked ``Popen`` proves none of them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import node_runtime  # noqa: E402
from cadgen._internal.node_runtime import (  # noqa: E402
    NodeBuilderError,
    NodeUnavailable,
    cad_node_executable,
    node_child_env,
    node_package_root,
    run_node_builder,
)
from cadgen.coordination import IMPLICIT_PACKAGE, artifact_build  # noqa: E402

_NODE = shutil.which("node")

# The helper is imported by BARE SPECIFIER, so every script below is also a live test of the
# NODE_PATH mechanism: implicitjs/package.json maps "./glb/*" -> "./src/lib/glb/*", and only
# a NODE_PATH entry (not a directory alias) resolves through an exports map.
_IMPORT = (
    'import { reportPhase, reportTotal, reportAdvance, reportResult } '
    'from "implicitjs/glb/progressStream.js";\n'
)


class Recorder:
    """Stands in for the ``BuildRun`` yielded by ``artifact_build``: same surface, but it
    remembers what it was told instead of writing a status record."""

    def __init__(self, *, fail_on_advance: bool = False) -> None:
        self.events: list[tuple] = []
        self.run_id = "recorder"
        self.skipped = False
        self._fail_on_advance = fail_on_advance

    def phase(self, name, *, total=None, detail="") -> None:
        self.events.append(("phase", name, total, detail))

    def set_total(self, total) -> None:
        self.events.append(("total", total))

    def advance(self, count=1, *, detail=None) -> None:
        self.events.append(("advance", count, detail))
        if self._fail_on_advance:
            raise RuntimeError("dispatch exploded")

    def stage_ms_snapshot(self) -> dict:
        return {}


@unittest.skipUnless(_NODE, "node is required for the Node builder bridge tests")
class NodeRuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadnode-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def script(self, body: str, name: str = "builder.mjs") -> Path:
        path = self.root / name
        path.write_text(_IMPORT + body, encoding="utf-8")
        return path

    @staticmethod
    def alive(pid: int) -> bool:
        """Is this pid still running? Signal 0 is the POSIX idiom and not portable.

        Windows has no signal 0: ``os.kill(pid, 0)`` reaches ``TerminateProcess`` with an
        exit code of 0 and raises WinError 87 for the bogus parameter -- an error that reads
        like "the process is gone" and is not. ``OpenProcess`` is the honest question there,
        and ``tasklist`` asks it without ctypes.
        """
        if os.name != "nt":
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                return False
            return True
        listed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        # tasklist prints "INFO: No tasks are running..." rather than an empty table, and
        # exits 0 either way, so the pid has to be looked for in the output.
        return str(pid) in listed.stdout


class ProtocolTest(NodeRuntimeTestCase):
    def test_phase_total_advance_reach_the_run(self):
        script = self.script(
            """
reportPhase("sample", 96);
reportTotal(973214);
reportAdvance(1, "slice 1/96");
reportAdvance(3, "slice 4/96");
reportResult({ ok: true });
"""
        )
        run = Recorder()
        run_node_builder(script, run=run)

        self.assertEqual(
            [
                ("phase", "sample", 96, ""),
                ("total", 973214),
                ("advance", 1, "slice 1/96"),
                ("advance", 3, "slice 4/96"),
            ],
            run.events,
        )

    def test_phase_without_a_total_is_indeterminate(self):
        script = self.script('reportPhase("weld");\nreportResult({ ok: true });\n')
        run = Recorder()
        run_node_builder(script, run=run)
        self.assertEqual([("phase", "weld", None, "")], run.events)

    def test_result_line_becomes_the_return_value(self):
        script = self.script(
            'reportResult({ ok: true, packagePath: "a/b.implicit.glb", triangles: 42 });\n'
        )
        payload = run_node_builder(script, run=Recorder())
        self.assertEqual(
            {"ok": True, "packagePath": "a/b.implicit.glb", "triangles": 42}, payload
        )
        # `type` is protocol framing, not payload: it must not leak into the CLI's JSON line.
        self.assertNotIn("type", payload)

    def test_argv_reaches_the_child(self):
        script = self.script(
            'reportResult({ ok: true, argv: process.argv.slice(2) });\n'
        )
        payload = run_node_builder(
            script, ["--package-dir", str(self.root), "--run-id", "abc"], run=Recorder()
        )
        self.assertEqual(["--package-dir", str(self.root), "--run-id", "abc"], payload["argv"])

    def test_non_json_stdout_is_ignored(self):
        script = self.script(
            """
console.log("hello from some dependency");
console.log("[1, 2, 3]");
console.log("{not json at all");
console.log(JSON.stringify({ type: "unknown-future-thing", files: ["a.js"] }));
console.log(JSON.stringify({ noTypeField: true }));
reportPhase("sample", 2);
reportResult({ ok: true });
"""
        )
        run = Recorder()
        seen: list[dict] = []
        payload = run_node_builder(script, run=run, on_message=seen.append)

        self.assertEqual({"ok": True}, payload)
        self.assertEqual([("phase", "sample", 2, "")], run.events)
        # Well-formed objects the bridge does not understand are offered to the caller and
        # dropped otherwise -- never dispatched, never fatal.
        self.assertEqual(
            [{"type": "unknown-future-thing", "files": ["a.js"]}, {"noTypeField": True}], seen
        )

    def test_malformed_progress_lines_do_not_reach_the_run(self):
        script = self.script(
            """
console.log(JSON.stringify({ type: "phase" }));
console.log(JSON.stringify({ type: "total", total: "lots" }));
reportResult({ ok: true });
"""
        )
        run = Recorder()
        run_node_builder(script, run=run)
        self.assertEqual([], run.events)


class FailureTest(NodeRuntimeTestCase):
    def test_non_zero_exit_raises(self):
        script = self.script(
            """
reportPhase("sample", 4);
process.stderr.write("builder blew up\\n");
process.exit(3);
"""
        )
        with self.assertRaises(NodeBuilderError) as ctx:
            run_node_builder(script, run=Recorder())
        self.assertIn("exit code 3", str(ctx.exception))

    def test_exit_zero_without_a_result_raises(self):
        script = self.script('reportPhase("sample", 4);\n')
        with self.assertRaises(NodeBuilderError) as ctx:
            run_node_builder(script, run=Recorder())
        self.assertIn("no result line", str(ctx.exception))

    def test_missing_script_raises_before_spawning(self):
        with self.assertRaises(NodeBuilderError):
            run_node_builder(self.root / "does-not-exist.mjs", run=Recorder())

    def test_a_child_that_reports_and_then_refuses_to_exit_is_killed(self):
        # The result is terminal by contract, so reading stops there. A builder that keeps
        # running past it would otherwise outlive the lock its parent is about to release.
        script = self.script(
            """
reportResult({ ok: true, pid: process.pid });
setTimeout(() => {}, 600000);
"""
        )
        with mock.patch.object(node_runtime, "_EXIT_GRACE_S", 0.5):
            payload = run_node_builder(script, run=Recorder())

        self.assertTrue(payload["ok"])
        self.assertFalse(self.alive(payload["pid"]), "the Node child outlived its parent scope")

    def test_a_child_is_killed_when_dispatch_raises(self):
        # An exception on the Python side (here: the run object failing) must not leave an
        # orphan writing into a package whose lock is being released on the way out.
        script = self.script(
            """
reportAdvance(1, `pid=${process.pid}`);
setTimeout(() => {}, 600000);
"""
        )
        run = Recorder(fail_on_advance=True)
        with self.assertRaises(RuntimeError):
            run_node_builder(script, run=run)

        pid = int(run.events[0][2].split("=")[1])
        self.assertFalse(self.alive(pid), "the Node child survived an exception in the parent")


class DiscoveryTest(NodeRuntimeTestCase):
    def test_env_override_wins_over_path(self):
        with mock.patch.dict(os.environ, {"CADGEN_NODE": _NODE}, clear=False):
            self.assertEqual(str(Path(_NODE).resolve()), cad_node_executable())

    def test_bad_env_override_raises_rather_than_silently_falling_back(self):
        bogus = str(self.root / "not-node")
        with mock.patch.dict(os.environ, {"CADGEN_NODE": bogus}, clear=False):
            with self.assertRaises(NodeUnavailable) as ctx:
                cad_node_executable()
        self.assertIn("CADGEN_NODE", str(ctx.exception))

    def test_missing_node_raises_an_actionable_error(self):
        cleared = {name: "" for name in node_runtime.NODE_ENV_VARS}
        with mock.patch.dict(os.environ, {**cleared, "PATH": str(self.root)}, clear=False):
            with mock.patch.object(node_runtime.shutil, "which", return_value=None):
                with self.assertRaises(NodeUnavailable) as ctx:
                    cad_node_executable()
        message = str(ctx.exception)
        self.assertIn("node was not found", message)
        self.assertIn("CADGEN_NODE", message)

    def test_node_path_points_at_the_packages_dir_holding_implicitjs(self):
        root = node_package_root()
        self.assertTrue((root / "implicitjs" / "package.json").is_file(), root)
        env = node_child_env()
        self.assertEqual(str(root), env["NODE_PATH"].split(os.pathsep)[0])

    def test_existing_node_path_entries_are_preserved(self):
        with mock.patch.dict(os.environ, {"NODE_PATH": "/somewhere/else"}, clear=False):
            entries = node_child_env()["NODE_PATH"].split(os.pathsep)
        self.assertEqual(str(node_package_root()), entries[0])
        self.assertIn("/somewhere/else", entries)

    def test_bare_specifier_resolves_through_the_exports_map(self):
        # Every script in this file already imports the helper by BARE specifier from a temp
        # dir with no node_modules above it, so they all depend on this. Pinned explicitly
        # because the mechanism is subtle: Node's ESM resolver ignores NODE_PATH, so the
        # bridge's --import hook forwards the miss to the CJS resolver, which reads NODE_PATH
        # AND applies the exports map. "implicitjs/mesh" has no counterpart on disk -- only
        # the map turns it into src/lib/implicitCad/mesh.js -- so resolving it proves the map
        # was consulted rather than a directory path being glued together.
        script = self.script(
            'reportResult({ ok: true, url: import.meta.resolve("implicitjs/mesh") });\n'
        )
        payload = run_node_builder(script, run=Recorder())
        self.assertTrue(
            payload["url"].endswith("/implicitjs/src/lib/implicitCad/mesh.js"), payload["url"]
        )

    def test_node_path_is_what_makes_it_resolve(self):
        # The other half of the claim: with NODE_PATH removed the same import fails. Without
        # this, a stray node_modules somewhere above the temp dir could make the test above
        # pass while the packaged, node_modules-free runtime still broke.
        script = self.script('reportResult({ ok: true });\n')
        with self.assertRaises(NodeBuilderError):
            run_node_builder(script, run=Recorder(), env={"NODE_PATH": ""})

    def test_caller_env_is_overlaid_on_the_child(self):
        script = self.script(
            'reportResult({ ok: true, seen: process.env.CADGEN_TEST_VAR ?? null });\n'
        )
        payload = run_node_builder(script, run=Recorder(), env={"CADGEN_TEST_VAR": "set"})
        self.assertEqual("set", payload["seen"])

    def test_cwd_is_honoured(self):
        sub = self.root / "work"
        sub.mkdir()
        script = self.script('reportResult({ ok: true, cwd: process.cwd() });\n')
        payload = run_node_builder(script, run=Recorder(), cwd=sub)
        self.assertEqual(str(sub.resolve()), str(Path(payload["cwd"]).resolve()))


class ArtifactBuildIntegrationTest(NodeRuntimeTestCase):
    """The real thing: a real lock, a real status record, a real Node child."""

    def test_child_progress_flows_through_a_real_build_run(self):
        package_dir = self.root / "__cadgen__" / "widget.implicit.glb"
        script = self.script(
            """
reportPhase("sample", 4);
for (let i = 1; i <= 4; i += 1) reportAdvance(1, `slice ${i}/4`);
reportPhase("write");
reportResult({ ok: true, packagePath: process.argv[2] });
"""
        )

        events = []
        with artifact_build(
            IMPLICIT_PACKAGE, package_dir, is_current=lambda: False, sink=events.append
        ) as run:
            payload = run_node_builder(script, [str(package_dir)], run=run)

        self.assertEqual(str(package_dir), payload["packagePath"])

        phases = [event.phase for event in events]
        self.assertIn("sample", phases)
        self.assertIn("write", phases)
        self.assertEqual("done", phases[-1])

        sampled = [event for event in events if event.phase == "sample"]
        self.assertTrue(sampled[-1].determinate)
        self.assertEqual(4, sampled[-1].done)
        self.assertEqual(4, sampled[-1].total)
        self.assertEqual("slice 4/4", sampled[-1].detail)

        # The count advanced through the child's work rather than sitting at zero.
        self.assertGreater(sampled[-1].fraction, sampled[0].fraction)
        # And the terminal record carries the phases the CHILD reported, so the run's own
        # timings account for the work it did.
        self.assertIn("sample", events[-1].stage_ms or {})


class StdlibOnlyTest(unittest.TestCase):
    """Same invariant :mod:`cadgen.coordination` is held to, for the same reason.

    The bridge sits beside coordination and is imported by the viewer's producer path; it
    must never be the module that drags OCP/build123d/ezdxf into a long-lived process. Runs
    in a FRESH interpreter -- asserting on ``sys.modules`` in this one would only report what
    the rest of the suite imported first.
    """

    def test_import_pulls_in_no_cad_runtime(self):
        src = str(Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src")
        probe = (
            "import json, sys\n"
            f"sys.path.insert(0, {src!r})\n"
            "import cadgen._internal.node_runtime as m\n"
            "print(json.dumps({\n"
            "    'heavy': sorted(x for x in ('OCP', 'build123d', 'ezdxf') if x in sys.modules),\n"
            "    'has_api': all(hasattr(m, n) for n in "
            "('run_node_builder', 'cad_node_executable', 'node_child_env')),\n"
            "}))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual([], result["heavy"])
        self.assertTrue(result["has_api"])


if __name__ == "__main__":
    unittest.main()


class BuilderErrorMessageTests(unittest.TestCase):
    """A failed Node builder must carry its reason back to the caller.

    stderr used to be inherited, so the builder's own diagnostic went to whatever console
    the producer owned. For a viewer-triggered build that is a server log the user never
    sees, and the error they got named no cause -- it said "see stderr above".
    """

    def test_the_message_line_is_preferred_over_stack_frames(self) -> None:
        lines = [
            "Error: Unsupported DXF entity HATCH",
            "    at parseDxf (file:///x/parseDxf.js:139:11)",
            "    at main (file:///x/dxf-artifact.mjs:83:19)",
        ]
        self.assertEqual("Unsupported DXF entity HATCH", node_runtime.first_builder_error(lines))

    def test_a_message_without_the_error_prefix_still_reports_something(self) -> None:
        self.assertEqual("something broke", node_runtime.first_builder_error(["something broke"]))

    def test_stack_only_output_does_not_report_a_frame_as_the_cause(self) -> None:
        self.assertEqual("", node_runtime.first_builder_error(["    at main (x.js:1:1)"]))

    def test_no_stderr_reports_nothing_rather_than_inventing_a_cause(self) -> None:
        self.assertEqual("", node_runtime.first_builder_error([]))
