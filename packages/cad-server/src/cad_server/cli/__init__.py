"""The ``cad`` console script -- a subcommand dispatcher over the distribution's CLIs.

Every subcommand is also reachable as ``python -m cad_server.cli.<module>``; this is the friendly
front door, not a second implementation. A subcommand's parser lives in its own module and
owns its arguments, so the console and module entry points cannot drift. The engine's verbs
(``export``, ``snapshot``, ``serve``, ``inspect``, ``status``, ``stop``, ``delete``, ``server``) are
``cad_server.engine.cli``'s, each run by its name; the robot validators' parsers are DERIVED from
the verb function's signature (``cad_server._internal.cli_from_function``).

**Dispatch is lazy on purpose.** Importing a CAD subcommand pulls in OCP/build123d, which
costs seconds and needs the heavy dependency set installed. ``cad --help`` and an
unknown command must not pay for that, so the registry stores dotted module names as
strings and imports exactly the one being run. Do not hoist these to module-level imports
when adding commands.
"""

from __future__ import annotations

import importlib
import os
import sys

# name -> (module, "one-line help"). The module must expose ``main(argv)`` returning an
# exit code. Keep this list grouped as below and the help text under ~60 chars so
# ``cad --help`` stays a single readable column.
#
# Two-word names are intentional where a noun has several verbs. Dispatch joins
# argv[0:2] before argv[0], so the two-word form wins where it exists.
#
# A model script builds by running it (``cad run <model>.py``: the CAD kernel environment's
# ``python <model>.py``): no command takes its place.
_COMMANDS: dict[str, tuple[str, str]] = {
    # The engine (cad.engine): documents exported, drawn and served, its server.
    "export": ("cad_server.cli.export", "write an .xbf or a .step to STEP, GLB, STL, 3MF, DXF or xbf"),
    "snapshot": ("cad_server.cli.snapshot", "render any supported file to an image"),
    "serve": ("cad_server.cli.serve", "serve a document over HTTP and print its URL"),
    "inspect": ("cad_server.cli.inspect", "an xbf's build closure, or what made one element of it"),
    "status": ("cad_server.cli.status", "show the engine server's workers and what it serves"),
    "stop": ("cad_server.cli.stop", "stop the engine server"),
    "delete": ("cad_server.cli.delete", "delete documents: record, cached document, the engine's copy"),
    "server": ("cad_server.cli.server", "run the engine server in this process"),
    # Robot descriptions: the validators check a description (the engine's snapshot draws one).
    "urdf validate": ("cad_server.cli.urdf_validate", "validate a URDF robot description"),
    "sdf validate": ("cad_server.cli.sdf_validate", "validate an SDF world or model"),
    "srdf validate": ("cad_server.cli.srdf_validate", "validate an SRDF against its URDF"),
    # Generic / services
    "run": ("cad_server.cli.run", "run a model script (or -m, -c) in the CAD kernel environment"),
    "doctor": ("cad_server.cli.doctor", "install: register, write the cad command, start the engine"),
    # text-to-cad in every agent app here, and the cad command with it, as this release; `update`
    # runs the newest release's. `uninstall` is setup's uninstall path, with a parser of its own.
    "setup": ("cad_server.cli.setup", "set up text-to-cad in every agent app here, as this release"),
    "update": ("cad_server.cli.update", "install the newest release and set it up in every agent app here"),
    "update auto": ("cad_server.cli.update_auto", "show or change automatic updates: status, on, off"),
    "uninstall": ("cad_server.cli.uninstall", "take text-to-cad out of every agent app here"),
    # The folder every agent app's plugin comes from, written from the current installation.
    "plugin": ("cad_server.cli.plugin", "write the agent apps' plugin folder and print its path"),
    # A page session on the installation engine; the launcher exits. (CAD inside an agent host's panels is
    # the shim's own command, ``cad-mcp``: the host starts that stdio peer per session.)
    "viewer": ("cad_server.cli.viewer", "open a viewer page on the installation engine"),
    "telemetry": ("cad_server.cli.telemetry", "show or change the usage stats and crash reports CAD sends: status, on, off"),
}

