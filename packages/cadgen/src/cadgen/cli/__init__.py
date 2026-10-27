"""The ``cadgen`` console script -- a subcommand dispatcher over the distribution's CLIs.

Every subcommand is also reachable as ``python -m cadgen.<module>``; this is the friendly
front door, not a second implementation. A subcommand's parser lives in its own module and
owns its arguments, so the console and module entry points cannot drift. The engine's verbs
(``export``, ``snapshot``, ``serve``, ``inspect``, ``status``, ``stop``, ``delete``, ``server``) are
``cadgen.engine.cli``'s, each run by its name; the robot validators' parsers are DERIVED from
the verb function's signature (``cadgen._internal.cli_from_function``).

**Dispatch is lazy on purpose.** Importing a CAD subcommand pulls in OCP/build123d, which
costs seconds and needs the heavy dependency set installed. ``cadgen --help`` and an
unknown command must not pay for that, so the registry stores dotted module names as
strings and imports exactly the one being run. Do not hoist these to module-level imports
when adding commands.
"""

from __future__ import annotations

import importlib
import os
import re
import sys

# name -> (module, "one-line help"). The module must expose ``main(argv)`` returning an
# exit code. Keep this list grouped as below and the help text under ~60 chars so
# ``cadgen --help`` stays a single readable column.
#
# Two-word names are intentional where a noun has several verbs. Dispatch joins
# argv[0:2] before argv[0], so the two-word form wins where it exists.
#
# A model script builds by running it (``python <model>.py``, or ``cadgen run <model>.py`` with this
# installation's python): no command takes its place.
_COMMANDS: dict[str, tuple[str, str]] = {
    # The engine (cadgen.engine): documents exported, drawn and served, its server.
    "export": ("cadgen.cli.export", "write an .xbf or a .step to STEP, GLB, STL, 3MF, DXF or xbf"),
    "snapshot": ("cadgen.cli.snapshot", "render any supported file to an image"),
    "serve": ("cadgen.cli.serve", "serve a document over HTTP and print its URL"),
    "inspect": ("cadgen.cli.inspect", "an xbf's build closure, or what made one element of it"),
    "status": ("cadgen.cli.status", "show the engine server's workers and what it serves"),
    "stop": ("cadgen.cli.stop", "stop the engine server"),
    "delete": ("cadgen.cli.delete", "delete documents: record, cached document, the engine's copy"),
    "server": ("cadgen.cli.server", "run the engine server in this process"),
    # DXF and robot descriptions: each format's snapshot draws its own files alone (the engine's
    # snapshot), and the robot validators check a description.
    "dxf snapshot": ("cadgen.cli.dxf_snapshot", "render a DXF to an image"),
    "urdf validate": ("cadgen.cli.urdf_validate", "validate a URDF robot description"),
    "urdf snapshot": ("cadgen.cli.urdf_snapshot", "render a URDF to an image"),
    "sdf validate": ("cadgen.cli.sdf_validate", "validate an SDF world or model"),
    "sdf snapshot": ("cadgen.cli.sdf_snapshot", "render an SDF to an image"),
    "srdf validate": ("cadgen.cli.srdf_validate", "validate an SRDF against its URDF"),
    "pcb drc": ("cadgen.cli.pcb_drc", "check a saved KiCad board with KiCad"),
    "pcb snapshot": ("cadgen.cli.pcb_snapshot", "render a saved KiCad board"),
    # Generic / services
    "run": ("cadgen.cli.run", "run a model script (or -m, -c) with this installation's python"),
    "doctor": ("cadgen.cli.doctor", "install: register, write the cadgen command, start the engine"),
    # A page session on the installation engine; the launcher exits.
    "viewer": ("cadgen.cli.viewer", "open a viewer page on the installation engine"),
    # CAD inside an agent host's panels. The host starts a stateless stdio peer per session.
    "mcp": ("cadgen.cli.mcp", "serve CAD to an agent host over MCP (stdio)"),
    "telemetry": ("cadgen.cli.telemetry", "show or change the usage stats and crash reports CAD sends: status, on, off"),
}

