"""``cad doctor``: one read-only report of this cad -- its release, its Python and where it is installed, its data
folder, its cache folder and how much ``cad cache prune`` would free there, whether the CAD kernel environment is made
(``cad_server._internal.base``) and loads -- where it is not, the environment ``cad run`` made for a program that a
build ran in, if one was (``extras.last_with_kernel``) --, where each integration's operations run, whether the server runs and
its release, and cad's own update (``cad_server._internal.auto_update``: the switches, whether this cad is a global
install and by which installer, the newest release of this cad's major the version feed as last read names and,
where it names a release of a higher major, the one line that says how to get it (``auto_update.MAJOR_LINE``), whether
that installer is found, and the last attempt) and the install command's
record (``cad_server._internal.plugin_catch_up``: the release it is up to date for, and the last run the server
began for a newer cad, and how it went); on Windows, uv's folder in
an app's private copy of AppData, a copy of cad or uv's leftovers, to delete (``private_folders``). It repairs,
registers, starts, writes and deletes nothing: ``--check`` prints the same report.

The kernel is loaded in a fresh interpreter of its environment (``-P -B``: never this one, never a module of the
working folder's, no bytecode written), so a refused load is named for what it is: on Windows 11, Smart App Control
blocking the unsigned ``.pyd``, which the bare ``ImportError`` never says (``cad_server._internal.kernel_load_hint``).
A kernel environment not made is reported, not failed: it is made on first need, and a no-deps install of the wheel
(what the release workflow smoke-tests) is a correct install.

``--json`` is the report as one document on stdout, ``{"ok", "version", "checks": [{"name", "status", "detail"}]}``,
each check's status ``ok``, ``info``, ``warning`` or ``failed``. Exit 0; 1 when the kernel is installed and does not
load, the one ``failed`` check; 2 for the command line.

stdlib-only on purpose: this must work when the heavy dependency set is broken.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Each check's status, as the report's lines and its JSON say them: right, said for what it is, worth a look, and
# failed (the exit status 1).
OK, INFO, WARNING, FAILED = "ok", "info", "warning", "failed"
KERNEL_OK, KERNEL_MISSING, KERNEL_FAILED = "ok", "missing", "failed"
# How long the server may take to say its status: a server that never answers is reported, never waited on.
STATUS_SECONDS = 10.0
# Windows: uv's folder in an app's private copy of AppData, under %LOCALAPPDATA%. A packaged app keeps a folder that
# something inside it makes under AppData in a private copy only it sees: a cad installed from inside one works in
# that app alone, and a failed try leaves a folder where every new Python uv installs there fails. cad names such a
# folder, with the reason, and never deletes it. The lines say to delete it in File Explorer: a delete of that path
# from inside the app reports the folder gone and leaves every file (measured with Remove-Item), and one from outside
# the app removes it (measured).
WINDOWS = os.name == "nt"
PRIVATE = ("Packages/*/LocalCache/Roaming/uv",)
COPY_LINE = ("another copy of cad is in an app's private folder: {path}. That app keeps using it instead of this one. "
             "Delete that folder in File Explorer so every app uses this cad; deleting it from inside that app does "
             "not work.")
LEFTOVER_LINE = ("uv left files in an app's private folder: {path}. Inside that app a new Python lands there and fails "
                 "to install. Delete that folder in File Explorer; deleting it from inside that app does not work.")


def build_parser(prog: str = "cad doctor"):
    """The parser of ``cad doctor``: its options, exactly as the command parses them."""
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description="Report this cad: its release, its data and cache folders and what "
                                                   "`cad cache prune` would free, the CAD kernel environment and the "
                                                   "integrations', and the server. It changes nothing. Exit 1 when "
                                                   "the CAD kernel is installed and does not load.")
    parser.add_argument("--check", action="store_true", help="the same report")
    parser.add_argument("--json", action="store_true", help="the report as one JSON document: each check's name, "
                                                            "status (ok, info, warning, failed) and detail")
    return parser


def main(argv: list[str] | None = None, prog: str = "cad doctor") -> int:
    args = build_parser(prog).parse_args(argv)

    from cad.engine.previous import version

    checks = _report()
    status = 1 if any(found["status"] == FAILED for found in checks) else 0
    if args.json:
        import json

        sys.stdout.write(json.dumps({"ok": status == 0, "version": version(), "checks": checks},
                                    separators=(",", ":")) + "\n")
        return status
    # The whole report on stdout, a failed kernel among it: `cad doctor > report.txt` keeps all of it.
    sys.stdout.write(f"cad {version()}\n")
    for found in checks:
        sys.stdout.write(f"  {found['name']:<8} {found['detail']}\n")
        for hint in found.get("more") or ():
            sys.stdout.write(f"           {hint}\n")
    return status


def _check(name: str, status: str, detail: str, more: list[str] | None = None) -> dict:
    """One line of the report: what it checks, its status and its words, and the lines under it (a refused kernel's
    hints)."""
    return {"name": name, "status": status, "detail": detail, **({"more": more} if more else {})}


def _report() -> list[dict]:
    """Each check, in order. One that cannot be read is said (``unknown``), never a reason the report fails."""
    import cad_server
    from cad.engine.places import state_dir

    def read(name: str, how) -> dict:
        try:
            return _check(name, *how())
        except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
            return _check(name, WARNING, f"unknown ({type(error).__name__}: {error})")

    return [_check("python", INFO, f"{sys.version.split()[0]} ({sys.executable})"),
            _check("install", INFO, str(Path(cad_server.__file__).resolve().parent)),
            *(_check("private", WARNING, line) for line in private_folders()),
            _check("data", INFO, str(state_dir())), read("cache", _cache), _kernel(),
            *(_check(line.split(" ", 1)[0], status, line.split(" ", 1)[1]) for status, line in _integrations()),
            read("server", _server), read("update", _update), _newest(), _installer(), read("attempt", _attempt),
            read("plugin", _catch_up)]


def private_folders() -> list[str]:
    """Windows: a line for each uv folder in an app's private copy of AppData (``PRIVATE``), with what it holds: a copy
    of cad (``COPY_LINE``) or uv's leftovers (``LEFTOVER_LINE``). Not the one this cad runs from (its ``tools/cad`` the
    same folder as ``sys.prefix``): deleting it would remove this cad. One glob; never raises, and nothing elsewhere."""
    if not WINDOWS:
        return []
    try:
        root = os.environ.get("LOCALAPPDATA")
        lines = []
        for folder in (path for pattern in PRIVATE for path in Path(root).glob(pattern)) if root else ():
            cad = folder / "tools" / "cad"
            try:
                if os.path.samefile(cad, sys.prefix):
                    continue
            except OSError:
                pass
            lines.append((COPY_LINE if cad.is_dir() else LEFTOVER_LINE).format(path=folder))
        return lines
    except Exception:  # noqa: BLE001 - a hint, never a reason for a command to fail
        return []


def _auto():
    from cad_server._internal import auto_update

    return auto_update


def _update() -> tuple[str, str]:
    """cad's own update: whether it updates itself (``cad update auto``), a global install alone (and by which
    installer), and whether the server runs the install command once where cad is newer than the release it is up to
    date for (``cad plugin update auto``)."""
    auto = _auto()
    found, word = auto.global_install(), {True: "on", False: "off"}
    plugin = f"plugin update auto {word[auto.plugin_switch()]}"
    if found is None:
        return INFO, f"this cad is not a global install, so it never updates itself; {plugin}"
    kept = auto.switches()
    earlier = " (turned off in an earlier release)" if kept.get("earlier") else ""
    return INFO, (f"update auto {word[kept['on']]}{earlier}, {plugin}; a global install by {found.installer.name} "
                  f"({found.prefix})")


def _newest() -> dict:
    """What the version feed as last read says of releases (read, never fetched): the newest release of this cad's
    major it names, and, under it, the one line that says a release of a higher major is out and how to get it."""
    try:
        import cad_server
        from cad_server import updates

        auto = _auto()
        version = cad_server.__version__
        known = updates.feed(fetch=False)
        numbers = auto.release(version)
        if known is None:
            return _check("newest", INFO, "the version feed has not been read on this computer yet")
        if numbers is None:
            return _check("newest", INFO, f"cad {known['latest']} is the newest release the version feed names")
        named = updates.newest_of_major(numbers[0], known)
        said = (f"cad {named} is the newest {numbers[0]}.x release the version feed names" if named else
                f"the version feed names no {numbers[0]}.x release; its newest is cad {known['latest']}")
        higher = auto.higher(known, version)
        return _check("newest", INFO, said, [auto.MAJOR_LINE.format(release=higher)] if higher else None)
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return _check("newest", WARNING, f"unknown ({type(error).__name__}: {error})")


def _installer() -> dict:
    """The installer cad's update runs, as the update finds it: the global install's (uv, pipx), and uv where this cad
    is none; the line named after it."""
    try:
        auto = _auto()
        found = auto.global_install()
        if found is None:
            return _check("uv", INFO, auto.find_uv() or "not found")
        return _check(found.installer.name, INFO, " ".join(found.program) if found.program else "not found")
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return _check("uv", WARNING, f"unknown ({type(error).__name__}: {error})")


def _attempt() -> tuple[str, str]:
    """The last update attempt: from which release to which, when, and its outcome (a failure's last line)."""
    import time

    last = _auto().last()
    if last is None:
        return INFO, "none"
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last["at"]))
    failed = last.get("outcome") == "failed" and last.get("detail")
    restored = {True: f"; {last.get('from')} put back", False: f"; {last.get('from')} not put back: cad is missing"}
    return INFO, (f"{last.get('from')} to {last['release']} on {when}: {last.get('outcome')}"
                  + (f" ({last['detail']})" if failed else "") + restored.get(last.get("restored"), ""))


