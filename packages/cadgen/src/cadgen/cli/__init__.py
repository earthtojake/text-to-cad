"""The ``cadgen`` console script — a subcommand dispatcher over the distribution's CLIs.

Every subcommand is also reachable as ``python -m cadgen.<module>``; this is the friendly
front door, not a second implementation. A subcommand's parser lives in its own module and
owns its arguments, so the console and module entry points cannot drift.

Commands in the ``<format> <verb>`` grammar (design/format-doors.md) go one step further:
their module names only the public verb function, and the parser is DERIVED from that
function's signature (``cadgen._internal.cli_from_function``). A flag and a parameter
cannot drift, because there is only one of them.

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
# argv[0:2] before argv[0], so the two-word form wins where it exists and one-word
# commands like `daemon` still work.
#
# Generation has NO CLI (design/library-first-generation.md): a model script runs
# itself — `python <model>.py` through the @step/@dxf decorators.
_COMMANDS: dict[str, tuple[str, str]] = {
    # STEP. `build` writes a NEW document (IN OUT); `compile` only makes an
    # existing document's tree current and is INTERNAL — every door
    # and the viewer compile on demand, so no skill documentation names it.
    "step build": (
        "cadgen.cli.step_build",
        "re-emit a STEP as a new one; can add kinematics, materials, animation",
    ),
    "step compile": ("cadgen.cli.step_compile", "make a STEP's tree current"),
    "step snapshot": ("cadgen.cli.step_snapshot", "render a STEP model to an image"),
    # Mesh formats — one door each: `build` tessellates a STEP DOCUMENT into this
    # format (the sibling default, or OUT) and reads no model declaration;
    # `snapshot` renders a mesh file. One format, one door.
    "stl build": ("cadgen.cli.stl_build", "write an STL mesh of a STEP document"),
    "stl snapshot": ("cadgen.cli.stl_snapshot", "render an STL mesh to an image"),
    "3mf build": ("cadgen.cli.threemf_build", "write a 3MF mesh of a STEP document"),
    "3mf snapshot": ("cadgen.cli.threemf_snapshot", "render a 3MF mesh to an image"),
    "glb build": ("cadgen.cli.glb_build", "write a GLB mesh of a STEP document"),
    "glb snapshot": ("cadgen.cli.glb_snapshot", "render a GLB mesh to an image"),
    # DXF. A drawing has no derived state a door must materialize: the file is
    # the product, made by running its script (python <drawing>.py), and
    # `dxf snapshot` meshes it on demand.
    "dxf snapshot": ("cadgen.cli.dxf_snapshot", "render a DXF to an image"),
    # Robot descriptions
    "urdf validate": ("cadgen.cli.urdf_validate", "validate a URDF robot description"),
    "urdf snapshot": ("cadgen.cli.urdf_snapshot", "render a URDF to an image"),
    "sdf validate": ("cadgen.cli.sdf_validate", "validate an SDF world or model"),
    "sdf snapshot": ("cadgen.cli.sdf_snapshot", "render an SDF to an image"),
    "srdf validate": ("cadgen.cli.srdf_validate", "validate an SRDF against its URDF"),
    # Finite element analysis. `faces` lists a part's faces with the selectors a
    # study names; `solve` runs one linear static study and writes the result
    # GLB (a von Mises colour map on the deformed shape) with its JSON sidecar.
    "fea faces": ("cadgen.cli.fea_faces", "list a part's faces with their #o1.fN selectors"),
    "fea solve": ("cadgen.cli.fea_solve", "run a linear static stress study on a STEP part"),
    # Generic / services
    "doctor": ("cadgen.cli.doctor", "print installed cadgen and verify a skill's pin"),
    # The store. `store why <model>` is the debugging surface STORE.md describes.
    "store": ("cadgen.cli.store", "the store: info, why <model> (gate verdict), forget <target>, gc"),
    "snapshot": ("cadgen.cli.snapshot", "render any supported input to an image"),
    "daemon": ("cadgen.daemon", "run the warm build daemon"),
    # The two-word entry is required, not cosmetic: dispatch matches argv[0:2] first, so
    # without it `cadgen daemon status` falls through to one-word `daemon` and the
    # supervisor treats "status" as a stray argument.
    "daemon status": ("cadgen.cli.daemon_status", "show the warm daemon's workers"),
    # The CAD Viewer. One-word `viewer` serves the cwd (what the cad-viewer skill
    # teaches); the two-word entries are the instance manager, split into their own
    # modules for the same dispatch reason `daemon status` is.
    "viewer": ("cadgen.cli.viewer", "serve the current directory in the CAD Viewer"),
    "viewer list": ("cadgen.cli.viewer_list", "show running CAD Viewers and what each serves"),
    "viewer stop": ("cadgen.cli.viewer_stop", "terminate a running CAD Viewer"),
}

# `cadgen==1.2.3` / `cadgen[snapshot]==1.2.3`, as written by
# scripts/release/pin-cadgen-requirements.sh. Only the `==` form is a pin; a bare
# `cadgen` line has nothing to enforce.
_PIN_RE = re.compile(r"^cadgen(?:\[[a-z0-9_,.-]+\])?\s*==\s*(?P<pin>[^\s;#]+)")


def read_requirements_pin(requirements_path) -> str | None:
    """The exact ``cadgen==<version>`` a requirements.txt pins, or ``None``.

    ``None`` covers the non-cases uniformly: file absent/unreadable, or cadgen named
    without a pin. The caller decides what a mismatch means (``cadgen doctor`` reports
    it and exits 3). A source checkout's editable install
    reports the repository's VERSION, which is what the checked-in pins name, so the
    pin matches there too. String comparison rather than
    PEP 440 on purpose: pins are written mechanically as exact ``==`` by
    scripts/release/pin-cadgen-requirements.sh.
    """
    try:
        with open(requirements_path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    return next(
        (match.group("pin") for match in map(_PIN_RE.match, (line.strip() for line in lines)) if match),
        None,
    )


# Commands the warm daemon can serve, mapped to its tool names. The daemon exists to
# avoid paying the multi-second OCP/build123d import per invocation, so the handoff has to
# happen BEFORE the command's module is imported -- which is why it lives here in dispatch
# rather than inside each command.
#
# Snapshot orchestration stays in the caller. Its document compilation and
# missing surfaces already use the build pool; rendering needs no kernel.
#
# ONE table: a tool's name is its command with the space dashed, and its module is
# the command's own (`_COMMANDS`). The daemon derives what it may import from here
# (`daemon_tool_modules`), so a door cannot be warm on one side and unknown on the other.
_WARM_COMMANDS = ("step build", "step compile", "stl build", "3mf build", "glb build")
_DAEMON_TOOLS = {command: command.replace(" ", "-") for command in _WARM_COMMANDS}


def daemon_tool_modules() -> dict[str, str]:
    """``{daemon tool name: parser module}`` for every warm-served door."""
    return {tool: _COMMANDS[command][0] for command, tool in _DAEMON_TOOLS.items()}


def _run_via_daemon(tool: str, rest: list[str], prog: str) -> int | None:
    """Exit code when the daemon handled it, None to run in this process.

    CADGEN_DAEMON_CHILD is set in the process the daemon serves from, so this cannot
    recurse. A daemon that is not installed or not running just falls through.
    """
    # Warm by default; CADGEN_DAEMON=0 opts out. There are two gates on this path -- this
    # one and the client's -- and only changing the client's left the default a no-op,
    # which a live check caught rather than any test.
    if os.environ.get("CADGEN_DAEMON") == "0" or os.environ.get("CADGEN_DAEMON_CHILD"):
        return None
    try:
        from cadgen.daemon.client import run_via_daemon
    except ModuleNotFoundError:
        return None
    return run_via_daemon(tool, rest, os.getcwd(), prog=prog)


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
    """The two-word commands of one format noun (``step`` -> ``step build``, ...)."""
    return [name for name in _COMMANDS if name.split(" ")[0] == noun and " " in name]


def _format_usage(noun: str) -> str:
    return (
        f"usage: cadgen {noun} <verb> [args...]\n\n{noun} commands:\n"
        + _command_lines(_format_verbs(noun))
        + f"\nRun 'cadgen {noun} <verb> --help' for a command's own options.\n"
    )


# Law 8: every retired surface fails loudly with a teaching error naming its
# replacement -- never an alias, never a shim. Matched on the leading words of argv;
# `step inspect` keeps its own module (it is also reachable as `python -m`).
_RETIRED: dict[tuple[str, ...], str] = {
    ("gen",): (
        "cadgen gen has been removed: generation has no CLI. A model script is a program "
        "-- run it: python <model>.py (it gates, builds, and writes the STEP/DXF, the "
        "sidecar and every declared mesh). Per-run flags ride the script's argv: "
        "--force, --json, --verbose, --mesh-tolerance, --mesh-angular-tolerance."
    ),
    ("step", "export"): (
        "cadgen step export has been removed: each mesh format is its own door. Use "
        "cadgen stl build IN.step [OUT.stl], cadgen 3mf build IN.step [OUT.3mf] or "
        "cadgen glb build IN.step [OUT.glb]; to write a new STEP document use "
        "cadgen step build IN.step OUT.step. A model's maintained meshes are declared "
        "with @stl/@threemf/@glb and written by python <model>.py."
    ),
    ("srdf", "snapshot"): (
        "cadgen srdf snapshot does not exist: an SRDF's geometry comes from the URDF "
        "beside it, so it has no snapshot door of its own. Use cadgen snapshot "
        "<file>.srdf [OUT.png], which routes it by suffix."
    ),
}


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
    us, so a library import must never touch them, and a daemon worker -- whose
    stdout is the pool's frame channel, pinned by the protocol at both ends --
    is not a CLI boundary.
    """
    if os.environ.get("CADGEN_DAEMON_CHILD"):
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # a caller replaced it with a plain object
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (OSError, ValueError):  # detached or already closed
            pass