# A skill's pin is the version its SKILL.md's install command names
# (`uvx ... --from cadgen==1.2.3 cadgen doctor`), stamped by the release with its `cadgen +1.2.3`;
# else the version its commands run by (`cadgen +1.2.3`, a development install's
# `cadgen +1.2.3-dev.<time>`).
_PIN_RE = re.compile(r"--from\s+cadgen==(?P<pin>[^\s`'\"]+)")
_RUN_PIN_RE = re.compile(r"(?<![\w.-])cadgen\s+\+(?P<pin>[0-9][0-9A-Za-z.+_-]*[0-9A-Za-z])")


def read_skill_pin(skill_path) -> str | None:
    """The cadgen version a SKILL.md pins, or ``None``.

    ``None`` covers the non-cases uniformly: file absent or unreadable, or no install command
    with a pin (a development install rewrites it to the checkout's interpreter). The caller
    decides what a mismatch means (``cadgen doctor`` reports it and exits 3). String comparison
    rather than PEP 440 on purpose: the release stamps the pin mechanically.
    """
    try:
        with open(skill_path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None
    match = _PIN_RE.search(text) or _RUN_PIN_RE.search(text)
    return match.group("pin") if match else None


_USAGE_HEAD = "usage: cadgen <command> [args...]\n\ncommands:\n"
_USAGE_TAIL = (
    "\nRun 'cadgen <command> --help' for a command's own options.\n"
    "Each command is also available as 'python -m <module>'.\n"
)


def _command_lines(names) -> str:
    width = max((len(name) for name in _COMMANDS), default=0)
    return "\n".join(f"  {name.ljust(width)}  {_COMMANDS[name][1]}" for name in sorted(names)) + "\n"


def _usage() -> str:
    return _USAGE_HEAD + _command_lines(_COMMANDS) + _USAGE_TAIL


def _format_verbs(noun: str) -> list[str]:
    """The two-word commands of one format noun (``urdf`` -> ``urdf validate``, ...)."""
    return [name for name in _COMMANDS if name.split(" ")[0] == noun and " " in name]


def _format_usage(noun: str) -> str:
    return (
        f"usage: cadgen {noun} <verb> [args...]\n\n{noun} commands:\n"
        + _command_lines(_format_verbs(noun))
        + f"\nRun 'cadgen {noun} <verb> --help' for a command's own options.\n"
    )


def _harden_std_stream_errors() -> None:
    """Make an unencodable character survive as an escape instead of killing the write.

    Windows gives a CLI process a legacy code page, and under strict error
    handling a character it cannot represent raises UnicodeEncodeError -- from
    the MESSAGE rather than from the work, which is the worst possible moment.
    cp1252 happens to carry the em dash and ellipsis this repo's teaching
    messages use, but an OEM console page (cp437, cp850) carries neither, and a
    user's own path can contain anything at all.

    Only the error HANDLER changes. Switching the encoding to utf-8 was tried
    and reverted: it fixed how CI logs render and broke everything on Windows
    that decodes our output with the platform's own code page -- including this
    repo's own subprocess tests, where a cold build then reported an error
    differently from a warm one. What we emit stays what the platform expects;
    what cannot be emitted degrades to a backslash-u escape, which a reader
    can decode,
    rather than to a question mark that destroys it.

    CLI ENTRY POINTS ONLY: these are process globals owned by whoever embedded
    us, so a library import must never touch them.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # a caller replaced it with a plain object
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (OSError, ValueError):  # detached or already closed
            pass


def main(argv: list[str] | None = None) -> int:
    try:
        code = _main(argv)
        if sys.stdout is not None:
            sys.stdout.flush()  # here, not as Python exits, where a closed pipe could only be complained about
        return code
    except BrokenPipeError:
        from cadgen.analytics import stdout_closed

        if not stdout_closed():
            raise  # another pipe it wrote to (a child's stdin): a failure like any other
        return _output_closed()


def _output_closed() -> int:
    """Whatever read this command's output closed it (``cadgen ... | head``): stop quietly, as a CLI does
    on SIGPIPE -- no traceback, no crash report (``cadgen.analytics.stdout_closed``), nothing more written. Both
    streams go to the null device first: Python flushes them again as it exits, and would print that
    flush's own BrokenPipeError."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return 1
    for stream in (sys.stdout, sys.stderr):
        try:
            os.dup2(devnull, stream.fileno())
        except (AttributeError, OSError, ValueError):  # not a real file: nothing of the process's to quiet
            pass
    os.close(devnull)
    import signal

    return 128 + signal.SIGPIPE if hasattr(signal, "SIGPIPE") else 1  # what a shell reports for `yes | head`


def _main(argv: list[str] | None) -> int:
    _harden_std_stream_errors()
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in {"-h", "--help", "help"}:
        sys.stdout.write(_usage())
        return 0

    if argv[0] in {"-V", "--version"}:
        # The installation's own version, as doctor's header says it: a development install's
        # name (0.8.0-dev.<stamp>), so two installations are told apart; else the package's.
        from cadgen import __version__
        from cadgen._internal.installations import own_version

        sys.stdout.write(f"cadgen {own_version() or __version__}\n")
        return 0

    # Longest match first, so `dxf snapshot` is dispatched as one command.
    command, rest = " ".join(argv[:2]), argv[2:]
    entry = _COMMANDS.get(command)
    if entry is None:
        command, rest = argv[0], argv[1:]
        entry = _COMMANDS.get(command)
    if entry is None:
        noun = argv[0]
        if _format_verbs(noun):
            # A known format with a missing, unknown or `--help` verb: the noun is
            # right, so answer with ITS verbs rather than calling the noun unknown.
            if rest[:1] and rest[0] in {"-h", "--help", "help"}:
                sys.stdout.write(_format_usage(noun))
                return 0
            problem = f"unknown {noun} command {rest[0]!r}" if rest else f"{noun} needs a verb"
            sys.stderr.write(f"cadgen: {problem}\n\n" + _format_usage(noun))
            return 2
        sys.stderr.write(f"cadgen: unknown command {noun!r}\n\n" + _usage())
        return 2

    # No command says a newer text-to-cad is out: it cannot tell which plugin, if any, it came
    # with, so the CAD app and the CAD Viewer say it (`cadgen/updates.py`). What a command does say,
    # once and before its work, is what those two send by default (`cadgen/analytics.py`).
    if command not in _UNTOLD:
        _tell()
    try:
        return _run(command, entry[0], rest)
    except BrokenPipeError as error:
        from cadgen.analytics import stdout_closed

        if not stdout_closed():  # its output's reader left: `main` stops quietly; any other pipe is a failure
            _report(error)
        raise
    except Exception as error:
        _report(error)
        raise


def _report(error: Exception) -> None:
    """A command that failed past its own reporting -- a crash of cadgen's -- kept for telemetry
    (``cadgen.analytics.report``); the traceback is the person's, as ever."""
    try:
        from cadgen.analytics import report
    except Exception:  # noqa: BLE001 - a crash report never adds a failure to one
        return
    report(error, "command", handled=False)


# Commands that never carry the analytics notice: a CAD app's server, whose output only the host's log
# reads; the engine's server, writing nowhere; `telemetry`, which says it its own way; and `run`, which is
# only the python it runs, as the `cadgen` command's `run` is.
_UNTOLD = frozenset({"mcp", "server", "telemetry", "run"})


def _tell() -> None:
    """Say, once, what CAD's apps send by default (``cadgen.analytics.notify``): one line on stderr,
    never in a command's output or its way."""
    try:
        from cadgen.analytics import notify
    except Exception:  # noqa: BLE001 - the notice never fails the command it rides on
        return
    notify()


def _run(command: str, module_name: str, rest: list[str]) -> int:
    # The engine's verbs this command runs are counted as a command's (`cadgen/_internal/engine_telemetry.py`).
    from cadgen._internal import engine_telemetry

    engine_telemetry.command = command
    return _run_module(command, module_name, rest)


def _run_module(command: str, module_name: str, rest: list[str]) -> int:
    module = importlib.import_module(module_name)

    # Tell the parser which front door it was reached through, so
    # `cadgen urdf validate --help` says "cadgen urdf validate".
    # Not every command takes a name for its parser, hence the signature check rather
    # than a blanket keyword.
    import inspect  # only the dispatcher needs it; `--help` does not.

    if "prog" in inspect.signature(module.main).parameters:
        return int(module.main(rest, prog=f"cadgen {command}") or 0)
    return int(module.main(rest) or 0)
