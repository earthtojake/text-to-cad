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
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad_server._internal import base, kernel_folder  # noqa: E402


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
        launcher = (folder / "bin" / "viewcore").read_text(encoding="utf-8")
        self.assertIn(f'exec "/usr/bin/node" "{folder / "core" / "hosts" / "node" / "serve.mjs"}" "$@"', launcher)
        marker = json.loads((folder / base.WASM_MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["core"], pinned["viewcore"]["sha256"])
        self.assertIn("and the view core", self.said[0])
        (self.root / "state").mkdir()
        (self.root / "state" / "settings.json").write_text(json.dumps({"kernel": {"kind": "wasm"}}), encoding="utf-8")
        with mock.patch.object(kernel_folder, "lock", return_value=pinned):
            self.assertEqual(base.kernel()["core"], str(folder / "bin" / "viewcore"))
            self.assertEqual(base.drawing()["core"], str(folder / "bin" / "viewcore"))
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
        launcher = (folder / "bin" / "python").read_text(encoding="utf-8")
        self.assertIn(f'CAD_KERNEL_HOME="{folder}" exec "/usr/bin/node" "{folder / "host" / "python.mjs"}" "$@"', launcher)
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
            self.assertEqual(base.kernel()["python"], str(folder / "bin" / "python"))
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

    _real_node = staticmethod(kernel_folder.node)

    def test_the_lock_cad_ships_names_every_file_by_an_https_url_and_a_sha256(self) -> None:
        pinned = kernel_folder.lock()
        for item in (*pinned["core"], *pinned["packages"]):
            self.assertRegex(item["url"], r"^https://[^/]+/.+")
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(item["url"].rsplit("/", 1)[1], item["file"])
        self.assertEqual(pinned["python"], "3.14")


if __name__ == "__main__":
    unittest.main()