def main(argv: list[str] | None = None) -> int:
    _harden_std_stream_errors()
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in {"-h", "--help", "help"}:
        sys.stdout.write(_usage())
        return 0

    if argv[0] in {"-V", "--version"}:
        from cadgen import __version__

        sys.stdout.write(f"cadgen {__version__}\n")
        return 0

    if argv[:2] == ["step", "inspect"]:
        from cadgen.cli.step_inspect.cli import main as retired_inspect

        return retired_inspect(argv[2:])
    for words, message in _RETIRED.items():
        if tuple(argv[: len(words)]) == words:
            sys.stderr.write(message + "\n")
            return 2

    # Longest match first, so `step build` beats a hypothetical `step`.
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

    # Before the command's module is imported: the daemon exists to avoid paying the
    # multi-second OCP/build123d import, so the handoff cannot wait until afterwards.
    daemon_tool = _DAEMON_TOOLS.get(command)
    if daemon_tool is not None:
        exit_code = _run_via_daemon(daemon_tool, rest, f"cadgen {command}")
        if exit_code is not None:
            return exit_code

    module_name, _ = entry
    module = importlib.import_module(module_name)

    # Tell the parser which front door it was reached through, so
    # `cadgen step build --help` says "cadgen step build".
    # Not every command has a parser to name (the daemon owns its own), hence
    # the signature check rather than a blanket keyword.
    import inspect  # only the dispatcher needs it; `--help` and the daemon handoff do not.

    if "prog" in inspect.signature(module.main).parameters:
        return int(module.main(rest, prog=f"cadgen {command}") or 0)
    return int(module.main(rest) or 0)