_USAGE_HEAD = "usage: cad <command> [args...]\n\ncommands:\n"
_USAGE_TAIL = (
    "\nRun 'cad <command> --help' for a command's own options.\n"
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
        f"usage: cad {noun} <verb> [args...]\n\n{noun} commands:\n"
        + _command_lines(_format_verbs(noun))
        + f"\nRun 'cad {noun} <verb> --help' for a command's own options.\n"
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
        from cad_server.analytics import stdout_closed

        if not stdout_closed():
            raise  # another pipe it wrote to (a child's stdin): a failure like any other
        return _output_closed()


def _output_closed() -> int:
    """Whatever read this command's output closed it (``cad ... | head``): stop quietly, as a CLI does
    on SIGPIPE -- no traceback, no crash report (``cad_server.analytics.stdout_closed``), nothing more written. Both
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
        from cad_server import __version__
        from cad_server._internal.installations import own_version

        sys.stdout.write(f"cad {own_version() or __version__}\n")
        return 0

    # Longest match first, so `urdf validate` is dispatched as one command.
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
            sys.stderr.write(f"cad: {problem}\n\n" + _format_usage(noun))
            return 2
        sys.stderr.write(f"cad: unknown command {noun!r}\n\n" + _usage())
        return 2

    # `doctor` registers this installation, as `setup` does: on a device an earlier release set up, what
    # this release keeps of its state folder moves into its own first, before the notice below writes there.
    if command in _REGISTERS:
        _adopt()
    # No command says a newer text-to-cad is out: it cannot tell which plugin, if any, it came
    # with, so the CAD app and the CAD Viewer say it (`cad_server/updates.py`). What a command does say,
    # once and before its work, is what those two send by default (`cad_server/analytics.py`).
    if command not in _UNTOLD:
        _tell()
    try:
        return _run(command, entry[0], rest)
    except BrokenPipeError as error:
        from cad_server.analytics import stdout_closed

        if not stdout_closed():  # its output's reader left: `main` stops quietly; any other pipe is a failure
            _report(error)
        raise
    except Exception as error:
        _report(error)
        raise


def _report(error: Exception) -> None:
    """A command that failed past its own reporting -- a crash of the server's -- kept for telemetry
    (``cad_server.analytics.report``); the traceback is the person's, as ever."""
    try:
        from cad_server.analytics import report
    except Exception:  # noqa: BLE001 - a crash report never adds a failure to one
        return
    report(error, "command", handled=False)


# Commands that never carry the analytics notice: the engine's server, writing nowhere; `telemetry` and
# `setup` (`update`), which say it their own way; `uninstall`; `run`, which is only the python it runs,
# as the `cad` command's `run` is; and `plugin`, which a switch runs with no one to read it.
_UNTOLD = frozenset({"server", "telemetry", "setup", "update", "uninstall", "run", "plugin"})


# The told commands that register this installation (``cad_server._internal.installations.setup``).
_REGISTERS = frozenset({"doctor"})


def _adopt() -> None:
    """What this release keeps of an earlier release's state folder, moved into its own
    (``cad.engine.places.adopt_earlier``): never in a command's way."""
    try:
        from cad.engine.places import adopt_earlier

        adopt_earlier()
    except Exception:  # noqa: BLE001 - registration tries again, and says what it could not write
        return


def _tell() -> None:
    """Say, once, what CAD's apps send by default (``cad_server.analytics.notify``): one line on stderr,
    never in a command's output or its way."""
    try:
        from cad_server.analytics import notify
    except Exception:  # noqa: BLE001 - the notice never fails the command it rides on
        return
    notify()


def _run(command: str, module_name: str, rest: list[str]) -> int:
    # The engine's verbs this command runs are counted as a command's (`cad_server/_internal/engine_telemetry.py`).
    from cad_server._internal import engine_telemetry

    engine_telemetry.command = command
    return _run_module(command, module_name, rest)


def _run_module(command: str, module_name: str, rest: list[str]) -> int:
    module = importlib.import_module(module_name)

    # Tell the parser which front door it was reached through, so
    # `cad urdf validate --help` says "cad urdf validate".
    # Not every command takes a name for its parser, hence the signature check rather
    # than a blanket keyword.
    import inspect  # only the dispatcher needs it; `--help` does not.

    if "prog" in inspect.signature(module.main).parameters:
        return int(module.main(rest, prog=f"cad {command}") or 0)
    return int(module.main(rest) or 0)
