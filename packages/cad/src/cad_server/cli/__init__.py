"""The ``cad`` console script -- a subcommand dispatcher over the distribution's CLIs.

Three kinds of command. A document type's: ``cad <document_type> <operation> <file>``, one per type in
the registry (``cad.registry``), each its own module, ``cad_server.cli.<type>``
(``cad_server.cli.document_types``: ``cad xbf export``, ``cad stl snapshot``, ``cad urdf validate``). An
integration's, for its tool's own files, which are no document type, which cad checks or writes and never
shows: ``cad <integration> <operation> [<file>]`` (``cad_server.cli.integrations``: ``cad mujoco check``,
``cad orcaslicer presets``), only for the integrations the registry gives operations. And the commands that are no file's: the server's (``server``: ``start``,
``stop``, ``status``), the CAD app an agent app starts (``mcp``), the engine's verbs (``serve``, ``delete``), ``run``,
and the installation's (``requirement``, ``setup``, ``doctor``, ``cache``, ``viewer``, ``telemetry``, ``update``, whose
``update auto`` is cad's own switch, and ``plugin``). ``cad --help`` lists them all but ``_UNLISTED``'s.

A command that reaches the server holds it to its own release (``cad.engine.client.RELEASE``): one of another
release is refused in one line. The server's own commands are not held to it (``_ANY_RELEASE``).

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
    # The server, documents served, and documents deleted.
    "server": ("cad_server.cli.server", "the cad server: start, stop, status"),
    "serve": ("cad_server.cli.serve", "serve a document over HTTP and print its URL"),
    "status": ("cad_server.cli.status", "`cad server status`"),
    "stop": ("cad_server.cli.stop", "`cad server stop`"),
    "delete": ("cad_server.cli.delete", "delete documents: record, cached document, the engine's copy"),
    # The CAD app an agent app's plugin starts: the server started as `cad server start` starts it, then MCP on stdio.
    "mcp": ("cad_mcp.shim", "serve the CAD app to the agent app that starts it, over MCP on stdin and stdout"),
    # Generic / services
    "run": ("cad_server.cli.run", "run a script (or -m, -c) as uv run does, cad pinned at this device's release "
                                  "with the integrations its imports use"),
    # The installation: the requirement a Python of a program's own installs this device's cad by.
    "requirement": ("cad_server.cli.requirement", "print the exact cad requirement for a Python of a program's own"),
    "doctor": ("cad_server.cli.doctor", "report this cad, its folders, its kernel and the server; it changes nothing"),
    "cache": ("cad_server.cli.cache", "cad's cache: dir, prune (what this release cannot use), clean (all of it)"),
    # BRIDGE-ONLY, never listed: what the updaters of 0.10.0 to 0.11.11 run of the release they bring
    # (``cad_server.cli.setup``).
    "setup": ("cad_server.cli.setup", "the bridge from releases 0.10.0 to 0.11.11"),
    # A page of the running server's; the launcher exits.
    "viewer": ("cad_server.cli.viewer", "open a viewer page on the running cad server"),
    "telemetry": ("cad_server.cli.telemetry", "show or change the usage stats and crash reports CAD sends: status, on, off"),
    "update": ("cad_server.cli.update", "update cad now to the newest release of its major version (`--major`: of "
                                     "all); `update auto`: whether it does so itself"),
    "plugin": ("cad_server.cli.plugin", "the plugin: `update` it now; `update auto`: whether cad's updates do"),
}
# Run, never listed. Only for releases 0.10.0 to 0.11.11 -- their skill text (`cad status`, `cad stop`) and their
# updaters (`cad setup`) -- and gone with the bridge. And commands for programs, not people: `serve` (a document served
# over HTTP, its URL printed) and `requirement` (the cad requirement a Python of a program's own installs).
_UNLISTED = frozenset({"status", "stop", "setup", "serve", "requirement"})

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
    return "\n".join(f"  {name.ljust(width)}  {_COMMANDS[name][1]}" for name in sorted(set(names) - _UNLISTED)) + "\n"


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


def _standard_streams() -> None:
    """The command's two streams: on Windows, UTF-8 where they go to a pipe or a file; everywhere, an unencodable
    character written as an escape instead of killing the write.

    Windows gives a CLI process a legacy code page for a stream that is no console (cp1252, ...), while whatever reads
    a command's output there -- an agent, a log, Git Bash -- reads UTF-8: a profile folder with an accent arrived
    broken. So such a stream is UTF-8 (``cad._internal.streams.switches``); a console is left as it is, as is every
    stream on other systems, and every reader of this release's output in this repository decodes UTF-8 (a reader
    that decoded the code page is why an earlier switch was reverted).

    The error HANDLER changes everywhere: a stream's encoding may still lack a character (a POSIX locale of ASCII,
    a path's undecodable bytes), and under strict handling one it cannot represent raises UnicodeEncodeError from
    the MESSAGE rather than from the work. What cannot be emitted degrades to a backslash-u escape, which a reader
    can decode, rather than to a question mark that destroys it.

    CLI ENTRY POINTS ONLY: these are process globals owned by whoever embedded
    us, so a library import must never touch them.
    """
    from cad._internal.streams import switches

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # a caller replaced it with a plain object
            continue
        try:
            reconfigure(errors="backslashreplace", **({"encoding": "utf-8"} if switches(stream) else {}))
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
    _standard_streams()

    if not argv or argv[0] in {"-h", "--help"}:
        sys.stdout.write(_usage())
        return 0
    if argv[0] == "help":  # `cad help step export` is `cad step export --help`, at any depth
        return _main([*argv[1:], "--help"]) if argv[1:] else _main([])

    if argv[0] in {"-V", "--version"}:
        # The version this is, as doctor's header says it: a development build's name (0.8.0-dev.<stamp>), else
        # the release's (``places.installation``).
        from cad.engine.places import installation

        sys.stdout.write(f"cad {installation()}\n")
        return 0

    command, rest = argv[0], argv[1:]
    if command in TYPE_COMMANDS:
        entry: tuple[str, str] | None = (TYPE_COMMANDS[command], "")
    elif command in INTEGRATION_COMMANDS:
        entry = (INTEGRATION_COMMANDS[command], "")
    else:
        entry = _COMMANDS.get(command)
    if entry is None:
        return _unknown(command, rest)

    # Help does no work: it writes nothing and says nothing but the help. Nor does a report (`cad doctor`).
    helping = _asks_help(command, rest) or command in _READ_ONLY
    # What a command says, once and before its work, is what CAD sends by default (`cad_server/analytics.py`)
    # -- to a person: an answer in JSON is a program's, so the notice waits for a later run a person reads, and
    # nothing is sent by default until it is said.
    from cad_server._internal.cli_errors import wants_json

    if command not in _UNTOLD and not helping and not wants_json(rest):
        _tell()
    if command not in _ANY_RELEASE:
        from cad_server._internal.attach import when

        when("cad.engine.client", _hold_to_release)  # as the client is imported, if it is: a command imports no more
    try:
        code = _run(command, entry[0], rest)
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
    return code


def _hold_to_release(client) -> None:
    """This command's client holds the server it reaches to this release (``cad.engine.client.RELEASE``)."""
    from cad.engine.previous import version

    client.RELEASE = version()


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


# Commands that reach a server of any release (``cad.engine.client.RELEASE``): the server's own -- which start this
# release's in place of another's, stop whichever runs, and say which runs --, `mcp`, which decides it itself
# (``cad_mcp.shim.start_server``), those that only ask whether one runs, and which (`doctor`, `cache`), and
# `update auto` and `plugin`, whose switches are the person's, kept for every release, which any server that knows how
# keeps, and `update`, which any server that knows how carries out (one that does not is said), and whose next server
# is another.
_ANY_RELEASE = frozenset({"server", "status", "stop", "mcp", "doctor", "cache", "update", "plugin"})
# Commands that never carry the analytics notice: the engine's server and `mcp`, writing nowhere a person reads;
# `telemetry`, which says it its own way; `setup`, which an updater of 0.11.11 and earlier runs with no person to read
# it, and `plugin`, which cad's own update runs with none, its output in a log; `run`, which is only the python it runs,
# as the `cad` command's `run` is; and `requirement`, whose output a program reads.
_UNTOLD = frozenset({"server", "mcp", "telemetry", "setup", "plugin", "run", "requirement"})
# Commands that only report, and so write nothing a command's run writes (``_tell``).
_READ_ONLY = frozenset({"doctor"})


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