def _catch_up() -> tuple[str, str]:
    """The install command's record: the release of cad it is up to date for -- the one it last ended with exit status
    0 for, or the one that turned ``cad plugin update auto`` on --, and the last run the server began for a newer cad --
    its release, when, how it went and its exit status, the try of how many."""
    import time

    from cad_server._internal import plugin_catch_up

    found = plugin_catch_up.read()
    named = found.get("for")
    said = (f"the install command is up to date for cad {named}" if isinstance(named, str)
            else "no record of the install command being up to date on this computer")
    if not isinstance(found.get("release"), str) or not isinstance(found.get("at"), (int, float)):
        return INFO, said
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(found["at"]))
    code = found.get("code")
    ended = found.get("outcome")
    how = f"{ended} (exit {code})" if ended == plugin_catch_up.FAILED and code is not None else str(ended)
    return INFO, (f"{said}; the last run, for cad {found['release']} on {when}: {how}, try {found.get('tries')} of "
                  f"{plugin_catch_up.TRIES}")


def _cache() -> tuple[str, str]:
    """The cache folder, and what ``cad cache prune`` would remove there and free."""
    from cad_server.cli import cache

    going, _kept = cache.prunable()
    if not going:
        return INFO, f"{cache.folder()}: nothing for `cad cache prune` to remove"
    return INFO, (f"{cache.folder()}: `cad cache prune` would remove {len(going)} "
                  f"{'folder' if len(going) == 1 else 'folders'} of other releases and free "
                  f"{cache.size(cache.freed(path for path, _what in going))}")


