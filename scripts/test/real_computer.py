"""A private computer with the real programs of agent apps, and a local stand-in for our repository.

``Computer`` is one computer of a test's own, in one folder: its own home (``HOME``, ``USERPROFILE``, ``APPDATA``,
``LOCALAPPDATA``, the XDG folders, the temporary folder), cad's state and engine folders, uv's folders, its own
default port, and an environment of the system's essentials alone (no account's key or token, nothing of the
machine's home). On its PATH are the REAL programs named, never stand-ins, each told its configuration folder inside
the home (``Program.environ``), and nothing else ``install.py`` would take for an agent app (``Computer.check_path``).

Its git reads our repository from a local copy (``Computer.stand_in``): the plugin as the ``latest`` branch carries it
(``scripts/release/plugin_branch.py``), committed to a local bare repository, and every address of our repository on
GitHub rewritten to it (``url.<local>.insteadOf``, for the https, ssh and ``git@`` forms) in the computer's global git
config (``GIT_CONFIG_GLOBAL``) and in the template every new repository starts from (``GIT_TEMPLATE_DIR``): Gemini CLI
clones with the global config set to nothing, which a new repository's own config survives.

Its uv keeps its tools, their commands and its Pythons in the computer (``UV_TOOL_DIR``, ``UV_TOOL_BIN_DIR``: the home's
``.local/bin``, first on PATH as on a person's; ``UV_PYTHON_INSTALL_DIR``), and its cache there too unless a run names
one folder for all its computers (``shared``: what each downloads once). ``Computer.isolation`` prints each folder a
program could write and fails before anything runs where one is not the computer's. Its port is the true default
(3245) on CI alone, where nothing else serves; elsewhere a free one of its own (``CAD_ENGINE_DEFAULT_PORT``), never a
person's.

``Feed`` is the version feed served on loopback (``CAD_API_URL``), at both its addresses: any path ending ``versions``
(``<api>/versions``, which 0.10.0 to 0.11.11 read) and any ending ``releases`` (``<api>/releases``, this tree's); the
install command reads no feed. ``publish`` writes this tree's wheels
again as another release, or a variant of one (a file replaced, its commands taken out), from wheels already built;
``stamp`` names that release: this tree's ``VERSION``'s major and minor, a patch far above any real one, so the wheels
offered to uv (``UV_FIND_LINKS``) are newer than PyPI's newest and the install command's ``uv tool install cad`` takes
them. The install workflows and ``scripts/test/real-install.py`` stamp with it.

``RealHome`` lists what the machine's own home holds for these programs and cad, to prove a run changed none of it;
``Sentinels``, the few files a person's agent apps and cad keep, before and after each rehearsal.
``scripts/test/real-install.py`` and ``scripts/test/rehearse-update.py`` run on it. The standard library alone.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"
CI = bool(os.environ.get("GITHUB_ACTIONS"))
REPOSITORY = "earthtojake/text-to-cad"
BRANCH = "latest"
# The ports the person's own servers serve on: never a test's.
TAKEN = range(3245, 3251)
DEFAULT_PORT = 3245
# How long the processes of a computer stopped by its own command may take to end.
GONE_SECONDS = 60.0
# The file the stand-in's copy carries beside the plugin, naming this run: a copy holding it came from here.
MARK = ".real-install"
# The variables of the machine a computer keeps: what the system and a proxy need, nothing of a person.
KEPT = ("LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME", "SHELL", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
        # Windows
        "SystemRoot", "SystemDrive", "windir", "ComSpec", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER", "NUMBER_OF_PROCESSORS", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
        "ProgramData", "CommonProgramFiles", "CommonProgramFiles(x86)", "CommonProgramW6432", "PSModulePath",
        "USERNAME", "USERDOMAIN", "ALLUSERSPROFILE", "PUBLIC", "DriverData")
# Telemetry off for every program a computer runs: cad's (every release's words for it) and the agent apps'.
QUIET = {"DO_NOT_TRACK": "1", "CAD_TELEMETRY": "0", "CADGEN_TELEMETRY": "0", "DISABLE_TELEMETRY": "1"}


@dataclass
class Program:
    """A real agent app's command: what the install script calls it, and where it keeps its configuration in a home
    (each from the program's own documentation, set explicitly so no default is relied on)."""

    command: str
    name: str  # the app's name in the install script's lines
    environ: Callable[[Path], dict[str, str]]
    folders: Callable[[Path], list[Path]]  # what it keeps in a home: the real home's are watched

    def path(self) -> str | None:
        return shutil.which(self.command)


PROGRAMS = {
    # Claude Code: CLAUDE_CONFIG_DIR holds its settings, plugins and its .claude.json. No update of itself.
    "claude": Program("claude", "Claude Code",
                      lambda home: {"CLAUDE_CONFIG_DIR": str(home / ".claude"), "DISABLE_AUTOUPDATER": "1"},
                      lambda home: [home / ".claude", home / ".claude.json"]),
    # Codex: CODEX_HOME (which must exist) holds config.toml, its marketplaces and plugins.
    "codex": Program("codex", "Codex", lambda home: {"CODEX_HOME": str(home / ".codex")},
                     lambda home: [home / ".codex"]),
    # Gemini CLI: GEMINI_CLI_HOME is the home it keeps .gemini in (else the system's home: USERPROFILE on Windows).
    "gemini": Program("gemini", "Gemini CLI", lambda home: {"GEMINI_CLI_HOME": str(home)},
                      lambda home: [home / ".gemini"]),
}


@dataclass
class Ran:
    code: int
    out: str

    def lines(self) -> list[str]:
        return self.out.splitlines()


class Failed(Exception):
    pass


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    if port in TAKEN:
        return free_port()
    return port


def default_free() -> bool:
    """Whether the true default port is free here (on loopback and every interface), nothing connected to."""
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket() as probe:
            try:
                probe.bind((host, DEFAULT_PORT))
            except OSError:
                return False
    return True


class Loopback(http.server.ThreadingHTTPServer):
    """A stand-in's server on loopback, bound without ``HTTPServer``'s naming of the host by reverse DNS
    (``socket.getfqdn``), which waits about 35 s where no resolver answers (GitHub's Macs), as cad's own server
    does (``cad_server.viewer.handler``). Nothing reads the name."""

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class Feed(Loopback):
    """The version feed saying ``latest`` at both its addresses: the old one (any path ending ``versions``), ``latest``
    alone, as releases 0.10.0 to 0.11.11 read it, and the new one (any path ending ``releases``), with ``lines``:
    ``lines`` as set (each major's newest release, by its number), else ``latest`` for its own major; anything else
    (telemetry) is not found. ``asked``: how many times it was read; ``reads``: each read, its address (``versions``
    or ``releases``) and the reader's ``User-Agent``."""

    def __init__(self, latest: str) -> None:
        self.latest = latest
        self.lines: dict[str, str] | None = None
        self.asked = 0
        self.reads: list[tuple[str, str]] = []
        feed = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                path = self.path.split("?", 1)[0].rstrip("/")
                address = next((name for name in ("versions", "releases") if path.endswith(name)), None)
                if address is None:
                    self.answer(None)
                    return
                feed.asked += 1
                feed.reads.append((address, self.headers.get("User-Agent") or ""))
                answer: dict = {"latest": feed.latest}
                if address == "releases":
                    answer["lines"] = (dict(feed.lines) if feed.lines is not None
                                       else {feed.latest.split(".", 1)[0]: feed.latest})
                self.answer(json.dumps(answer).encode())

            def do_POST(self) -> None:  # noqa: N802
                self.answer(None)

            def answer(self, body: bytes | None) -> None:
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body or b"")))
                self.end_headers()
                self.wfile.write(body or b"")

            def log_message(self, *_args) -> None:
                pass

        super().__init__(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/v1"

    def close(self) -> None:
        self.shutdown()
        self.server_close()


class Computer:
    """A private computer in ``work`` with the real ``programs`` (command -> its path on this machine) on its PATH:
    see the module."""

    def __init__(self, work: Path, programs: dict[str, str], *, feed: Feed | None = None,
                 shared: Path | None = None, wheels: Path | None = None,
                 helpers: tuple[str, ...] = ("node", "git", "uv", "uvx")) -> None:
        self.work = Path(work).resolve()
        self.home = self.work / "home"
        self.state = self.work / "state"
        self.tools = self.work / "tools"
        self.bin = self.home / ".local" / "bin"  # uv's bin folder, as on a person's computer
        self.uv_tools = self.home / ".local" / "share" / "uv" / "tools"
        self.programs = programs
        self.feed = feed
        self.helpers = helpers
        self.port = DEFAULT_PORT if CI and default_free() else free_port()
        for folder in (self.home, self.tools, self.work / "tmp", self.state, self.bin):
            folder.mkdir(parents=True, exist_ok=True)
        home = self.home
        uv = Path(shared).resolve() if shared is not None else self.work / "uv"
        self.uv = uv
        self.looked = True  # whether the last look at the running processes could see them (``processes``)
        env = {key: os.environ[key] for key in KEPT if key in os.environ}
        bypass = ",".join(filter(None, ("127.0.0.1,localhost", os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))))
        env.update({
            "HOME": str(home), "TMPDIR": str(self.work / "tmp"), "TEMP": str(self.work / "tmp"),
            "TMP": str(self.work / "tmp"), "TERM": "dumb", "NO_COLOR": "1", "BROWSER": "true", **QUIET,
            "NO_PROXY": bypass, "no_proxy": bypass,
            "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_STATE_HOME": str(home / ".local" / "state"), "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_BIN_HOME": str(self.bin),
            "CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.work / "engine"),
            "CAD_CACHE_DIR": str(self.work / "cache"), "CAD_ENGINE_DEFAULT_PORT": str(self.port),
            "CADGEN_ENGINE_DEFAULT_PORT": str(self.port),
            # uv's folders, each named, so no default is relied on: its tools and their commands in the home, as on a
            # person's computer; its cache and Pythons the computer's, or the run's (``shared``).
            "UV_CACHE_DIR": str(uv / "cache"), "UV_PYTHON_INSTALL_DIR": str(uv / "python"),
            "UV_PYTHON_BIN_DIR": str(self.work / "uv-python-bin"), "UV_PYTHON_INSTALL_BIN": "0",
            "UV_TOOL_DIR": str(self.uv_tools), "UV_TOOL_BIN_DIR": str(self.bin), "UV_NO_MODIFY_PATH": "1",
            "GIT_CONFIG_GLOBAL": str(self.work / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TEMPLATE_DIR": str(self.work / "git-template"), "GIT_TERMINAL_PROMPT": "0",
            # The install command looks for the apps on PATH alone.
            "CAD_INSTALL_PATH_ONLY": "1",
            # Agent apps' own config folders, in the home even where the app is not under test.
            "CLAUDE_CONFIG_DIR": str(home / ".claude"), "CODEX_HOME": str(home / ".codex"),
            "GEMINI_CLI_HOME": str(home),
        })
        if not WINDOWS:
            env["XDG_RUNTIME_DIR"] = str(self.work / "run")
            (self.work / "run").mkdir(mode=0o700, exist_ok=True)
        if WINDOWS:
            env.update({"USERPROFILE": str(home), "APPDATA": str(home / "AppData" / "Roaming"),
                        "LOCALAPPDATA": str(home / "AppData" / "Local"), "HOMEDRIVE": home.drive,
                        "HOMEPATH": str(home)[len(home.drive):]})
        if feed is not None:
            # cad's version feed and its telemetry (the stand-in answers the feed alone).
            env["CAD_API_URL"] = feed.url
        else:
            env["CAD_API_URL"] = "http://127.0.0.1:9"
        if wheels is not None:
            # A folder of wheels uv reads beside the index: the install command's and cad's own `uv tool install`
            # (UV_FIND_LINKS), the environments cad and its earlier releases make (CAD_UPDATE_FIND_LINKS).
            env.update({"UV_FIND_LINKS": str(wheels), "CAD_UPDATE_FIND_LINKS": str(wheels)})
        for name in programs:
            env.update(PROGRAMS[name].environ(home) if name in PROGRAMS else {})
        if "codex" not in programs:
            # 0.10.0 to 0.11.11 take CODEX_CLI before the Codex app's bundled codex, which they find outside PATH: a
            # path where there is none, so no codex is theirs to find.
            env["CODEX_CLI"] = str(self.work / "no-such" / "codex")
        (home / ".codex").mkdir(exist_ok=True)
        # Gemini CLI: no update of itself, which would change the machine's install outside this computer.
        (home / ".gemini").mkdir(exist_ok=True)
        (home / ".gemini" / "settings.json").write_text(
            json.dumps({"general": {"enableAutoUpdate": False, "enableAutoUpdateNotification": False}}), "utf-8")
        for folder in (env.get("APPDATA"), env.get("LOCALAPPDATA")):
            if folder:
                Path(folder).mkdir(parents=True, exist_ok=True)
        env["PATH"] = self._path(programs)
        self.env = env
        (self.work / "gitconfig").write_text("", encoding="utf-8")
        (self.work / "git-template").mkdir(exist_ok=True)
        # Telemetry off as the person's kept choice too: a detached server goes by that, not by the environment.
        quiet(self.state)
        self.commit = ""
        self.nonce = ""

    # Every variable that names a folder a program of the computer writes in.
    ISOLATED = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TMPDIR", "TEMP", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_BIN_HOME", "XDG_RUNTIME_DIR", "CAD_STATE_DIR",
                "CAD_ENGINE_DIR", "CAD_CACHE_DIR", "UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "UV_PYTHON_BIN_DIR",
                "CODEX_HOME", "CLAUDE_CONFIG_DIR", "GEMINI_CLI_HOME", "GIT_CONFIG_GLOBAL")

    def isolation(self, say: Callable[[str], None] = print) -> None:
        """Each folder a program of the computer writes in, printed, and ``Failed`` before anything runs where one is
        not inside the computer; uv's cache and Pythons, where the run shares them, in none of the person's own
        folders of uv, cad and the agent apps, and not holding the home (``uv_refused``); the feed on loopback."""
        wrong = []
        for name in self.ISOLATED:
            value = self.env.get(name)
            if value is None:
                continue
            inside = _within(Path(value), self.work)
            say(f"  {name}={value}")
            if not inside:
                wrong.append(name)
        for name in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"):
            value = self.env[name]
            say(f"  {name}={value}")
            if not _within(Path(value), self.work) and uv_refused(Path(value)):
                wrong.append(name)
        value = self.env.get("CAD_API_URL", "")
        say(f"  CAD_API_URL={value}")
        if value and not value.startswith("http://127.0.0.1:"):
            wrong.append("CAD_API_URL")
        say(f"  CAD_ENGINE_DEFAULT_PORT={self.port}")
        if self.port in TAKEN and not CI:
            wrong.append("CAD_ENGINE_DEFAULT_PORT")
        if wrong:
            raise Failed(f"the computer is not isolated: {', '.join(wrong)}")

    # --- PATH -------------------------------------------------------------------------------------------------

    def _path(self, programs: dict[str, str]) -> str:
        """The computer's PATH: the programs, node, git and uv, and the system's own folders. On macOS and Linux each
        is linked into one folder of the computer's, so no other command of their folders comes along; on Windows,
        where npm's commands are .cmd files that run what lies beside them, their folders themselves."""
        needed = {**programs}
        for helper in self.helpers:
            found = shutil.which(helper)
            if found:
                needed[helper] = found
        if WINDOWS:
            system = os.environ.get("SystemRoot", r"C:\Windows")
            folders = [str(self.bin), str(self.tools), *dict.fromkeys(str(Path(path).parent) for path in needed.values()),
                       rf"{system}\System32", system, rf"{system}\System32\WindowsPowerShell\v1.0",
                       rf"{system}\System32\Wbem"]
            return os.pathsep.join(folders)
        for name, path in needed.items():
            link = self.tools / name
            if not link.exists():
                link.symlink_to(os.path.realpath(path))
        return os.pathsep.join([str(self.bin), str(self.tools), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])

    def check_path(self, commands: list[str]) -> None:
        """``Failed`` when a command an agent app is found by, other than the programs under test, is on the computer's
        PATH: the install script would run it."""
        found = [f"{name} ({where})" for name in commands if name not in self.programs
                 and (where := shutil.which(name, path=self.env["PATH"]))]
        if found:
            raise Failed(f"programs not under test are on the computer's PATH: {', '.join(found)}")

    # --- running ----------------------------------------------------------------------------------------------

    def which(self, name: str) -> str:
        found = shutil.which(name, path=self.env["PATH"])
        if not found:
            raise Failed(f"{name} is not on the computer's PATH")
        return found

    def run(self, argv: list, *, cwd: Path | None = None, stdin: bytes | None = None, extra: dict | None = None,
            echo: Callable[[str], None] | None = None) -> Ran:
        """``argv`` run in the computer, stdout and stderr together; each line handed to ``echo`` as it comes."""
        argv = [str(part) for part in argv]
        if WINDOWS and not os.path.isabs(argv[0]):
            argv[0] = self.which(argv[0])
        process = subprocess.Popen(argv, cwd=str(cwd or self.work), env={**self.env, **(extra or {})},
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        process.stdin.write(stdin or b"")
        process.stdin.close()
        lines = []
        for raw in process.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            lines.append(line)
            if echo:
                echo(line)
        return Ran(process.wait(), "\n".join(lines))

    def listing(self, argv: list) -> Ran:
        """``argv`` run with its output to a file, not a pipe: Node writes to a pipe as it goes and may exit before a
        long listing is out (Gemini CLI's list of its extensions, 170 kB, came cut at 64 kB)."""
        argv = [str(part) for part in argv]
        if WINDOWS and not os.path.isabs(argv[0]):
            argv[0] = self.which(argv[0])
        with tempfile.TemporaryFile(dir=self.work / "tmp") as out:
            code = subprocess.run(argv, cwd=str(self.work), env=self.env, stdin=subprocess.DEVNULL, stdout=out,
                                  stderr=subprocess.STDOUT).returncode
            out.seek(0)
            text = out.read().decode("utf-8", "replace")
        if code:
            raise Failed(f"`{' '.join(argv)}` exited {code}:\n{text[-3000:]}")
        return Ran(code, text)

    def must(self, argv: list, **options) -> Ran:
        ran = self.run(argv, **options)
        if ran.code:
            raise Failed(f"`{' '.join(str(word) for word in argv)}` exited {ran.code}:\n{ran.out}")
        return ran

    # --- our repository, from a local copy --------------------------------------------------------------------

    def stand_in(self, tree: dict[str, tuple[str, bytes]]) -> str:
        """``tree`` (path -> (git mode, bytes), as ``plugin_branch.build`` gives it) and a file naming this run
        (``MARK``) committed as the ``latest`` branch of a local bare repository, which the computer's git reads for
        every address of our repository on GitHub. The commit."""
        self.nonce = uuid.uuid4().hex
        source, bare = self.work / "stand-in" / "source", self.work / "stand-in" / "text-to-cad.git"
        source.mkdir(parents=True)
        for path, (mode, data) in {**tree, MARK: ("100644", f"{self.nonce}\n".encode())}.items():
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if mode == "100755" and not WINDOWS:
                target.chmod(0o755)
        who = ["-c", "user.name=real-install", "-c", "user.email=real-install@localhost", "-c", "core.autocrlf=false"]
        self.must(["git", "init", "--quiet", "--initial-branch", BRANCH, source])
        self.must(["git", *who, "-C", source, "add", "--all"])
        self.must(["git", *who, "-C", source, "commit", "--quiet", "--message", "the plugin's latest copy, this tree"])
        self.must(["git", "clone", "--quiet", "--bare", source, bare])
        local = bare.as_uri()
        # insteadOf replaces a prefix, the longest that matches: each form with and without .git names the bare one.
        forms = [f"https://github.com/{REPOSITORY}", f"http://github.com/{REPOSITORY}",
                 f"ssh://git@github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}", f"git://github.com/{REPOSITORY}"]
        config = f'[url "{local}"]\n' + "".join(f"\tinsteadOf = {form}\n\tinsteadOf = {form}.git\n" for form in forms)
        (self.work / "gitconfig").write_text(config, encoding="utf-8")
        (self.work / "git-template" / "config").write_text(config, encoding="utf-8")
        self.commit = self.must(["git", "-C", bare, "rev-parse", BRANCH]).out.strip()
        # Proved, as a person's git reads it: GitHub's address answers with this commit.
        said = self.must(["git", "ls-remote", f"https://github.com/{REPOSITORY}", BRANCH]).out.split()
        if said[:1] != [self.commit]:
            raise Failed(f"the computer's git does not read our repository from the local copy: {said}")
        return self.commit

    def advance(self, version: str, following: str) -> str:
        """The local repository's ``latest`` moved on as a release moves GitHub's: a commit whose manifests name
        ``following`` in place of ``version`` (an app keeps a copy of each version: the same version is not copied
        again), and a new run (``MARK``). The commit."""
        self.nonce = uuid.uuid4().hex
        source, bare = self.work / "stand-in" / "source", self.work / "stand-in" / "text-to-cad.git"
        (source / MARK).write_text(f"{self.nonce}\n", encoding="utf-8", newline="\n")
        for manifest in source.rglob("*.json"):
            if "skills" not in manifest.relative_to(source).parts:
                text = manifest.read_bytes().decode("utf-8")
                manifest.write_text(text.replace(f'"version": "{version}"', f'"version": "{following}"'),
                                    encoding="utf-8", newline="\n")
        who = ["-c", "user.name=real-install", "-c", "user.email=real-install@localhost"]
        self.must(["git", *who, "-C", source, "commit", "--quiet", "--all", "--message", "the next copy"])
        self.must(["git", "-C", source, "push", "--quiet", bare, BRANCH])
        self.commit = self.must(["git", "-C", bare, "rev-parse", BRANCH]).out.strip()
        return self.commit

    def local_copy(self, folder: Path) -> bool:
        """Whether ``folder`` holds this run's copy (its ``MARK``)."""
        try:
            return (Path(folder) / MARK).read_text(encoding="utf-8").strip() == self.nonce
        except OSError:
            return False

    # --- ending -----------------------------------------------------------------------------------------------

    def processes(self) -> list[tuple[int, str]]:
        """Every process of the computer's, but this one: on macOS and Linux each whose command line names the
        computer's folder; on Windows each whose program lies in it or in the run's uv folder (a venv's python.exe
        starts uv's Python, whose command line names no folder of the computer's), read through the Win32 API in this
        process (WMI is refused in a service's session). ``looked`` says whether it could look at all."""
        if WINDOWS:
            images = windows_images()
            self.looked = images is not None
            places = (self.work, self.uv)
            return [(pid, image) for pid, image in images or [] if pid != os.getpid()
                    and any(_within(Path(image), place) for place in places)]
        listed = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, errors="replace")
        self.looked = listed.returncode == 0
        found = []
        mark = str(self.work)
        for line in listed.stdout.splitlines():
            pid, _, command = line.strip().partition(" ")
            if pid.isdigit() and int(pid) != os.getpid() and mark in command:
                found.append((int(pid), command))
        return found

    def stop(self, cad: Path | None = None, seconds: float = GONE_SECONDS) -> list[str]:
        """The computer's cad server stopped by its own command, every process from its folder awaited until gone
        (``cad stop`` returns once the server's door is shut and its lock free: the server's process is still
        exiting then, and a kernel worker's multiprocessing resource tracker ends only after the worker), then what
        is still running after ``seconds`` ended. What had to be ended, which the caller treats as left behind."""
        if cad is not None and cad.exists():
            self.run([cad, "server", "stop"])
        deadline = time.monotonic() + seconds
        left = self.processes()
        while left and time.monotonic() < deadline:
            time.sleep(0.25)
            left = self.processes()
        for pid, _command in left:
            try:
                if WINDOWS:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return [f"{pid} {command}" for pid, command in left]

    def remove(self) -> None:
        def again(function, name, *_error) -> None:
            try:
                os.chmod(name, 0o700)
                function(name)
            except OSError:
                pass

        if sys.version_info >= (3, 12):
            shutil.rmtree(self.work, onexc=again)
        else:
            shutil.rmtree(self.work, onerror=again)


