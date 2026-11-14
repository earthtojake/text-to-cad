"""The ``cad`` console script -- a subcommand dispatcher over the distribution's CLIs.

Three kinds of command. A document type's: ``cad <document_type> <operation> <file>``, one per type in
the registry (``cad.registry``), each its own module, ``cad_server.cli.<type>``
(``cad_server.cli.document_types``: ``cad xbf export``, ``cad stl snapshot``, ``cad urdf validate``). An
integration's, for its tool's own files, which are no document type, which cad checks or writes and never
shows: ``cad <integration> <operation> [<file>]`` (``cad_server.cli.integrations``: ``cad mujoco check``,
``cad orcaslicer presets``), only for the integrations the registry gives operations. And the commands that are no file's: the engine's process control (``serve``, ``status``, ``stop``,
``delete``, ``server``), ``run``, and the installation's (``setup``, ``update``, ``uninstall``,
``doctor``, ``plugin``, ``viewer``, ``telemetry``).

A command line may start with a pin, ``cad +<version>[@<channel>] ...``, as every command a skill runs does:
the ``cad`` command runs the version it names, and that version reads it here before anything else
(``cad_server._internal.pins``): a pin to another version is refused (exit 5), and the pin's channel is moved to
this version where it is behind it, or the command refused as stale where it is ahead (exit 4).

Every command is also reachable as ``python -m <module>``; this is the friendly front door, not a
second implementation. A command's parser lives in its own module and owns its arguments, so the
console and module entry points cannot drift.

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

from cad.registry import DOCUMENT_TYPES, INTEGRATIONS

# name -> (module, "one-line help"). The module must expose ``main(argv)`` returning an
# exit code. Keep this list grouped as below and the help text under ~60 chars so
# ``cad --help`` stays a single readable column. The document types' commands are not here:
# they are the registry's (``TYPE_COMMANDS``).
#
# A model script builds by running it (``cad run <model>.py``: ``uv run``, cad pinned, in the environment the
# device's engine makes for it): no command takes its place.
_COMMANDS: dict[str, tuple[str, str]] = {
    # The engine's process control: documents served, its server, and documents deleted.
    "serve": ("cad_server.cli.serve", "serve a document over HTTP and print its URL"),
    "status": ("cad_server.cli.status", "show the engine server's workers and what it serves"),
    "stop": ("cad_server.cli.stop", "stop the engine server"),
    "delete": ("cad_server.cli.delete", "delete documents: record, cached document, the engine's copy"),
    "server": ("cad_server.cli.server", "run the engine server in this process"),
    # Generic / services
    "run": ("cad_server.cli.run", "run a script (or -m, -c) as uv run does, cad pinned at this device's release "
                                  "with the integrations its imports use"),
    # The installation: the requirement a Python of a program's own installs this device's cad by.
    "requirement": ("cad_server.cli.requirement", "print the exact cad requirement for a Python of a program's own"),
    "doctor": ("cad_server.cli.doctor", "set the server up and report it (--check: report only)"),
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

# Each document type's command, by its id: ``cad <type> <operation>`` (``cad_server.cli.document_types``).
TYPE_COMMANDS: dict[str, str] = {document_type: f"cad_server.cli.{document_type}" for document_type in DOCUMENT_TYPES}

# Each integration's command, by its name, for those with operations of their own on their tool's files:
# ``cad <integration> <operation>`` (``cad_server.cli.integrations``). A name is a type's or an integration's,
# never both (``tests/python/packages/cad/test_registry.py``).
INTEGRATION_COMMANDS: dict[str, str] = {name: f"cad_server.cli.{name}" for name, entry in INTEGRATIONS.items()
                                        if entry.operations}

_USAGE_HEAD = ("usage: cad <document_type> <operation> FILE [args...] | cad <integration> <operation> [FILE] [args...]\n"
               "       | cad <command> [args...]\n\n")
_USAGE_TAIL = (
    "\nRun 'cad <document_type> --help' for a type's operations ('cad <integration> --help' for an\n"
    "integration's), 'cad <document_type> <operation> --help' or 'cad <command> --help' for its options.\n"
    "Each command is also available as 'python -m <module>'.\n"
)


def _command_lines(names) -> str:
    width = max((len(name) for name in _COMMANDS), default=0)
    return "\n".join(f"  {name.ljust(width)}  {_COMMANDS[name][1]}" for name in sorted(names)) + "\n"


def _type_lines() -> str:
    """The document types, grouped: each with its operations and what it is (``cad.registry``)."""
    from cad_server.cli.document_types import operations_of

    width = max(len(name) for name in DOCUMENT_TYPES)
    ops = {name: ", ".join(operations_of(name)) for name in DOCUMENT_TYPES}
    ops_width = max(len(text) for text in ops.values())
    return "\n".join(f"  {name.ljust(width)}  {ops[name].ljust(ops_width)}  {entry.title}: "
                     f"{', '.join(entry.extensions) or 'a document id, held in memory'}"
                     for name, entry in DOCUMENT_TYPES.items()) + "\n"


def _integration_lines() -> str:
    """The integrations with operations of their own, each with them and the files they take, or, for one whose
    tool's files are found by name in its own folders, that tool (``cad.registry``)."""
    width = max(len(name) for name in INTEGRATION_COMMANDS)
    ops = {name: ", ".join(INTEGRATIONS[name].operation_names) for name in INTEGRATION_COMMANDS}
    ops_width = max(len(text) for text in ops.values())

    def takes(entry) -> str:
        if entry.files:
            return f"{entry.operations[0].summary.split(':')[0]}: {', '.join(entry.files)}"
        return f"found by name in {entry.summary.split(',')[0]}'s own folders"

    return "\n".join(f"  {name.ljust(width)}  {ops[name].ljust(ops_width)}  {takes(INTEGRATIONS[name])}"
                     for name in INTEGRATION_COMMANDS) + "\n"


