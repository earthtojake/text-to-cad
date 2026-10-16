# Copyright The KiCad Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Helpers for running a headless KiCad API server via kicad-cli."""

from __future__ import annotations

import os
import platform
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import IO

from cadgen.kipy.errors import ApiError, ConnectionError

_READY_PREFIX = "KiCad API server listening at "


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _version_key(path: Path) -> tuple[int, ...]:
    version_name = path.parents[1].name
    parts = []

    for chunk in version_name.split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            digits = "".join(ch for ch in chunk if ch.isdigit())
            if digits == "":
                parts.append(-1)
            else:
                parts.append(int(digits))

    return tuple(parts)


def _find_windows_kicad_cli() -> str | None:
    roots: list[Path] = []

    for env_var in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(env_var)
        if value:
            roots.append(Path(value) / "KiCad")

    candidates: list[Path] = []

    for root in roots:
        if root.exists():
            candidates.extend(root.glob("*/bin/kicad-cli.exe"))

    if not candidates:
        return None

    candidates.sort(key=_version_key, reverse=True)

    for candidate in candidates:
        if _is_executable_file(candidate):
            return str(candidate)

    return None


def find_kicad_cli(hint: str | None = None) -> str:
    """Find a kicad-cli executable for the current platform."""
    if hint is not None:
        hinted = Path(hint).expanduser().resolve()

        if _is_executable_file(hinted):
            return str(hinted)

        raise FileNotFoundError(f"kicad-cli was not found at: {hint}")

    system = platform.system()

    if system == "Darwin":
        macos_default = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")

        if _is_executable_file(macos_default):
            return str(macos_default)

        path_match = shutil.which("kicad-cli")
        if path_match is not None:
            return path_match

    elif system == "Windows":
        win_default = _find_windows_kicad_cli()

        if win_default is not None:
            return win_default

        path_match = shutil.which("kicad-cli.exe") or shutil.which("kicad-cli")
        if path_match is not None:
            return path_match

    else:
        path_match = shutil.which("kicad-cli")
        if path_match is not None:
            return path_match

    raise FileNotFoundError("Unable to find kicad-cli. Pass kicad_cli_path=... to KiCad(...).")


class KiCadServer:
    """Manage a kicad-cli api-server subprocess."""

    def __init__(
        self,
        kicad_cli_path: str,
        file_path: str | None = None,
        socket_path: str | None = None,
    ):
        self._kicad_cli_path = kicad_cli_path
        self._file_path = file_path
        self._socket_path = socket_path or self._generate_socket_path()

        self._process: subprocess.Popen[str] | None = None
        self._stdout_lines: queue.Queue[str] = queue.Queue()
        self._stderr_lines: queue.Queue[str] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._ready_line: str | None = None
        self._last_probe_error: str | None = None

    @staticmethod
    def _generate_socket_path() -> str:
        temp_root = Path(tempfile.gettempdir()) / "kicad" / "kicad-python"
        temp_root.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex[:8]
        return str(temp_root / f"api-{os.getpid()}-{token}.sock")

    def _drain_stream(self, stream: IO[str] | None, out_queue: queue.Queue[str]):
        if stream is None:
            return

        for line in stream:
            out_queue.put(line.rstrip("\n"))

    def start(self):
        if self._process is not None and self._process.poll() is None:
            return

        cmd = [self._kicad_cli_path, "api-server", "--socket", self._socket_path]

        if self._file_path:
            cmd.append(self._file_path)

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._stdout_thread = threading.Thread(
            target=self._drain_stream,
            args=(self._process.stdout, self._stdout_lines),
            daemon=True,
        )
        self._stdout_thread.start()

        self._stderr_thread = threading.Thread(
            target=self._drain_stream,
            args=(self._process.stderr, self._stderr_lines),
            daemon=True,
        )
        self._stderr_thread.start()

    def wait_for_ready(self, timeout_s: float = 15.0) -> str:
        if self._process is None:
            raise RuntimeError("KiCad server process has not been started")

        deadline = time.monotonic() + timeout_s
        next_probe = time.monotonic()

        from google.protobuf.empty_pb2 import Empty

        from cadgen.kipy.client import KiCadClient
        from cadgen.kipy.proto.common import commands

        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                break

            while True:
                try:
                    line = self._stdout_lines.get_nowait()
                except queue.Empty:
                    break

                if line.startswith(_READY_PREFIX):
                    self._ready_line = line
                    self._socket_path = line[len(_READY_PREFIX) :].strip()

            now = time.monotonic()

            if now >= next_probe:
                probe = KiCadClient(
                    self.socket_url,
                    "kipy.headless-probe",
                    "",
                    250,
                )

                try:
                    probe.send(commands.Ping(), Empty)
                    probe.close()
                    return self._socket_path
                except (ConnectionError, ApiError) as e:
                    self._last_probe_error = str(e)
                    probe.close()

                next_probe = now + 0.2

            time.sleep(0.05)

        stderr = []
        while True:
            try:
                stderr.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break

        stdout = []
        while True:
            try:
                stdout.append(self._stdout_lines.get_nowait())
            except queue.Empty:
                break

        self.stop()

        details = "\n".join(
            [
                *(["stdout:", *stdout] if stdout else []),
                *(["stderr:", *stderr] if stderr else []),
                *(
                    ["last probe error:", self._last_probe_error]
                    if self._last_probe_error is not None
                    else []
                ),
            ]
        )

        if details:
            raise TimeoutError("Timed out waiting for kicad-cli api-server readiness\n" + details)

        raise TimeoutError("Timed out waiting for kicad-cli api-server readiness")

    @property
    def socket_url(self) -> str:
        return f"ipc://{self._socket_path}"

    def stop(self):
        process = self._process

        if process is None:
            return

        if process.poll() is None:
            try:
                if platform.system() == "Windows":
                    process.terminate()
                else:
                    process.send_signal(signal.SIGTERM)

                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)

        self._process = None

        socket = Path(self._socket_path)
        if socket.exists():
            try:
                socket.unlink()
            except OSError:
                pass
