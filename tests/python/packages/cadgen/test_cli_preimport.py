"""What must happen BEFORE the heavy imports, at both front doors.

`cadgen <command>` dispatch hands off to the warm daemon before importing the
command's module (the daemon exists to avoid paying the multi-second
OCP/build123d import per invocation). Directly-run model scripts do the same
inside the @step/@dxf decorator (cadgen.authoring).

The decorator used to own one more pre-import ritual: a COLD @dxf run re-ran
itself with PYTHONHASHSEED pinned, because ezdxf's emitted order followed string
hashing. The engine's emitter makes DXF bytes a function of the drawing's
geometry instead, so that re-exec is gone and its absence is now the thing
worth testing — a returning re-exec would double every drawing's cold cost.

None of this is testable by calling a command's `main()`; it is a property of
dispatch and of the decorator.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import cadgen.cli as cli  # noqa: E402
from cadgen import authoring  # noqa: E402


class DaemonHandoff(unittest.TestCase):
    def test_every_routed_command_has_a_tool_the_daemon_knows(self):
        # A command mapped to a name the daemon does not import would fail at runtime
        # with nothing useful; this is the only place the two registries meet. "run"
        # is served without a cadgen.cli command: its front door is the @step/@dxf
        # decorator on a directly-executed model script.
        from cadgen.daemon import server

        self.assertEqual(set(cli._DAEMON_TOOLS.values()) | {"run"}, set(server._TOOL_IMPORTS))

    def test_the_served_set_is_the_non_generation_build_and_review_tools(self):
        # Generation has no CLI (library-first): model scripts dispatch themselves
        # via the decorator, so dispatch serves the document/mesh build doors plus
        # the two review tools. Every mesh door is warm: `step export` served all
        # three formats from one spawn, and three doors are three spawns. There is
        # no `dxf build` to serve — a drawing is made by running its script.
        self.assertEqual(
            set(cli._DAEMON_TOOLS),
            {
                "step build",
                "step compile",
                "step inspect",
                "step snapshot",
                "stl build",
                "3mf build",
                "glb build",
            },
        )

    def test_a_step_command_hands_off_and_never_imports_the_module(self):
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "1"}, clear=False), \
                mock.patch("cadgen.daemon.client.run_via_daemon", return_value=7) as daemon, \
                mock.patch.object(cli.importlib, "import_module") as imported:
            self.assertEqual(cli.main(["stl", "build", "part.step"]), 7)
        daemon.assert_called_once()
        self.assertEqual(daemon.call_args.args[0], "stl-build")
        self.assertEqual(daemon.call_args.args[1], ["part.step"])
        imported.assert_not_called()  # the whole point: no OCP import

    def test_a_daemon_that_declines_falls_through_to_the_module(self):
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "1"}, clear=False), \
                mock.patch("cadgen.daemon.client.run_via_daemon", return_value=None), \
                mock.patch.object(cli.importlib, "import_module") as imported:
            imported.return_value.main.return_value = 0
            self.assertEqual(cli.main(["stl", "build", "part.step"]), 0)
        imported.assert_called_once()

    def test_no_handoff_when_explicitly_disabled(self):
        # Warm is the default now; CADGEN_DAEMON=0 is the opt-out.
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "0"}, clear=False), \
                mock.patch("cadgen.daemon.client.run_via_daemon") as daemon, \
                mock.patch.object(cli.importlib, "import_module") as imported:
            imported.return_value.main.return_value = 0
            cli.main(["stl", "build", "x"])
        daemon.assert_not_called()

    def test_the_daemon_child_never_routes_back_to_itself(self):
        with mock.patch.dict(
            "os.environ", {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_CHILD": "1"}, clear=False
        ), mock.patch("cadgen.daemon.client.run_via_daemon") as daemon, \
                mock.patch.object(cli.importlib, "import_module") as imported:
            imported.return_value.main.return_value = 0
            cli.main(["stl", "build", "x"])
        daemon.assert_not_called()

    def test_an_unserved_command_is_never_routed_to_the_daemon(self):
        # The generic snapshot has no warm tool; routing it would import the wrong module
        # in the worker.
        for command in (["snapshot", "x"], ["doctor"]):
            with self.subTest(command=command):
                with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "1"}, clear=False), \
                        mock.patch("cadgen.daemon.client.run_via_daemon") as daemon, \
                        mock.patch.object(cli.importlib, "import_module") as imported:
                    imported.return_value.main.return_value = 0
                    cli.main(command)
                daemon.assert_not_called()


def _defn(fmt: str) -> authoring.ModelDef:
    def fake():
        return None

    return authoring.ModelDef(
        func=fake,
        fmt=fmt,
        script_path=pathlib.Path("/tmp/preimport-model.py"),
        out=None,
        kind=None,
        mesh_tolerance=None,
        mesh_angular_tolerance=None,
    )


class ColdRunsStayInProcess(unittest.TestCase):
    """No format re-execs the interpreter any more.

    A cold ``@dxf`` run used to restart itself with ``PYTHONHASHSEED=0``, because
    ezdxf's emitted order followed string hashing. The engine's emitter makes DXF
    bytes a function of the drawing's geometry
    (:mod:`cadgen._internal.dxf_emit`), so both formats now reach the pipeline by
    the same route and a directly-run model costs one interpreter, not two.

    Every case sets ``CADGEN_DAEMON=0``: the warm handoff comes first, and without
    the opt-out these would route past the code they are about.
    """

    def test_neither_format_spawns_a_second_interpreter(self):
        for fmt in ("dxf", "step"):
            for seed in ("", "0", "12345"):
                with self.subTest(fmt=fmt, seed=seed):
                    with mock.patch.dict(
                        "os.environ",
                        {"PYTHONHASHSEED": seed, "CADGEN_DAEMON": "0"},
                        clear=False,
                    ), mock.patch("subprocess.run") as run, mock.patch.object(
                        sys, "argv", ["preimport-model.py"]
                    ), mock.patch(
                        "cadgen.cli._run_model.run_model_argv", return_value=0
                    ) as pipeline:
                        self.assertEqual(authoring._build(_defn(fmt)), 0)
                    run.assert_not_called()
                    pipeline.assert_called_once()

    def test_the_pipelines_exit_code_reaches_the_caller(self):
        # Swallowing it would turn every failed generator into a success.
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "0"}, clear=False), \
                mock.patch.object(sys, "argv", ["preimport-model.py"]), \
                mock.patch("cadgen.cli._run_model.run_model_argv", return_value=3):
            self.assertEqual(authoring._build(_defn("dxf")), 3)

    def test_a_warm_dxf_run_still_hands_off(self):
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "1"}, clear=False), \
                mock.patch("cadgen.daemon.client.run_via_daemon", return_value=0) as daemon, \
                mock.patch("subprocess.run") as rerun, \
                mock.patch.object(sys, "argv", ["preimport-model.py"]):
            self.assertEqual(authoring._build(_defn("dxf")), 0)
        daemon.assert_called_once()
        self.assertEqual(daemon.call_args.args[0], "run")
        rerun.assert_not_called()


if __name__ == "__main__":
    unittest.main()