def _server() -> tuple[str, str]:
    """Whether the server runs, asked and never started: its process, its release and its workers."""
    from cad.engine import client, places
    from cad.engine.previous import version
    from cad_server.engine.cli import workers_text

    where = places.address()
    answer = client.request({"op": "status"}, start=False, timeout=STATUS_SECONDS)
    if not isinstance(answer, dict):
        return INFO, f"not running ({where}): run `{client.START}`"
    release = answer.get("version")
    said = f"running, pid {answer.get('pid')}, cad {release or 'of 0.11.11 or earlier'}, {workers_text(answer)} ({where})"
    if release != version():
        return WARNING, f"{said}: not this release; `{client.START}` runs {version()}'s"
    return OK, said


def _kernel() -> dict:
    """The CAD kernel environment, never made here, and its kernel loaded where it is made: ``FAILED`` -- the one
    failure of the report, exit 1 -- when it is installed and does not load."""
    from cad_server._internal import base
    from cad_server._internal.kernel_load_hint import kernel_load_hint, system_library_hint

    try:
        found = base.ensure(make=False)
    except base.Refused as refused:
        return _check("kernel", INFO, f"not made — {refused}")
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return _check("kernel", WARNING, f"unknown ({type(error).__name__}: {error})")
    if found is None:  # made on first need; a wheel installed --no-deps (the release smoke test) is a correct install
        from cad_server._internal import extras

        ran = extras.last_with_kernel(base.Installation.here())
        if ran is None:
            return _check("kernel", INFO, f"not made — {base.where()}, made on first need: the first build or view "
                                          "that needs it")
        # The builds ran where `cad run` made an environment for their program (more than the kernel, or a setting of
        # uv's from its caller): that one's kernel, said for what it is, and the base said not made yet.
        found, where = ran, (f"the environment `cad run` made for a program, {ran.prefix}; the CAD kernel environment, "
                             f"{base.where()}, made on first need")
    else:
        where = "this installation carries it" if found.own else f"the CAD kernel environment, {found.prefix}"
    state, detail = _probe_kernel(found.python)
    if state == KERNEL_OK:
        return _check("kernel", OK, f"OK — OCP at {detail} ({where})")
    if state == KERNEL_MISSING:
        return _check("kernel", WARNING, f"not installed — OCP is absent from {found.python} ({where})")
    return _check("kernel", FAILED, f"FAILED — {detail}", list(kernel_load_hint(detail) or system_library_hint(detail)
                                                                 or ()))