def _usage() -> str:
    return (_USAGE_HEAD + "document types, the files cad shows (cad <type> <operation> FILE):\n" + _type_lines()
            + "\nintegrations, for a tool's own files cad checks or writes and does not show (cad <integration> "
              "<operation> [FILE]):\n" + _integration_lines()
            + "\ncommands:\n" + _command_lines(_COMMANDS) + _USAGE_TAIL)


def resolve(argv: list[str]) -> tuple[str, list[str]] | None:
    """The command a command line names, as ``main`` dispatches it, and its arguments: ``("xbf export",
    [...])`` for a document type's operation, ``("status", [...])`` for a command; None for neither."""
    if argv[:1] and argv[0] in TYPE_COMMANDS:
        from cad_server.cli.document_types import OPERATIONS

        if len(argv) > 1 and (argv[0], argv[1]) in OPERATIONS:
            return f"{argv[0]} {argv[1]}", argv[2:]
        return None
    if argv[:1] and argv[0] in INTEGRATION_COMMANDS:
        from cad_server.cli.integrations import OPERATIONS as INTEGRATION_OPERATIONS

        if len(argv) > 1 and (argv[0], argv[1]) in INTEGRATION_OPERATIONS:
            return f"{argv[0]} {argv[1]}", argv[2:]
        return None
    if " ".join(argv[:2]) in _COMMANDS:  # a two-word command (``update auto``) before its first word
        return " ".join(argv[:2]), argv[2:]
    if argv[:1] and argv[0] in _COMMANDS:
        return argv[0], argv[1:]
    return None


