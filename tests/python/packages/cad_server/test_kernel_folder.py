"""The WebAssembly kernel's folder made by the engine (``cad_server._internal.kernel_folder``): every file of the
lock downloaded and checked against its sha256, the wheels unpacked, cad's host put beside them and a launcher
written for the Node on PATH; made once, and refused in one line that says what to do. The index is a server of
this test's on the loopback, the lock one that names it, and Node a stand-in: nothing here reaches the network."""

from __future__ import annotations

import functools
import hashlib
import http.server
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine import places  # noqa: E402
from cad_server._internal import base, kernel_folder  # noqa: E402


def _runs(folder: Path, name: str) -> tuple[list[str], str | None]:
    """What a kernel folder's launcher ``bin/NAME`` runs, as ``[node, script]``, and the folder it names
    (``CAD_KERNEL_HOME``) or None: a shell script's ``exec NODE SCRIPT "$@"``, on Windows a command file's
    ``"NODE" "SCRIPT" %*`` (``bin/NAME.cmd``). Anything else is ``([], None)``."""
    import re

    if os.name == "nt":
        lines = (folder / "bin" / f"{name}{base.WASM_LAUNCHER}").read_text(encoding="utf-8").splitlines()
        home = next((found[1] for line in lines if (found := re.fullmatch(r'set "CAD_KERNEL_HOME=(.*)"', line))), None)
        found = re.fullmatch(r'"([^"]+)" "([^"]+)" %\*', lines[-1])
        return ([found[1], found[2]] if found and lines[0] == "@echo off" else []), home
    words = shlex.split((folder / "bin" / name).read_text(encoding="utf-8").splitlines()[-1])
    home = words.pop(0).split("=", 1)[1] if words and words[0].startswith("CAD_KERNEL_HOME=") else None
    return (words[1:3] if len(words) == 4 and (words[0], words[3]) == ("exec", "$@") else []), home


