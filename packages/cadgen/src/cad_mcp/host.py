"""Which host launched this process, read from its parent processes: what only this process can see.

A host's greeting does not always say whether it shows CAD cards: Codex greets the server as
``codex-mcp-client`` and declares no MCP Apps extension from its desktop app (which shows them as tabs), from
``codex exec`` or from its terminal UI (which show none), and Claude Code's terminal declares none either. The
process that started this one does say: the first ancestor that is not a launcher (uv, a Python, a shell) is
the host, and its program and subcommand name it. This process reads it once as it starts (``launcher``) and
hands it to the server with the host's initialize, which weighs it (the server's ``host.presentation``).
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

UI_EXTENSION = "io.modelcontextprotocol/ui"
TABS_EXTENSION = "dev.texttocad/tabs"
MIME = "text/html;profile=mcp-app"  # an MCP App's page, which the ui extension lists

# The processes between a host and this server that are not the host: what runs a command for it
# (Claude Desktop's ``disclaimer`` helper among them, which starts Claude Code's sessions), and the
# init a walk ends at, pid 1, when that is not the host itself (a container's entrypoint can be).
# A Python is not one: a host's plugin config runs cadgen through uvx (uv, then this process) or a
# venv's Python (this process), so a Python above this one is a client of its own, as a test is.
_LAUNCHERS = frozenset({"uv", "uvx", "sh", "bash", "zsh", "dash", "fish", "env", "nohup", "cadgen", "disclaimer",
                        "npx", "npm", "init", "systemd", "tini", "docker-init", "dumb-init"})
# Codex's options that take a value spelled apart from it (``-c key=value``), before its subcommand.
_CODEX_VALUED = frozenset({"-c", "--config", "-m", "--model", "-p", "--profile", "-s", "--sandbox",
                           "-a", "--ask-for-approval", "-C", "--cd", "-i", "--image", "--add-dir",
                           "--enable", "--disable", "--local-provider", "--remote", "--remote-auth-token-env"})
# Codex's subcommands that run turns and show no app: exec (``e``) and review, and its terminal UI (no
# subcommand, a prompt, ``resume``, ``fork``). Only its app server -- the Codex desktop app's, inside
# its bundle, and its editor extensions' -- shows CAD tabs.
_CODEX_TEXT = frozenset({"exec", "e", "review", "resume", "fork"})
_CODEX_SUBCOMMANDS = _CODEX_TEXT | {"login", "logout", "mcp", "mcp-server", "app-server", "app", "completion",
                                    "sandbox", "debug", "apply", "cloud", "exec-server", "features", "help"}
_DEPTH = 12


def _name(path: str) -> str:
    name = os.path.basename(path.rstrip("/\\")).lower()
    return name[:-4] if name.endswith(".exe") else name


def _codex_subcommand(args: list[str]) -> str | None:
    """The subcommand of a ``codex`` command line (its arguments after the program), else None."""
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in _CODEX_VALUED:
            skip = True
        elif not arg.startswith("-"):
            return arg if arg in _CODEX_SUBCOMMANDS else None  # anything else is the terminal UI's prompt
    return None


def classify(argv: list[str]) -> dict[str, Any] | None:
    """The host one process is, from its command line: ``{"host", "renders"}``, ``renders`` True where
    it shows CAD cards, False where it shows none, None for a program this does not know; or None
    where the process is not a host but what launched this server for one (a launcher, a Python)."""
    if not argv:
        return None  # a parent read with no command line (a zombie, one exiting): its parent says
    program, args = _name(argv[0]), argv[1:]
    if program in ("node", "bun") and args:
        # An npm install of a host runs its script under node: the script names it.
        script = args[0].replace("\\", "/")
        if _name(script) in ("codex", "codex.js"):
            program, args = "codex", args[1:]
        elif "/@anthropic-ai/claude-code/" in script:
            program, args = "claude", args[1:]
        elif _name(script) in ("npx-cli.js", "npm-cli.js"):
            return None
    if program == "codex":
        sub = _codex_subcommand(args)
        if sub == "app-server":
            return {"host": "codex app-server", "renders": True}
        if sub is None or sub in _CODEX_TEXT:
            return {"host": f"codex {sub}" if sub else "codex", "renders": False}
        return {"host": f"codex {sub}", "renders": None}
    if "/Claude.app/Contents/" in argv[0] and os.path.basename(argv[0]) == "Claude":
        # The desktop app's own program, whose name is Claude Code's but for its case.
        return {"host": "claude desktop", "renders": True}
    if program == "claude":
        # Claude Code: its terminal, and the desktop app's code sessions, which run this program too.
        # It shows no cards unless it declares the extension (``CLAUDE_CODE_MCP_APPS_HOST=1``).
        return {"host": "claude code", "renders": False}
    if program in _LAUNCHERS:
        return None
    if "/Claude.app/Contents/" in argv[0]:
        return {"host": "claude desktop", "renders": True}
    return {"host": program, "renders": None}


def host_of(chain: list[list[str]]) -> dict[str, Any] | None:
    """The host among a server's ancestors, nearest first: the first that is not a launcher, with its
    command line; None where every one is a launcher (or there are none)."""
    for argv in chain:
        found = classify(argv)
        if found is not None:
            return {**found, "command": " ".join(argv)[:400]}
    return None


def _darwin_argv(pid: int) -> list[str] | None:
    """A process's arguments as it was started, exactly (``KERN_PROCARGS2``); None where they cannot be read."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0 or not size.value:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
        return None
    raw = buffer.raw[:size.value]
    argc = int.from_bytes(raw[:4], sys.byteorder)
    rest = raw[4:]
    rest = rest[rest.find(b"\0"):].lstrip(b"\0")  # the executable's path, its padding, then argv
    return [arg.decode("utf-8", "replace") for arg in rest.split(b"\0")[:argc]]