def build_parser_for(name: str):
    """The parser a resolved command (``resolve``) parses with, or None for one that builds its own."""
    if name not in _COMMANDS:  # a document type's operation (``xbf export``), or an integration's (``mujoco check``)
        document_type, operation = name.split(" ", 1)
        if document_type in INTEGRATION_COMMANDS:
            from cad_server.cli.integrations import build_parser as integration_parser

            return integration_parser(document_type, operation)
        from cad_server.cli.document_types import build_parser

        return build_parser(document_type, operation)
    builder = getattr(importlib.import_module(_COMMANDS[name][0]), "build_parser", None)
    return builder() if builder is not None else None


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
    argv = list(sys.argv[1:] if argv is None else argv)
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
    except KeyboardInterrupt:
        # Ctrl-C: said in a word, never as a traceback, and the status a shell gives an interrupt
        # (``cad_server._internal.cli_errors``: ``canceled``, 130). A build it waited for goes on in the
        # engine; the same command waits for it again.
        from cad_server._internal.cli_errors import Failure, wants_json, write

        return write(Failure("canceled", "canceled"), prog="cad", as_json=wants_json(argv))


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


def _main(argv: list[str]) -> int:
    _harden_std_stream_errors()

    # A pinned command, `cad +<version>[@<channel>] ...`: the pin names this version, or nothing runs; its
    # channel is this command's (`cad_server._internal.pins`, imported only for one: a command imports no more
    # than it uses).
    pin = None
    if argv[:1] and argv[0].startswith("+"):
        from cad_server._internal import pins
        from cad_server._internal.cli_errors import Failure, wants_json, write

        try:
            pin, argv = pins.take(argv)
            pins.check(pin)
        except Failure as failure:
            return write(failure, prog="cad", as_json=wants_json(argv))

    if not argv or argv[0] in {"-h", "--help"}:
        sys.stdout.write(_usage())
        return 0
    if argv[0] == "help":  # `cad help step export` is `cad step export --help`, at any depth
        return _main([*argv[1:], "--help"]) if argv[1:] else _main([])

    if argv[0] in {"-V", "--version"}:
        # The version this is: the installed version it belongs to, the name a pin names it by; else the
        # installation's own version, as doctor's header says it: a development install's name
        # (0.8.0-dev.<stamp>), so two installations are told apart; else the package's.
        from cad_server import __version__
        from cad_server._internal import pins

        sys.stdout.write(f"cad {pins.own() or __version__}\n")
        return 0

    command, rest = argv[0], argv[1:]
    if " ".join(argv[:2]) in _COMMANDS:  # a two-word command (``update auto``) before its first word
        command, rest = " ".join(argv[:2]), argv[2:]
    if command in TYPE_COMMANDS:
        entry: tuple[str, str] | None = (TYPE_COMMANDS[command], "")
    elif command in INTEGRATION_COMMANDS:
        entry = (INTEGRATION_COMMANDS[command], "")
    else:
        entry = _COMMANDS.get(command)
    if entry is None:
        return _unknown(command, rest)

    # Help does no work: it moves nothing, writes nothing and says nothing but the help. Nor does a report
    # asked for read-only (`cad doctor --check`).
    from cad_server._internal.cli_errors import options

    helping = _asks_help(command, rest) or (command in _REGISTERS and "--check" in options(rest))
    # The pin's channel made to run this version: equal, nothing; newer, or its first use, moved to it; older, the
    # chat's copy of the skill is stale and nothing runs (`pins.apply`). Help reads no pointer.
    if pin is not None and not helping:
        from cad_server._internal import pins
        from cad_server._internal.cli_errors import Failure, wants_json, write

        try:
            pins.apply(pin)
        except Failure as failure:
            return write(failure, prog="cad", as_json=wants_json(rest))
    # No pin, run by a version that has never started where the default channel has no pointer (the newest version
    # present, which the cad command runs where none has started): the default channel's first use made first, so
    # nothing is written before the version's data is imported (`pins.first_use`). `setup` moves the channel itself,
    # and `uninstall` takes things out.
    elif pin is None and not helping and command not in _MOVES_ITSELF and _maybe_a_version():
        from cad.engine.places import versioned

        if versioned() is not None:
            from cad_server._internal import pins
            from cad_server._internal.cli_errors import Failure, wants_json, write

            try:
                pins.first_use()
            except Failure as failure:
                return write(failure, prog="cad", as_json=wants_json(rest))
    # `doctor` registers this installation, as `setup` does: on a device an earlier release set up, what
    # this release keeps of its state folder moves into its own first, before the notice below writes there.
    if command in _REGISTERS and not helping:
        _adopt()
    # No command says a newer text-to-cad is out: it cannot tell which plugin, if any, it came
    # with, so the CAD app and the CAD Viewer say it (`cad_server/updates.py`). What a command does say,
    # once and before its work, is what those two send by default (`cad_server/analytics.py`) -- to a
    # person: an answer in JSON is a program's, so the notice waits for a later run a person reads, and
    # nothing is sent by default until it is said.
    from cad_server._internal.cli_errors import wants_json

    if command not in _UNTOLD and not helping and not wants_json(rest):
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
        if command == "run" or not wants_json(rest):  # `run`'s words are its program's: never its own --json
            raise  # its traceback the person's
        return _crashed(command, rest, error)