def _wheel(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


class _Quiet(http.server.SimpleHTTPRequestHandler):
    fetched: list[str] = []

    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        type(self).fetched.append(self.path)
        super().do_GET()


class KernelFolderTest(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-kernel-folder-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        folders = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.root / "cache"),
                                               "CAD_STATE_DIR": str(self.root / "state")})
        folders.start()
        self.addCleanup(folders.stop)
        index = self.root / "index"
        index.mkdir()
        self.files = {
            "pyodide.mjs": b"export const loadPyodide = 1;\n",
            "python_stdlib.zip": b"the standard library",
            "part-1.0-py3-none-any.whl": _wheel({"part/__init__.py": b"SIZE = 3\n", "part-1.0.dist-info/WHEEL": b"pure\n"}),
            "looks-2.0-py3-none-any.whl": _wheel({"looks/__init__.py": b"", "looks/maps/wood.png": b"\x89PNG" * 100,
                                                   "looks/oak/color.png": b"\x89PNG", "looks/oak/normal.png": b"\x89PNG"}),
        }
        for name, data in self.files.items():
            (index / name).write_bytes(data)
        _Quiet.fetched = []
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(index)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.said: list[str] = []
        self.compiled: list[Path] = []
        for patch in (mock.patch.object(kernel_folder, "node", return_value="/usr/bin/node"),
                      mock.patch.object(kernel_folder, "_compiled", self.compiled.append)):
            patch.start()
            self.addCleanup(patch.stop)

    def item(self, file: str, **more) -> dict:
        return {"file": file, "url": f"http://127.0.0.1:{self.server.server_address[1]}/{file}",
                "sha256": hashlib.sha256(self.files[file]).hexdigest(), **more}

    def locked(self, **changed) -> dict:
        return {"schema": "cad wasm kernel lock/1", "pyodide": "314.0.8", "python": "3.14", "deferred": ["scipy"],
                "core": [self.item("pyodide.mjs"), self.item("python_stdlib.zip")],
                "packages": [self.item("part-1.0-py3-none-any.whl", name="part", version="1.0"),
                             self.item("looks-2.0-py3-none-any.whl", name="looks", version="2.0", slim=True)],
                **changed}

    def ensure(self, pinned: dict, **given):
        with mock.patch.object(kernel_folder, "lock", return_value=pinned):
            return kernel_folder.ensure(told=self.said.append, **given)

    def test_the_view_core_the_lock_names_is_its_core_and_draws_its_stills(self) -> None:
        """A lock that names the view core's archive: unpacked into ``core/``, run by ``bin/viewcore`` under the same
        Node, its sha256 in ``kernel.json``; the engine's pools and its render processes are handed it."""
        self.files["viewcore-4.zip"] = _wheel({"hosts/node/serve.mjs": b"// the job server", "hosts/node/viewcore.mjs": b"",
                                               "hosts/web/viewcore.js": b"", "dist/viewcore.wasm": b"\0asm",
                                               "package.json": b'{"type": "module"}'})
        (self.root / "index" / "viewcore-4.zip").write_bytes(self.files["viewcore-4.zip"])
        pinned = self.locked(viewcore=self.item("viewcore-4.zip"))
        folder = self.ensure(pinned)
        self.assertEqual((folder / "core" / "hosts" / "node" / "serve.mjs").read_bytes(), b"// the job server")
        serve = str(folder / "core" / "hosts" / "node" / "serve.mjs")
        self.assertEqual(_runs(folder, "viewcore"), (["/usr/bin/node", serve], None))
        marker = json.loads((folder / base.WASM_MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["core"], pinned["viewcore"]["sha256"])
        self.assertIn("and the view core", self.said[0])
        (self.root / "state").mkdir()
        (self.root / "state" / "settings.json").write_text(json.dumps({"kernel": {"kind": "wasm"}}), encoding="utf-8")
        with mock.patch.object(kernel_folder, "lock", return_value=pinned):
            self.assertEqual(base.kernel()["core"], str(folder / "bin" / f"viewcore{base.WASM_LAUNCHER}"))
            self.assertEqual(base.drawing()["core"], str(folder / "bin" / f"viewcore{base.WASM_LAUNCHER}"))
            # What the engine starts for it: the launcher; on Windows the Node it names, running the job server.
            self.assertEqual(places.started(base.kernel()["core"]),
                             ["/usr/bin/node", serve] if os.name == "nt" else [base.kernel()["core"]])
        # An archive that is no view core is refused, and nothing is left made.
        self.files["other.zip"] = _wheel({"README": b"not a core"})
        (self.root / "index" / "other.zip").write_bytes(self.files["other.zip"])
        with self.assertRaisesRegex(base.Refused, "holds no hosts/node/serve.mjs"):
            self.ensure(self.locked(viewcore=self.item("other.zip"), deferred=[]))

    def test_it_is_made_once_of_the_lock_s_files_each_checked_and_is_a_kernel_folder_the_engine_takes(self) -> None:
        self.assertIsNone(self.ensure(self.locked(), make=False), "not made for the asking")
        self.assertEqual(_Quiet.fetched, [])
        folder = self.ensure(self.locked())
        self.assertEqual(folder.parent, self.root / "cache" / "kernel")
        site = folder / "lib" / "python3.14" / "site-packages"
        self.assertEqual((folder / "pyodide" / "pyodide.mjs").read_bytes(), self.files["pyodide.mjs"])
        self.assertEqual((site / "part" / "__init__.py").read_bytes(), b"SIZE = 3\n")
        self.assertTrue((site / "looks" / "__init__.py").is_file())
        self.assertFalse((site / "looks" / "maps" / "wood.png").exists(), "a slim wheel's texture images are left out")
        self.assertFalse((site / "looks" / "oak" / "normal.png").exists())
        self.assertTrue((site / "looks" / "oak" / "color.png").is_file(), "but its colour maps: a material's colour")
        self.assertEqual(sorted(path.name for path in (folder / "host").iterdir()), ["bootstrap.py", "python.mjs"])
        self.assertEqual(_runs(folder, "python"), (["/usr/bin/node", str(folder / "host" / "python.mjs")], str(folder)))
        if os.name != "nt":
            self.assertTrue(os.access(folder / "bin" / "python", os.X_OK))
        marker = json.loads((folder / base.WASM_MARKER).read_text(encoding="utf-8"))
        self.assertEqual((marker["schema"], marker["python"], marker["deferred"]), (base.WASM_SCHEMA, "3.14", ["scipy"]))
        self.assertEqual(self.compiled, [folder])
        self.assertEqual(len(_Quiet.fetched), 4)
        self.assertEqual(self.said[0], "making the WebAssembly CAD kernel, once: 4 files of Pyodide 314.0.8")
        # Asked again: the folder as it stands, nothing fetched; and it is the kernel a setting with no folder names.
        self.assertEqual(self.ensure(self.locked()), folder)
        self.assertEqual((len(_Quiet.fetched), self.compiled), (4, [folder]))
        (self.root / "state").mkdir()
        (self.root / "state" / "settings.json").write_text(json.dumps({"kernel": {"kind": "wasm"}}), encoding="utf-8")
        with mock.patch.object(kernel_folder, "lock", return_value=self.locked()):
            self.assertEqual(base.kernel()["python"], str(folder / "bin" / f"python{base.WASM_LAUNCHER}"))
            self.assertEqual(places.started(base.kernel()["python"]),
                             ["/usr/bin/node", str(folder / "host" / "python.mjs")] if os.name == "nt"
                             else [base.kernel()["python"]])
        # Another lock (another release's) is another folder, made of the downloads it shares with this one.
        other = self.ensure(self.locked(deferred=[]))
        self.assertNotEqual(other, folder)
        self.assertEqual(len(_Quiet.fetched), 4, "each file was downloaded once")

    def test_a_file_that_is_not_the_one_the_lock_names_is_refused_and_nothing_is_made(self) -> None:
        pinned = self.locked()
        pinned["packages"][0]["sha256"] = "0" * 64
        with self.assertRaises(base.Refused) as refused:
            self.ensure(pinned)
        said = str(refused.exception)
        self.assertRegex(said, r"^the WebAssembly kernel's part-1\.0-py3-none-any\.whl, downloaded from http://127\.0\.0\.1:"
                               r"\d+/part-1\.0-py3-none-any\.whl, is not the file this release of cad names")
        self.assertNotIn("\n", said)
        self.assertEqual([path.name for path in (self.root / "cache" / "kernel").iterdir()], ["downloads"])
        self.assertNotIn("0" * 64, os.listdir(self.root / "cache" / "kernel" / "downloads"), "the wrong file is not kept")

    def test_a_file_that_cannot_be_fetched_is_one_line_that_says_what_to_do(self) -> None:
        pinned = self.locked()
        pinned["core"][0]["url"] = pinned["core"][0]["url"].replace("pyodide.mjs", "absent.mjs")
        pinned["core"][0]["sha256"] = "1" * 64
        with self.assertRaises(base.Refused) as refused:
            self.ensure(pinned)
        said = str(refused.exception)
        self.assertIn("could not be downloaded from", said)
        self.assertIn("connect to the network and ask again, or make the folder by hand and name it in the settings", said)
        self.assertNotIn("\n", said)
        self.assertEqual(refused.exception.cause, "network")

    def test_no_node_or_an_old_one_is_one_line_before_anything_is_fetched(self) -> None:
        import subprocess

        kernel_folder._version.cache_clear()
        self.addCleanup(kernel_folder._version.cache_clear)

        for found, version, word in ((None, "", "no node is on PATH"), ("/usr/bin/node", "v22.11.0\n", "is v22.11.0")):
            with mock.patch.object(kernel_folder, "node", kernel_folder.node.__wrapped__
                                   if hasattr(kernel_folder.node, "__wrapped__") else self._real_node), \
                    mock.patch("shutil.which", return_value=found), \
                    mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, version, "")):
                with self.assertRaises(base.Refused) as refused:
                    self.ensure(self.locked())
                self.assertIn(word, str(refused.exception))
                self.assertIn(f"Node {kernel_folder.NODE} or later", str(refused.exception))
                self.assertIsNone(self.ensure(self.locked(), make=False))
        self.assertEqual(_Quiet.fetched, [])

    def test_a_node_is_asked_its_version_once_a_process(self) -> None:
        """Every kernel process's start asks for the folder, which names its Node: ``node --version`` runs once."""
        import subprocess

        kernel_folder._version.cache_clear()
        self.addCleanup(kernel_folder._version.cache_clear)
        with mock.patch("shutil.which", return_value="/opt/node24/bin/node"), \
                mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v24.1.0\n", "")) as run:
            for _ in range(3):
                self.assertEqual(self._real_node(), "/opt/node24/bin/node")
        self.assertEqual(run.call_count, 1)

    def test_a_download_is_kept_only_once_it_is_the_file_and_a_short_one_is_the_network_s(self) -> None:
        """A file is put in its place only after its bytes are the lock's (a wrong one leaves nothing kept); a download
        that stops short is a network failure; one that cannot be written is the disk's, not the network's."""
        downloads = self.root / "cache" / "kernel" / "downloads"
        self.files["pyodide.mjs"] = b"another file"
        (self.root / "index" / "pyodide.mjs").write_bytes(b"another file")
        wrong = self.locked()
        wrong["core"][0]["sha256"] = hashlib.sha256(b"the file the lock names").hexdigest()
        with self.assertRaisesRegex(base.Refused, "is not the file this release of cad names"):
            self.ensure(wrong)
        self.assertFalse((downloads / wrong["core"][0]["sha256"]).exists(), "nothing unchecked is kept")
        self.assertEqual(list(downloads.glob("*.part-*")), [])

        class Short(_Quiet):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b"x" * 10)

        short = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Short)
        threading.Thread(target=short.serve_forever, daemon=True).start()
        self.addCleanup(short.server_close)
        self.addCleanup(short.shutdown)
        stopped = self.locked()
        stopped["core"][0]["url"] = f"http://127.0.0.1:{short.server_address[1]}/pyodide.mjs"
        with self.assertRaises(base.Refused) as refused:
            self.ensure(stopped)
        self.assertEqual(refused.exception.cause, "network")
        self.assertIn("connect to the network and ask again", str(refused.exception))
        real_open = open

        def full(path, mode="r", *args, **kwargs):
            if ".part-" in str(path) and "w" in mode:
                raise OSError(28, "No space left on device")
            return real_open(path, mode, *args, **kwargs)

        with mock.patch("builtins.open", full), self.assertRaises(base.Refused) as refused:
            self.ensure(self.locked())
        self.assertEqual(refused.exception.cause, "other")
        self.assertIn("could not be written", str(refused.exception))
        self.assertIn("No space left on device", str(refused.exception))

    def test_what_a_killed_making_left_is_swept_and_a_living_one_s_is_not(self) -> None:
        kernel, downloads = self.root / "cache" / "kernel", self.root / "cache" / "kernel" / "downloads"
        downloads.mkdir(parents=True)
        gone = subprocess.Popen(["true"])
        gone.wait()
        for path in (kernel / f"abc.making-{gone.pid}", kernel / f"abc.making-{os.getpid()}"):
            path.mkdir()
        (downloads / f"{'0' * 64}.part-{gone.pid}").write_bytes(b"half")
        self.ensure(self.locked())
        self.assertFalse((kernel / f"abc.making-{gone.pid}").exists())
        self.assertFalse((downloads / f"{'0' * 64}.part-{gone.pid}").exists())
        self.assertTrue((kernel / f"abc.making-{os.getpid()}").exists(), "a living process's making is its own")

    @unittest.skipIf(os.name == "nt", "a shell launcher's quoting; Windows' is a command file, and no Windows name holds a quote")
    def test_a_cache_path_the_shell_would_read_is_quoted_in_the_launcher(self) -> None:
        odd = self.root / 'cache $HOME `x` "q"'
        with mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(odd)}):
            folder = self.ensure(self.locked())
        line = (folder / "bin" / "python").read_text(encoding="utf-8").splitlines()[-1]
        self.assertEqual(shlex.split(line)[0], f"CAD_KERNEL_HOME={folder}")
        checked = subprocess.run(["sh", "-n", str(folder / "bin" / "python")], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_the_host_cad_ships_reads_no_variable_of_cad_s_but_the_folder_its_launcher_names(self) -> None:
        """A variable is for what a process must know before it starts: the host's folder, which its launcher sets.
        What the host refuses is said for someone with the installed package alone (no tool outside it named)."""
        import re

        host = (kernel_folder._HOST / "python.mjs").read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r"process\.env\.(CAD_\w+)", host))), ["CAD_KERNEL_HOME"])
        refusals = re.findall(r"refuse\((.*?)\);", host, re.S)
        self.assertTrue(refusals)
        self.assertFalse([said for said in refusals if "make.mjs" in said or "fetch.mjs" in said])

    _real_node = staticmethod(kernel_folder.node)

    def test_the_lock_cad_ships_names_every_file_by_an_https_url_and_a_sha256(self) -> None:
        pinned = kernel_folder.lock()
        for item in (*pinned["core"], *pinned["packages"]):
            self.assertRegex(item["url"], r"^https://[^/]+/.+")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(item["url"].rsplit("/", 1)[1], item["file"])
        self.assertEqual(pinned["python"], "3.14")


