from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


_PRELUDE = """
import contextlib
import json
import sys
from unittest import mock

from cadgen import authoring
from cadgen import step
from cadgen.daemon import executors

class Captured:
    def __init__(self, *, error=None):
        self.error = error
        self.finished = []
        self.waits = 0
    def _finish(self, code):
        self.finished.append(code)
    def wait_result(self):
        self.waits += 1
        if self.error:
            raise self.error
        return "checked-tree"

captured = Captured()
@contextlib.contextmanager
def capture_source_result(_ref):
    yield captured

@step(out="part.step")
def part():
    raise AssertionError("the mocked top-level build must not execute the body")
"""


class DiscardedModelResultTests(unittest.TestCase):
    def run_source(self, body: str, *, command_string: bool = False) -> dict[str, object]:
        source = textwrap.dedent(_PRELUDE + "\n" + body)
        env = os.environ.copy()
        package = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src"
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(package), env.get("PYTHONPATH", "")]))
        if command_string:
            argv = [sys.executable, "-c", source]
            cwd = None
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            script = Path(temporary.name) / "main.py"
            script.write_text(source, encoding="utf-8")
            argv = [sys.executable, str(script)]
            cwd = temporary.name
        completed = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json_from_last_line(completed.stdout)

    def test_real_main_bare_call_waits_for_receipt_without_importing_lazy_geometry(self) -> None:
        result = self.run_source("""
class BlockLazy:
    def find_spec(self, fullname, _path=None, _target=None):
        if fullname == "cadgen.store.lazy" or fullname == "build123d" or fullname.startswith("OCP"):
            raise AssertionError("discarded result imported native/materialization code: " + fullname)
        return None

for loaded in list(sys.modules):
    if loaded == "cadgen.store.lazy" or loaded == "build123d" or loaded.startswith("OCP"):
        sys.modules.pop(loaded, None)
sys.meta_path.insert(0, BlockLazy())
with mock.patch.object(authoring, "_build", return_value=0), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    part()
print(json.dumps({"waits": captured.waits, "finished": captured.finished,
                  "lazyImported": "cadgen.store.lazy" in sys.modules}))
""")
        self.assertEqual(result, {"waits": 1, "finished": [0], "lazyImported": False})

    def test_assigned_and_nested_returns_materialize(self) -> None:
        result = self.run_source("""
materialized = mock.Mock(side_effect=["assigned-shape", "nested-shape"])
with mock.patch.object(authoring, "_build", return_value=0), \\
     mock.patch.object(authoring, "_built_geometry", materialized), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    assigned = part()
    nested = (lambda value: value)(part())
print(json.dumps({"assigned": assigned, "nested": nested,
                  "calls": materialized.call_count, "waits": captured.waits}))
""")
        self.assertEqual(result, {
            "assigned": "assigned-shape", "nested": "nested-shape", "calls": 2, "waits": 2,
        })

    def test_command_string_declines_the_shortcut(self) -> None:
        result = self.run_source("""
materialized = mock.Mock(return_value="interactive-shape")
with mock.patch.object(authoring, "_build", return_value=0), \\
     mock.patch.object(authoring, "_built_geometry", materialized), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    part()
print(json.dumps({"calls": materialized.call_count, "waits": captured.waits}))
""", command_string=True)
        self.assertEqual(result, {"calls": 1, "waits": 1})

    def test_synthetic_main_globals_decline_the_shortcut(self) -> None:
        result = self.run_source("""
materialized = mock.Mock(return_value="synthetic-shape")
namespace = {"__name__": "__main__", "__file__": __file__, "part": part}
with mock.patch.object(authoring, "_build", return_value=0), \\
     mock.patch.object(authoring, "_built_geometry", materialized), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    exec(compile("part()", __file__, "exec"), namespace)
print(json.dumps({"calls": materialized.call_count, "waits": captured.waits}))
""")
        self.assertEqual(result, {"calls": 1, "waits": 1})

    def test_real_main_bare_call_can_use_a_model_imported_from_another_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "model_lib.py").write_text(textwrap.dedent("""
                from cadgen import step
                @step(out="part.step")
                def part():
                    raise AssertionError("mocked build must not execute")
            """), encoding="utf-8")
            (root / "main.py").write_text(textwrap.dedent("""
                import contextlib
                import json
                from unittest import mock
                from cadgen import authoring
                from cadgen.daemon import executors
                from model_lib import part
                class Captured:
                    def _finish(self, code): self.code = code
                    def wait_result(self): return "checked-tree"
                captured = Captured()
                @contextlib.contextmanager
                def capture_source_result(_ref): yield captured
                materialized = mock.Mock(return_value="unexpected")
                with mock.patch.object(authoring, "_build", return_value=0), \\
                     mock.patch.object(authoring, "_built_geometry", materialized), \\
                     mock.patch.object(executors, "capture_source_result", capture_source_result):
                    part()
                print(json.dumps({"materialized": materialized.call_count, "code": captured.code}))
            """), encoding="utf-8")
            env = os.environ.copy()
            package = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src"
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(package), env.get("PYTHONPATH", "")]))
            completed = subprocess.run(
                [sys.executable, str(root / "main.py")], cwd=root, env=env,
                text=True, capture_output=True, timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json_from_last_line(completed.stdout), {"materialized": 0, "code": 0})

    def test_trace_profile_and_monitoring_tools_decline_the_shortcut(self) -> None:
        result = self.run_source("""
materialized = mock.Mock(return_value="observed-shape")
def trace(_frame, _event, _arg):
    return trace
with mock.patch.object(authoring, "_build", return_value=0), \\
     mock.patch.object(authoring, "_built_geometry", materialized), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    sys.settrace(trace)
    try:
        part()
    finally:
        sys.settrace(None)
    sys.setprofile(lambda *_args: None)
    try:
        part()
    finally:
        sys.setprofile(None)
    monitoring = getattr(sys, "monitoring", None)
    if monitoring is not None:
        monitoring.use_tool_id(5, "cadgen-test")
        try:
            part()
        finally:
            monitoring.free_tool_id(5)
print(json.dumps({"calls": materialized.call_count, "waits": captured.waits,
                  "monitoring": monitoring is not None}))
""")
        expected = 3 if result["monitoring"] else 2
        self.assertEqual(result["calls"], expected)
        self.assertEqual(result["waits"], expected)

    def test_build_and_source_result_failures_stay_observable(self) -> None:
        result = self.run_source("""
materialized = mock.Mock(return_value="unreachable")
exit_code = None
with mock.patch.object(authoring, "_build", return_value=7), \\
     mock.patch.object(authoring, "_built_geometry", materialized), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    try:
        part()
    except SystemExit as error:
        exit_code = error.code
captured.error = RuntimeError("source receipt failed")
source_error = ""
with mock.patch.object(authoring, "_build", return_value=0), \\
     mock.patch.object(authoring, "_built_geometry", materialized), \\
     mock.patch.object(executors, "capture_source_result", capture_source_result):
    try:
        part()
    except RuntimeError as error:
        source_error = str(error)
print(json.dumps({"exit": exit_code, "sourceError": source_error,
                  "materialized": materialized.call_count, "finished": captured.finished}))
""")
        self.assertEqual(result, {
            "exit": 7,
            "sourceError": "source receipt failed",
            "materialized": 0,
            "finished": [7, 0],
        })


def json_from_last_line(output: str) -> dict[str, object]:
    import json
    return json.loads(output.strip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