def _probe_kernel(python: str | None = None) -> tuple[str, str]:
    """Import OCP in a fresh interpreter (``python``'s, else this one's), writing no bytecode: ``(state, detail)``,
    ``KERNEL_OK`` with the module's path, ``KERNEL_MISSING`` (``ModuleNotFoundError``) or ``KERNEL_FAILED`` with the
    last line of its stderr. A subprocess, so a kernel that crashes the interpreter cannot take the report down."""
    import subprocess

    try:
        # Both ends utf-8: on Windows the child's stdio would otherwise be the ANSI code page.
        result = subprocess.run([python or sys.executable, "-P", "-B", "-c", "import OCP; print(OCP.__file__)"],
                                capture_output=True, text=True, encoding="utf-8", errors="backslashreplace",
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as error:
        return KERNEL_FAILED, f"{type(error).__name__}: {error}"
    if result.returncode == 0:
        lines = [text for text in result.stdout.splitlines() if text.strip()]
        return KERNEL_OK, lines[-1].strip() if lines else ""
    lines = [text for text in result.stderr.splitlines() if text.strip()]
    detail = lines[-1].strip() if lines else f"exit status {result.returncode}"
    return (KERNEL_MISSING if detail.startswith("ModuleNotFoundError:") else KERNEL_FAILED), detail


def _integrations() -> list[tuple[str, str]]:
    """Each integration that has an environment of its own (``cad[<integration>]``, made on first need:
    ``cad_server._internal.integration_env``) -- this installation's own where it carries it, else that
    environment, made or where it will be -- read, never made: what a manufacturing check (trimesh) or a KiCad
    command (kicad) runs in, or a ``cad run`` of a program that imports an integration with no command of its
    own and nothing else of cad's (blender's bpy); what first needs it is the registry's to say (``_need``). One
    whose tool has no build for this platform says so, and one whose Python is gone (a Python uv managed,
    uninstalled) that it is made again. The CAD kernel's is the kernel line's."""
    try:
        from cad.registry import INTEGRATIONS
        from cad_server._internal import base, extras, integration_env

        lines = []
        for name, integration in INTEGRATIONS.items():
            if name == "build123d" or not integration.extra:
                continue
            try:
                extras.supported((name,), base.Installation.here().arch)
            except base.Refused as refused:  # its tool has no build for this platform: said, nothing to make
                lines.append((INFO, f"{name} not made: {refused}"))
                continue
            state, folder, release = integration_env.found(name)
            if state == "carried":
                lines.append((OK, f"{name} this installation carries it (cad[{integration.extra}])"))
            elif state == "made":
                lines.append((OK, f"{name} cad[{integration.extra}] {release} in {folder}"))
            elif base.marked(Path(folder)) is not None:
                lines.append((INFO, f"{name} cad[{integration.extra}] {release} in {folder} has lost its "
                                    f"Python: made again on first need, {_need(name, integration)}"))
            else:
                lines.append((INFO, f"{name} cad[{integration.extra}] {release}, made on first need in "
                                    f"{folder}: {_need(name, integration)}"))
        return lines
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [(WARNING, f"extras unknown ({type(error).__name__}: {error})")]


def _need(name: str, integration) -> str:
    """What first needs an integration's environment, as the registry says: a command, for one a document
    type's operation runs in or that declares commands of its tool's (``kicad-cli``); else a ``cad run`` of a
    program that imports it."""
    from cad.registry import DOCUMENT_TYPES

    if integration.commands or any(operation.integration == name for entry in DOCUMENT_TYPES.values()
                                   for operation in entry.operations):
        return "the first command that needs it"
    imports = " or ".join(integration.modules) or name
    return f"the first `cad run` of a program that imports {imports} and no other integration"


if __name__ == "__main__":
    raise SystemExit(main())