def plugin_tree() -> dict[str, tuple[str, bytes]]:
    """The plugin's ``latest`` copy as Publish Release builds it from this tree (``plugin_branch.build``)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "release"))
    try:
        import plugin_branch  # noqa: PLC0415 - beside it, in scripts/release
    finally:
        sys.path.pop(0)
    tree, errors, _manifest = plugin_branch.build(REPO_ROOT, "latest")
    if errors:
        raise Failed("the latest copy does not build: " + "; ".join(errors))
    return tree


def tagged_tree(tag: str, paths: list[str], into: Path) -> Path:
    """``paths`` as release ``tag`` had them, written into ``into`` (``git archive``). ``Failed`` naming the fetch to
    run where the tag is not here (a shallow checkout)."""
    have = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],
                          capture_output=True)
    if have.returncode:
        raise Failed(f"the tag {tag} is not in this checkout: git fetch --depth 1 origin tag {tag}")
    archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", "--format=tar", tag, "--", *paths],
                             capture_output=True, check=True).stdout
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=__import__("io").BytesIO(archive)) as tar:
        tar.extractall(into, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return into


def tagged_file(tag: str, path: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{tag}:{path}"], capture_output=True, check=True,
                          text=True, encoding="utf-8").stdout


# --- the machine's own home, untouched ------------------------------------------------------------------------


@dataclass
class RealHome:
    """What the machine's own home holds for the programs and cad: each file's size and time, each link's target, and
    in the places an install of ours writes (``OURS``) how often each of ``needles`` (our names, the computer's folder)
    appears in a file. ``changes``: a change there that adds or drops one of them, or a path naming one, is ours; any
    other change (a running app's sessions, logs, its own catalog refreshed) is listed apart, and on CI, where nothing
    else runs, fails too."""

    roots: list[Path]
    needles: tuple[str, ...]
    listing: dict[str, tuple] = field(default_factory=dict)
    counts: dict[str, tuple[int, ...]] = field(default_factory=dict)

    OURS = tuple(re.compile(pattern) for pattern in (
        r"\.claude/plugins(/|$)", r"\.claude/settings\.json$",
        r"\.codex/config\.toml$", r"\.codex/(plugins|\.tmp)(/|$)",
        r"\.gemini/extensions(/|$)", r"\.gemini/(settings|trustedFolders)\.json$",
        r"/cad(-state)?/(default|plugin|installations|versions/[^/]+$|releases/[^/]+$)", r"/\.local/bin/cad(\.exe)?$",
        r"\.gitconfig$"))

    @classmethod
    def here(cls, programs: list[str], needles: tuple[str, ...]) -> "RealHome":
        home = Path.home()
        roots = [path for name in programs for path in PROGRAMS[name].folders(home)]
        if sys.platform == "darwin":
            roots.append(home / "Library" / "Application Support" / "cad")
        else:
            roots.append(Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "cad")
        if WINDOWS:
            roots += [Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "cad-state",
                      home / ".local" / "bin" / "cad.exe"]
        roots += [home / ".local" / "bin" / "cad", home / ".gitconfig"]
        return cls(roots, needles).taken()

    def taken(self) -> "RealHome":
        listing, counts = {}, {}
        for root in self.roots:
            for path in [root, *(_walk(root) if root.is_dir() and not root.is_symlink() else [])]:
                try:
                    found = path.lstat()
                except OSError:
                    continue
                key = path.as_posix()
                if path.is_symlink():
                    listing[key] = ("link", os.readlink(path))
                elif path.is_dir():
                    listing[key] = ("dir",)
                else:
                    listing[key] = ("file", found.st_size, found.st_mtime_ns)
                    if found.st_size <= 4_000_000 and any(pattern.search(key) for pattern in self.OURS):
                        try:
                            text = path.read_bytes().decode("utf-8", "replace")
                        except OSError:
                            continue
                        counts[key] = tuple(text.count(needle) for needle in self.needles)
        self.listing, self.counts = listing, counts
        return self

    def changes(self, after: "RealHome") -> tuple[list[str], list[str]]:
        """``(ours, other)``: each path added, removed or changed between this listing and ``after``."""
        changed = sorted(path for path in set(self.listing) | set(after.listing)
                         if self.listing.get(path) != after.listing.get(path))
        ours = [path for path in changed if any(pattern.search(path) for pattern in self.OURS)
                and (self.counts.get(path) != after.counts.get(path) or any(needle in path for needle in self.needles))]
        return ours, [path for path in changed if path not in ours]


def _walk(root: Path):
    for folder, folders, files in os.walk(root):
        for name in folders + files:
            yield Path(folder) / name


def _within(path: Path, folder: Path) -> bool:
    """Whether ``path`` is ``folder`` or inside it, both resolved."""
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(folder))
        return True
    except ValueError:
        return False


# --- the few files a person's apps and cad keep, untouched -------------------------------------------------


@dataclass
class Sentinels:
    """Each file or folder a run must never change on the machine it runs on -- the agent apps' plugin lists and
    configuration, cad's state folder and command, uv's tools and their commands, the shell profiles -- and its modification time (None
    where there is none). ``moved``: what changed between two readings. Not ``~/.claude.json``: a Claude Code
    session that is open on the machine rewrites it as it works, so a run beside one would fail for nothing; the
    plugin lists beside it, which a run could change, are watched.

    Claude Desktop's ``claude_desktop_config.json`` is watched by what an install could change there, its
    ``mcpServers`` section, parsed (``servers_of``), not by its time: the running app rewrites the file by itself
    (its ``preferences``) every few minutes."""

    times: dict[str, object]

    # The files watched by their MCP servers alone (``servers_of``), by name.
    BY_SERVERS = ("claude_desktop_config.json",)

    @classmethod
    def here(cls) -> "Sentinels":
        home = Path.home()
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        paths = [home / ".codex" / "config.toml", home / ".claude" / "plugins" / "installed_plugins.json",
                 home / ".claude" / "plugins" / "known_marketplaces.json", home / ".cursor",
                 home / ".gemini" / "extensions", home / ".local" / "bin" / ("cad.exe" if WINDOWS else "cad"),
                 home / ".local" / "bin", home / ".local" / "share" / "uv" / "tools"]
        # The shell profiles `uv tool update-shell` (which the install command runs) and uv's installer may edit.
        paths += [home / name for name in (".zshenv", ".zshrc", ".zprofile", ".bashrc", ".bash_profile",
                                           ".bash_login", ".profile")] + [home / ".config" / "fish" / "conf.d"]
        if sys.platform == "darwin":
            support = home / "Library" / "Application Support"
            paths += [support / "cad", support / "cad" / "installations" / "current", support / "Claude"
                      / "claude_desktop_config.json"]
        elif WINDOWS:
            paths += [home / ".local" / "state" / "cad", local / "cad-state",
                      Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "Claude" / "claude_desktop_config.json"]
        else:
            paths += [Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "cad"]
        times: dict[str, object] = {}
        for path in paths:
            try:
                times[str(path)] = (servers_of(path.read_bytes()) if path.name in cls.BY_SERVERS
                                    else path.stat().st_mtime)
            except OSError:
                times[str(path)] = None
        return cls(times)

    def moved(self, after: "Sentinels") -> list[str]:
        return [f"{path}: {self.times[path]} -> {after.times.get(path)}" for path in self.times
                if self.times[path] != after.times.get(path)]


def servers_of(data: bytes) -> str:
    """What an install could change in Claude Desktop's config (``data``, the file's bytes): its ``mcpServers``
    section, as canonical JSON (keys sorted), so the app's own rewrites of the rest compare equal; ``{}`` where the
    file has none. A file that is not a JSON object is compared whole, by its bytes' digest."""
    try:
        config = json.loads(data.decode("utf-8"))
    except ValueError:
        config = None
    if not isinstance(config, dict):
        return "unparsed sha256:" + hashlib.sha256(data).hexdigest()
    return json.dumps(config.get("mcpServers", {}), sort_keys=True, separators=(",", ":"))


# --- this tree's wheels as another release -----------------------------------------------------------------


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def rewrite(wheel: Path, out: Path, version: str, *, replace: dict[str, bytes] | None = None,
            commands: bool = True, requires: list[str] | None = None) -> Path:
    """``wheel`` written into ``out`` as release ``version``: its ``.dist-info`` renamed, its version and every
    requirement on ``cad==`` stamped with ``version``, ``replace``'s files (by their path in the wheel) given other
    bytes, and with ``commands`` false no console script (a release whose ``cad`` uv cannot install as a tool:
    "No executables are provided"); ``requires``: ``Requires-Dist`` lines added. Its record written again. The new
    wheel."""
    with zipfile.ZipFile(wheel) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    infos = {name.split("/", 1)[0] for name in files if name.split("/", 1)[0].endswith(".dist-info")}
    if len(infos) != 1:
        raise Failed(f"{wheel.name}: not one .dist-info ({sorted(infos)})")
    info = infos.pop()
    stem, old = info[: -len(".dist-info")].rsplit("-", 1)
    new_info = f"{stem}-{version}.dist-info"
    for name, data in (replace or {}).items():
        if name not in files:
            raise Failed(f"{wheel.name} has no {name} to replace")
        files[name] = data
    written: dict[str, bytes] = {}
    for name, data in files.items():
        if name == f"{info}/RECORD":
            continue
        if name.startswith(info + "/"):
            relative = name[len(info) + 1:]
            if relative == "METADATA":
                text = data.decode("utf-8")
                text = re.sub(r"(?m)^Version: .*$", f"Version: {version}", text, count=1)
                text = re.sub(r"(?m)^(Requires-Dist: cad(?:\[[^\]]*\])?) ?==" + re.escape(old) + r"\b",
                              rf"\g<1>=={version}", text)
                text = text.rstrip("\n") + "\n" + "".join(f"Requires-Dist: {line}\n" for line in requires or [])
                data = text.encode("utf-8")
            elif relative == "entry_points.txt" and not commands:
                data = re.sub(r"(?ms)^\[console_scripts\]\n.*?(?=^\[|\Z)", "", data.decode("utf-8")).encode("utf-8")
            name = f"{new_info}/{relative}"
        written[name] = data
    record = [_record_line(name, data) for name, data in written.items()]
    written[f"{new_info}/RECORD"] = ("\n".join([*record, f"{new_info}/RECORD,,"]) + "\n").encode("utf-8")
    tag = wheel.name[: -len(".whl")].split("-", 2)[2]
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{stem}-{version}-{tag}.whl"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, data in written.items():
            archive.writestr(name, data)
    return target


def stamp(patch: int = 9999, version: str | None = None) -> str:
    """The release a rehearsal writes this tree's wheels again as (``publish``): ``version`` (default: this tree's
    ``VERSION``) with its major and minor kept and its patch ``patch``, far above any real one (9000 and up), so it
    is newer than every release PyPI holds and uv, offered both, installs it. Never an earlier minor: once PyPI holds
    one of this tree's minor or newer, a fixed ``0.11.9xxx`` would lose to it."""
    if patch < 9000:
        raise ValueError(f"a rehearsal's patch is 9000 or above, far from a real one: {patch}")
    text = (REPO_ROOT / "VERSION").read_text(encoding="utf-8") if version is None else version
    major, minor = text.strip().split(".")[:2]
    return f"{int(major)}.{int(minor)}.{patch}"


def publish(wheels: Path, version: str, out: Path, *, replace: dict[str, bytes] | None = None,
            commands: bool = True) -> list[Path]:
    """Every wheel of one release in ``wheels`` (cad's and its aliases': cad-server, cad-mcp, cadgen) written into
    ``out`` as release ``version`` (``rewrite``; ``replace`` and ``commands`` apply to cad's own wheel). The wheels
    written."""
    found = sorted(Path(wheels).glob("*.whl"))
    releases = {path.name.split("-")[1] for path in found}
    if len(releases) != 1 or not any(path.name.startswith("cad-") for path in found):
        raise Failed(f"{wheels}: expected the wheels of one release, cad's among them: {[path.name for path in found]}")
    return [rewrite(path, out, version, **({"replace": replace, "commands": commands}
                                            if path.name.startswith("cad-") else {})) for path in found]


def quiet(state: Path) -> None:
    """Telemetry off as the person's kept choice in the state folder ``state`` (its ``settings.json``'s ``telemetry``
    section, as every release from 0.8 reads it), where nothing is kept there yet."""
    path = Path(state) / "settings.json"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"telemetry": {"choice": "off", "by": "rehearsal", "decidedAt": time.time()}}),
                    encoding="utf-8")


