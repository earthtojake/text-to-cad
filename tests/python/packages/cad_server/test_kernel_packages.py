"""A script's own packages on the WebAssembly kernel (``cad_server._internal.kernel_packages``), and ``cad run``
there (``cad_server.cli.run``): the pure-Python ones the kernel folder does not carry installed in a folder of
their own, one with native code refused by name, and the program run on the kernel's Python with a relay to the
engine. uv is stood in for: each step it is asked is recorded, and an install writes the wheels' records."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad_server._internal import base, kernel_packages  # noqa: E402
from cad_server.cli import run  # noqa: E402

PURE = "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
NATIVE = "Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp314-cp314-manylinux_2_28_x86_64\n"


class Uv:
    """uv: ``compile`` answers ``resolved``; ``install`` writes each package's record into the target, ``native``
    ones as wheels built for a platform."""

    def __init__(self, resolved: str, native: tuple[str, ...] = (), fails: str | None = None) -> None:
        self.resolved, self.native, self.fails = resolved, native, fails
        self.steps: list[list[str]] = []

    def __call__(self, step: list[str], folder: Path) -> subprocess.CompletedProcess:
        self.steps.append(list(step))
        if step[2] == "compile":
            if self.fails:
                return subprocess.CompletedProcess(step, 1, "", f"  x No solution found\n{self.fails}\n")
            return subprocess.CompletedProcess(step, 0, self.resolved, "")
        target = Path(step[step.index("--target") + 1])
        for pinned in (item for item in step if "==" in item):
            name, version = pinned.split("==")
            info = target / f"{name}-{version}.dist-info"
            info.mkdir(parents=True)
            (info / "WHEEL").write_text(NATIVE if name in self.native else PURE, encoding="utf-8")
            (target / f"{name}.py").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(step, 0, "", "")


class KernelPackagesTest(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-kernel-packages-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        folders = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.root / "cache"),
                                               "CAD_STATE_DIR": str(self.root / "state")})
        folders.start()
        self.addCleanup(folders.stop)
        home = self.root / "kernel"
        site = home / "lib" / "python3.14" / "site-packages"
        for carried in ("numpy-2.4.6", "build123d-0.13.0", "typing_extensions-4.15.0"):
            (site / f"{carried}.dist-info").mkdir(parents=True)
        (home / base.WASM_MARKER).write_text(json.dumps({"schema": base.WASM_SCHEMA, "python": "3.14"}), encoding="utf-8")
        (home / "bin").mkdir()
        (home / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        self.kernel = {"python": str(home / "bin" / "python"), "prefix": str(home), "path": None, "own": False, "wasm": True}
        self.said: list[str] = []

    def ensure(self, uv: Uv, *requirements: str) -> Path | None:
        with mock.patch.object(kernel_packages, "_uv", uv), mock.patch.object(base, "find_uv", return_value="uv"):
            return kernel_packages.ensure(self.kernel, tuple(requirements), self.said.append)

    def test_what_the_kernel_folder_carries_is_not_installed_and_the_rest_is_once(self) -> None:
        self.assertIsNone(self.ensure(Uv("")), "no requirement: no folder, and uv not asked")
        uv = Uv("tabulate==0.9.0\nnumpy==2.4.6\ntyping-extensions==4.15.0 ; python_version < '3.15'\n")
        folder = self.ensure(uv, "tabulate", "numpy>=2")
        self.assertEqual([step[2] for step in uv.steps], ["compile", "install"])
        self.assertEqual([item for item in uv.steps[1] if "==" in item], ["tabulate==0.9.0"])
        self.assertIn("--no-deps", uv.steps[1])
        self.assertTrue((folder / "tabulate.py").is_file())
        self.assertEqual(json.loads((folder / kernel_packages.MARKER).read_text(encoding="utf-8"))["installed"], ["tabulate==0.9.0"])
        self.assertEqual(folder.parent, self.root / "cache" / "kernel-packages")
        again = Uv("")
        self.assertEqual(self.ensure(again, "numpy>=2", "tabulate"), folder, "the same requirements: the same folder")
        self.assertEqual(again.steps, [], "made once")
        self.assertEqual(sorted(path.name for path in folder.parent.iterdir()), [folder.name])

    def test_a_package_with_native_code_is_refused_by_name_and_nothing_is_left(self) -> None:
        uv = Uv("ujson==5.11.0\ntabulate==0.9.0\n", native=("ujson",))
        with self.assertRaises(base.Refused) as refused:
            self.ensure(uv, "ujson", "tabulate")
        said = str(refused.exception)
        self.assertTrue(said.startswith("ujson has native code, which the WebAssembly kernel does not run"), said)
        self.assertNotIn("\n", said)
        self.assertEqual(list((self.root / "cache" / "kernel-packages").iterdir()), [])

    def test_requirements_uv_cannot_resolve_are_refused_in_one_line_with_its_reason(self) -> None:
        with self.assertRaises(base.Refused) as refused:
            self.ensure(Uv("", fails="  Because nosuchpackage was not found in the package registry"), "nosuchpackage")
        self.assertRegex(str(refused.exception), r"^the script's own packages do not resolve .*: Because nosuchpackage")
        self.assertNotIn("\n", str(refused.exception))


class RunOnTheKernelTest(KernelPackagesTest):
    """``cad run`` where a person chose the WebAssembly kernel: the program runs on that kernel's Python."""

    def plan(self, **given):
        return run.Plan(**{"kind": "script", "target": "model.py", "args": ["--size", "3"], **given})

    def test_a_program_of_the_kernel_alone_runs_there_and_any_other_as_before(self) -> None:
        from cad_server._internal import extras

        self.assertTrue(run._for_the_kernel(self.plan(), extras.Spec(requirements=("tabulate",))))
        self.assertTrue(run._for_the_kernel(self.plan(kind="module", target="pkg.tool"), extras.Spec()))
        for plan, spec in ((self.plan(kind="command", target="kicad-cli"), extras.Spec()),
                           (self.plan(), extras.Spec(integrations=("build123d", "kicad"))),
                           (self.plan(), extras.Spec(python="3.13")),
                           (self.plan(), extras.Spec(editable=("/w/project",)))):
            self.assertFalse(run._for_the_kernel(plan, spec), (plan, spec))

    def test_it_runs_on_the_kernel_s_python_with_the_library_its_own_packages_and_a_relay_to_the_engine(self) -> None:
        from cad.engine import places, relay
        from cad_server._internal import extras

        ran: dict = {}

        def call(command, env):
            ran.update(command=command, env=env, relay=relay.named(env[relay.VARIABLE]))
            import socket

            socket.create_connection(("127.0.0.1", ran["relay"][0]), timeout=30).close()  # it listens while it runs
            return 7

        uv = Uv("tabulate==0.9.0\n")
        with mock.patch.object(kernel_packages, "_uv", uv), mock.patch.object(base, "find_uv", return_value="uv"), \
                mock.patch.object(subprocess, "call", call), mock.patch.dict(os.environ, {"PYTHONPATH": "/mine"}):
            code = run._on_the_kernel(self.plan(), extras.Spec(requirements=("tabulate",)), self.kernel, self.said.append)
        self.assertEqual(code, 7, "the program's exit code")
        self.assertEqual(ran["command"], [self.kernel["python"], "-P", "-m", run.PROGRAM, "model.py", "--size", "3"])
        path = ran["env"]["PYTHONPATH"].split(os.pathsep)
        self.assertEqual((path[0], Path(path[1]).parent.name, path[2:]), (places.engine_root(), "kernel-packages", ["/mine"]))
        import socket

        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", ran["relay"][0]), timeout=5)  # gone with the program


if __name__ == "__main__":
    unittest.main()