def _unknown(word: str, rest: list[str]) -> int:
    """A command that is none of the table's: the command line's failure (``usage``, exit 2), naming it,
    the one command it is closest to, if any, and where the commands are listed -- never the whole list."""
    from cad_server._internal.cli_errors import Failure, wants_json, write
    from cad_server._internal.cli_parser import suggest

    close = suggest(word, [*(name.split()[0] for name in _COMMANDS), *TYPE_COMMANDS, *INTEGRATION_COMMANDS])
    words = (f"unknown command {word!r}" + (f" (did you mean {close!r}?)" if close else "")
             + "; 'cad --help' lists the commands")
    return write(Failure(words, "usage"), prog="cad", as_json=wants_json(rest))


def _crashed(command: str, rest: list[str], error: Exception) -> int:
    """A crash past the command's own report, under ``--json``: its one JSON document (``internal_error``,
    exit 1) and no traceback, but with ``--verbose``, on stderr."""
    from cad_server._internal.cli_errors import Failure, wants_verbose, write

    if wants_verbose(rest):
        import traceback

        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    return write(Failure(f"{type(error).__name__}: {error}", "internal_error"), prog=f"cad {command}", as_json=True)


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
# as the `cad` command's `run` is; `plugin`, which a switch runs with no one to read it; and `requirement`,
# whose output a program reads.
def _maybe_a_version() -> bool:
    """Whether this process may be an installed version, told without importing the engine (a command imports no
    more than it uses): told its name (a development version, ``CAD_INSTALLATION_VERSION``), or its environment is a
    version's server, ``versions/<version>/code/server``. ``places.versioned`` then says."""
    import os

    if os.environ.get("CAD_INSTALLATION_VERSION"):
        return True
    parts = os.path.normcase(sys.prefix).split(os.sep)
    return len(parts) >= 4 and parts[-1] == "server" and parts[-2] == "code" and parts[-4] == "versions"


# Commands that never make the default channel's first use before they run (``pins.first_use``): setup moves it
# itself (an updater's first run of it stops once its release is present), uninstall takes things out.
_MOVES_ITSELF = frozenset({"setup", "uninstall"})
_UNTOLD = frozenset({"server", "telemetry", "setup", "update", "uninstall", "run", "plugin", "requirement"})


# The told commands that register this installation (``cad_server._internal.installations.setup``).
_REGISTERS = frozenset({"doctor"})


def _asks_help(command: str, rest: list[str]) -> bool:
    """Whether a command line asks for its help -- ``-h`` or ``--help`` among its options, or a type's ``help``
    -- which its parser prints and exits on; for ``run``, only its own first word, since what follows is the
    program's."""
    from cad_server._internal.cli_errors import options

    if command == "run":
        return rest[:1] in (["-h"], ["--help"])
    if (command in TYPE_COMMANDS or command in INTEGRATION_COMMANDS) and rest[:1] == ["help"]:
        return True
    return bool({"-h", "--help"} & set(options(rest)))


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
