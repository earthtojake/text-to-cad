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

``RealHome`` lists what the machine's own home holds for these programs and cad, to prove a run changed none of it.
``scripts/test/real-install.py`` runs the install script on it; an update rehearsal can run a shipped release on it.
The standard library alone.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"
REPOSITORY = "earthtojake/text-to-cad"
BRANCH = "latest"
# The ports the person's own servers serve on: never a test's.
TAKEN = range(3245, 3251)
DEFAULT_PORT = 3245
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


class Feed(http.server.ThreadingHTTPServer):
    """The version feed (``GET /v1/versions``) saying ``latest``; anything else (telemetry) is not found."""

    def __init__(self, latest: str) -> None:
        self.latest = latest
        feed = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                self.answer(json.dumps({"latest": feed.latest}).encode() if self.path == "/v1/versions" else None)

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

    def __init__(self, work: Path, programs: dict[str, str], *, feed: Feed | None = None) -> None:
        self.work = Path(work).resolve()
        self.home = self.work / "home"
        self.state = self.work / "state"
        self.tools = self.work / "tools"
        self.programs = programs
        self.feed = feed
        self.port = DEFAULT_PORT if default_free() else free_port()
        for folder in (self.home, self.tools, self.work / "tmp", self.state):
            folder.mkdir(parents=True, exist_ok=True)
        home = self.home
        env = {key: os.environ[key] for key in KEPT if key in os.environ}
        env.update({
            "HOME": str(home), "TMPDIR": str(self.work / "tmp"), "TEMP": str(self.work / "tmp"),
            "TMP": str(self.work / "tmp"), "TERM": "dumb", "NO_COLOR": "1", "DO_NOT_TRACK": "1", "BROWSER": "true",
            "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_STATE_HOME": str(home / ".local" / "state"), "XDG_CACHE_HOME": str(home / ".cache"),
            "CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.work / "engine"),
            "CAD_ENGINE_DEFAULT_PORT": str(self.port),
            # uv's folders, each in the computer (its defaults are in the home too; named, so none is relied on).
            "UV_CACHE_DIR": str(self.work / "uv" / "cache"), "UV_PYTHON_INSTALL_DIR": str(self.work / "uv" / "python"),
            "UV_TOOL_DIR": str(self.work / "uv" / "tools"), "UV_NO_MODIFY_PATH": "1",
            "GIT_CONFIG_GLOBAL": str(self.work / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TEMPLATE_DIR": str(self.work / "git-template"), "GIT_TERMINAL_PROMPT": "0",
        })
        if not WINDOWS:
            env["XDG_RUNTIME_DIR"] = str(self.work / "run")
            (self.work / "run").mkdir(mode=0o700, exist_ok=True)
        if WINDOWS:
            env.update({"USERPROFILE": str(home), "APPDATA": str(home / "AppData" / "Roaming"),
                        "LOCALAPPDATA": str(home / "AppData" / "Local"), "HOMEDRIVE": home.drive,
                        "HOMEPATH": str(home)[len(home.drive):]})
        if feed is not None:
            # The install script's feed, and cad's (its version feed and its telemetry: the stand-in answers neither).
            env.update({"CAD_INSTALL_FEED": f"{feed.url}/versions", "CAD_API_URL": feed.url})
        else:
            env["CAD_API_URL"] = "http://127.0.0.1:9"
        for name in programs:
            env.update(PROGRAMS[name].environ(home) if name in PROGRAMS else {})
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
        self.commit = ""
        self.nonce = ""

    # --- PATH -------------------------------------------------------------------------------------------------

    def _path(self, programs: dict[str, str]) -> str:
        """The computer's PATH: the programs, node, git and uv, and the system's own folders. On macOS and Linux each
        is linked into one folder of the computer's, so no other command of their folders comes along; on Windows,
        where npm's commands are .cmd files that run what lies beside them, their folders themselves."""
        needed = {**programs}
        for helper in ("node", "git", "uv", "uvx"):
            found = shutil.which(helper)
            if found:
                needed[helper] = found
        if WINDOWS:
            system = os.environ.get("SystemRoot", r"C:\Windows")
            folders = [str(self.tools), *dict.fromkeys(str(Path(path).parent) for path in needed.values()),
                       rf"{system}\System32", system, rf"{system}\System32\WindowsPowerShell\v1.0",
                       rf"{system}\System32\Wbem"]
            return os.pathsep.join(folders)
        for name, path in needed.items():
            link = self.tools / name
            if not link.exists():
                link.symlink_to(os.path.realpath(path))
        return os.pathsep.join([str(self.tools), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])

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
        (source / MARK).write_text(f"{self.nonce}\n", encoding="utf-8")
        for manifest in source.rglob("*.json"):
            if "skills" not in manifest.relative_to(source).parts:
                text = manifest.read_text(encoding="utf-8")
                manifest.write_text(text.replace(f'"version": "{version}"', f'"version": "{following}"'), "utf-8")
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
        """Every process whose command line names the computer's folder, but this one."""
        if WINDOWS:
            listing = ["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"]
        else:
            listing = ["ps", "-axo", "pid=,command="]
        listed = subprocess.run(listing, capture_output=True, text=True, errors="replace").stdout
        found = []
        mark = str(self.work).lower() if WINDOWS else str(self.work)
        for line in listed.splitlines():
            pid, _, command = line.strip().partition(" ")
            if pid.isdigit() and int(pid) != os.getpid() and mark in (command.lower() if WINDOWS else command):
                found.append((int(pid), command))
        return found

    def stop(self, cad: Path | None = None) -> list[str]:
        """The computer's cad server stopped by its own command, then anything still running from its folder
        ended. What had to be ended, which the caller treats as a process left behind."""
        if cad is not None and cad.exists():
            self.run([cad, "stop"])
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