class HostWindowsPathsTest(unittest.TestCase):
    """The host's Windows paths (``bootstrap._windows``): on a Windows computer the kernel's Python reads and makes
    paths as a Windows Python does, though its platform is POSIX. Pure Python: run here in a Python of its own,
    with the platform's working folder a mounted drive's (``/C:/...``) and its path as Pyodide makes it."""

    def test_the_program_is_handed_windows_paths_and_the_platform_s_own_folders_stay_its_own(self) -> None:
        code = r"""
import json, os, sys, importlib.metadata, importlib.util, pathlib, site  # imported first: their folders are no drive's
spec = importlib.util.spec_from_file_location("host_bootstrap", sys.argv[1])
host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
os.getcwd = lambda: "/C:/work/model"
os.environ["PYTHONPATH"] = "C:\\src;D:\\more"
sys.path[:] = ["/home/pyodide/C", "/home/pyodide/\\src;D", "/home/pyodide/\\more", "/lib/python3.14", *sys.path]
host._windows({"windows": True, "site": "/lib/python3.14/site-packages"})
host._path({"isolated": False, "safe": True, "kind": "module", "target": "m"})
print(json.dumps({"cwd": os.getcwd(), "seps": [os.sep, os.altsep, os.pathsep],
    "parent": str(pathlib.Path("C:/work/model/part.py").parent), "name": pathlib.Path("C:\\work\\part.py").name,
    "absolute": [os.path.isabs(name) for name in ("C:\\x", "/lib/x", "relative")],
    "own": [os.path.abspath("/lib/python3.14"), str(pathlib.Path("/lib/x").resolve())],
    "site": site.getsitepackages(), "path": sys.path,
    "joined": [importlib._bootstrap_external._path_join(*parts) for parts in (("C:\\src\\", "cad", "__init__.py"),
                                                                             ("/lib/python314.zip", "json"))]}))
"""
        ran = subprocess.run([sys.executable, "-I", "-c", code, str(kernel_folder._HOST / "bootstrap.py")],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        said = json.loads(ran.stdout)
        self.assertEqual(said["cwd"], "C:\\work\\model")
        self.assertEqual(said["seps"], ["\\", "/", ";"])
        self.assertEqual((said["parent"], said["name"]), ("C:\\work\\model", "part.py"))
        self.assertEqual(said["absolute"], [True, True, False])
        self.assertEqual(said["own"], ["\\lib\\python3.14", "\\lib\\x"], "no drive is put before them")
        self.assertEqual(said["site"], ["/lib/python3.14/site-packages"])
        # A module's file is named as Windows names it; the platform's own as the platform does.
        self.assertEqual(said["joined"][0], "C:\\src\\cad\\__init__.py")
        if os.name != "nt":  # a Windows Python's own joins are Windows' anyway
            self.assertEqual(said["joined"][1], "/lib/python314.zip/json")
        # PYTHONPATH read by Windows' separator; the pieces the platform made of it by its own are gone.
        self.assertEqual(said["path"][:3], ["C:\\src", "D:\\more", "/lib/python3.14"])
        self.assertFalse([entry for entry in said["path"] if entry.startswith("/home/pyodide/")])


if __name__ == "__main__":
    unittest.main()