def _ancestors_darwin(pid: int) -> list[list[str]]:
    table = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True, timeout=5).stdout
    parents: dict[int, int] = {}
    commands: dict[int, str] = {}
    for row in table.splitlines():
        fields = row.split(None, 2)
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            parents[int(fields[0])] = int(fields[1])
            commands[int(fields[0])] = fields[2] if len(fields) > 2 else ""
    chain = []
    while pid > 1 and len(chain) < _DEPTH and pid in parents:
        chain.append(_darwin_argv(pid) or commands[pid].split())
        pid = parents[pid]
    return chain


def _ancestors_linux(pid: int) -> list[list[str]]:
    """The command lines from ``/proc``, up to and with pid 1, whose parent is 0: in a container,
    pid 1 is its entrypoint, which can be the host."""
    chain = []
    while pid > 0 and len(chain) < _DEPTH:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                argv = handle.read().rstrip(b"\0").split(b"\0")
            with open(f"/proc/{pid}/stat", "rb") as handle:
                stat = handle.read()
        except OSError:
            break
        chain.append([arg.decode("utf-8", "replace") for arg in argv if arg])
        pid = int(stat[stat.rindex(b")") + 2:].split()[1])  # after the state, the parent
    return chain


def ancestors(pid: int | None = None) -> list[list[str]]:
    """The command lines of ``pid`` and its ancestors (this process's parent by default), nearest
    first: read on macOS and Linux, none elsewhere."""
    start = os.getppid() if pid is None else pid
    try:
        if sys.platform == "darwin":
            return _ancestors_darwin(start)
        if sys.platform.startswith("linux"):
            return _ancestors_linux(start)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return []


def launcher() -> dict[str, Any] | None:
    """The host that launched this process (``host_of`` its ancestors), or None where none is known."""
    return host_of(ancestors())


def family(found: Any) -> str | None:
    """The host a launcher (``launcher``) names, as its shells name it:
    ``codex`` for each of Codex's programs, ``claude code``, else the host's own name; None where none
    is known."""
    name = str(found.get("host") or "") if isinstance(found, dict) else ""
    return "codex" if name.startswith("codex") else (name or None)