def protected(home: Path | None = None, environ: dict[str, str] | None = None,
              windows: bool = WINDOWS, darwin: bool = sys.platform == "darwin") -> list[Path]:
    """The person's own folders a run must never share: uv's cache, Pythons, tools and their commands (where uv's
    variables name them, and uv's defaults), cad's state, cache and command, and the agent apps' configuration."""
    environ = os.environ if environ is None else environ
    home = Path(home or Path.home())
    named = [environ.get(name) for name in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR", "UV_TOOL_BIN_DIR",
                                            "UV_INSTALL_DIR", "CAD_STATE_DIR", "CAD_CACHE_DIR")]
    found = [Path(value) for value in named if value]
    found += [home / ".local" / "bin", home / ".local" / "state" / "cad", home / ".cache" / "cad",
              home / ".claude", home / ".codex", home / ".cursor", home / ".gemini"]
    if windows:
        local = Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        roaming = Path(environ.get("APPDATA") or home / "AppData" / "Roaming")
        found += [local / "uv", roaming / "uv", local / "cad-state", local / "cad"]
    else:
        found += [Path(environ.get("XDG_CACHE_HOME") or home / ".cache") / "uv",
                  Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "uv",
                  Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "uv",
                  Path(environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "cad"]
        if darwin:
            found.append(home / "Library" / "Application Support" / "cad")
    return found


def uv_refused(path: Path, home: Path | None = None, environ: dict[str, str] | None = None,
               windows: bool = WINDOWS, darwin: bool = sys.platform == "darwin") -> bool:
    """Whether a run may not keep uv's cache or Pythons at ``path``: inside one of the person's own folders
    (``protected``), or holding one of them, or the home itself."""
    home = Path(home or Path.home())
    return _within(home, path) or any(_within(path, place) or _within(place, path)
                                      for place in protected(home, environ, windows, darwin))


def windows_images() -> list[tuple[int, str]] | None:
    """Windows: each running process's id and program path, read through the Win32 API in this process (no program
    started, no WMI); a process whose path cannot be read is left out. None where the API cannot be used."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Entry(ctypes.Structure):  # PROCESSENTRY32W
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                        ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                        ("parent", wintypes.DWORD), ("priority", ctypes.c_long), ("flags", wintypes.DWORD),
                        ("name", ctypes.c_wchar * 260)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                      ctypes.POINTER(wintypes.DWORD)]
        snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == wintypes.HANDLE(-1).value:
            return None
        found: list[tuple[int, str]] = []
        entry = Entry()
        entry.size = ctypes.sizeof(Entry)
        try:
            more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                process = kernel.OpenProcess(0x1000, False, entry.pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if process:
                    buffer, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
                    if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                        found.append((int(entry.pid), buffer.value))
                    kernel.CloseHandle(process)
                more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        return found
    except (AttributeError, OSError, ValueError):
        return None


def windows_command_line(pid: int) -> str | None:
    """Windows: the command line of process ``pid``, read through the Win32 API in this process (no WMI):
    ``NtQueryInformationProcess``'s ProcessCommandLineInformation (60), Windows 8.1 and later. None where it cannot be
    read, or elsewhere."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Text(ctypes.Structure):  # UNICODE_STRING, at the start of what the call returns
            _fields_ = [("length", wintypes.USHORT), ("maximum", wintypes.USHORT), ("buffer", ctypes.c_void_p)]

        kernel, ntdll = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("ntdll")
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        query = ntdll.NtQueryInformationProcess
        query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                          ctypes.POINTER(wintypes.ULONG)]
        query.restype = ctypes.c_long
        process = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            return None
        try:
            size = wintypes.ULONG(0)
            query(process, 60, None, 0, ctypes.byref(size))  # the size it needs
            if not size.value:
                return None
            buffer = ctypes.create_string_buffer(size.value)
            if query(process, 60, buffer, size, ctypes.byref(size)) != 0:
                return None
            text = Text.from_buffer(buffer)
            return ctypes.wstring_at(text.buffer, text.length // 2) if text.buffer else None
        finally:
            kernel.CloseHandle(process)
    except (AttributeError, OSError, ValueError):
        return None


def cad_commands(folder: Path, windows: bool = WINDOWS) -> list[Path]:
    """The ``cad`` commands in the bin folder ``folder``, in the order a shell runs them: ``cad`` on macOS and Linux;
    on Windows ``cad.exe`` (uv's, and 0.11's launcher) before ``cad.cmd`` (0.10's)."""
    names = ("cad.exe", "cad.cmd") if windows else ("cad",)
    return [Path(folder) / name for name in names]


def interpreter(env: Path) -> Path:
    """The Python of the virtual environment ``env``."""
    return Path(env) / ("Scripts/python.exe" if WINDOWS else "bin/python")


def command(env: Path, name: str = "cad") -> Path:
    """The console script ``name`` of the virtual environment ``env``."""
    return Path(env) / (f"Scripts/{name}.exe" if WINDOWS else f"bin/{name}")


if __name__ == "__main__":
    # `python scripts/test/real_computer.py stamp [PATCH]`: the release a rehearsal stamps (``stamp``), printed.
    # `python scripts/test/real_computer.py publish WHEELS VERSION OUT`: the install workflows' wheels as that release,
    # which no index holds.
    import argparse

    parser = argparse.ArgumentParser(description="This tree's wheels written again as another release.")
    actions = parser.add_subparsers(dest="action", required=True)
    stamping = actions.add_parser("stamp", help="print the release a rehearsal stamps this tree's wheels with")
    stamping.add_argument("patch", nargs="?", type=int, default=9999)
    publishing = actions.add_parser("publish", help="write the wheels in WHEELS again as VERSION into OUT")
    publishing.add_argument("wheels", type=Path)
    publishing.add_argument("version")
    publishing.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.action == "stamp":
        print(stamp(args.patch))
    else:
        for written in publish(args.wheels, args.version, args.out):
            print(written)
