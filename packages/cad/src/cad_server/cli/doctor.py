"""``cad doctor`` -- the health of this version of cad, and its repair: the ``cad`` command written, the
installation registered where none is, the engine started, and what this computer runs said.

It writes the proxy, ``~/.local/bin/cad`` (on Windows ``cad.exe``, with the Python it runs by), where it is missing
or of an older revision, and, on a computer where no installation is current, registers this one
(``<state>/installations/<version>.json``) and makes it current (``cad_server._internal.installations``: the records
clients of 0.11.10 and earlier, and processes with no version, read); on one where an installation is, it registers
nothing. It says what it found: each written, already right, or a folder it cannot write (a sandbox's), the records
of installations whose interpreter is gone, a file in the proxy's place that is not cad's, another command
shadowing it on PATH.

It reads every version installed (``_versions``): where each is, whether it is completely installed, whether its
server runs and on which port, when an agent last used it (``versions.last_used``), which is the newest, and when the
newest one's server removes an older one (``versions.clean``: unused for 2 days); and what is left of the layout of
0.11.10 and earlier and whether it can go yet (``legacy.unsafe``). And it says what earlier releases left behind that
nothing of cad uses (``cad_server._internal.leftovers``: engine records of an older format, the bytecode of
installations no longer registered, cache folders no record names, environments of models' packages unused for a
week, the launchers 0.8 published beside the ``cad`` command, cadgen 0.7's store and state files, 0.10.0's folders
on Windows), with their size and when they were last written: nothing removes them but the person. Everything else
it does acts on the one version it runs as (the pinned one, or the newest with no pin).

It says what the computer runs for clients of 0.11.10 and earlier, comparing nothing: the installation
``installations/current`` names, and the flat release folders of that layout on disk
(``cad_server._internal.releases``).

It says whether the CAD kernel environment, the base the engine's own kernel processes start from
(``cad_server._internal.base``: ``cad[build123d]`` at this release), is made -- it never makes it: a version
installed in its own folder made it as it was installed (``versions.make_present``), and an installation with no
version makes it on first need, by the first build or view that needs the kernel; an installation that carries the
kernel itself is its own -- and, where it is, proves the CAD kernel loads there. ``OCP`` is imported in a fresh
interpreter of that environment (never in this one, so the report itself stays stdlib-only and
fast to reach), and a refused load is named for what it is: on Windows 11 that is Smart App
Control blocking the unsigned ``.pyd``, which the bare ``ImportError`` never
says (``cad_server._internal.kernel_load_hint``). And it says where this version's engine server, where every build
runs, keeps its door, and whether it was running or was started (``cad.engine.client``). ``--no-server`` does all of
it but start the engine, saying whether one runs: a CI job's smoke check, which must leave no engine behind. It says
too where each integration's operations run (``trimesh``'s manufacturing check, ``kicad``'s commands): this
installation's own environment, or ``cad[<integration>]``'s, made on first need and never here
(``integration_env.found``).

``--check`` is the report alone, read-only: it registers nothing, writes nothing -- not the ``cad``
command, not the telemetry notice, not an install id, not the bytecode of the kernel it loads -- and starts
nothing, saying what ``cad doctor`` would write; what a bug report wants. ``--json`` is the report as one
document on stdout, ``{"ok", "version", "checks": [{"name", "status", "detail"}]}``, each check's status
``ok``, ``info``, ``warning`` or ``failed``. The whole report goes to stdout, a failed kernel among it.

Exit codes: 0 = done; 1 = the kernel is installed but cannot be loaded (the report says why when it
can tell), the one ``failed`` check; 2 = the command line. A kernel environment that is not made, or
cannot be made here (no uv, no network), is reported, not failed: it is made on first need, and a no-deps
install of the wheel (what the release workflow smoke-tests) is still a correct install.

stdlib-only on purpose: this must work when the heavy dependency set is broken.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Each check's status, as the report's lines and its JSON say them: right, said for what it is, worth a
# look (a write a sandbox refused, a command that is not cad's), and failed (the exit status 1).
OK, INFO, WARNING, FAILED = "ok", "info", "warning", "failed"


def _server(start: bool = True) -> tuple[str, str]:
    """The device's engine server (``cad_server.engine.daemon``): where its door is, and whether one is
    running, from which installation -- started when none is and ``start``, through the client's own
    start (the current installation's), which in a sandbox that cannot start one says so. ``(status,
    words)``, the status ``ok`` for one running, ``info`` for none, ``warning`` for one it could not ask."""
    try:
        from cad.engine import places
        from cad.engine.client import request

        where = places.address()
        answer = request({"op": "status"}, start=False)
        started = False
        if not isinstance(answer, dict) and start:
            try:
                answer = request({"op": "status"}, start=True)
            except ConnectionError as error:
                return WARNING, f"not running ({where}): {error}"
            started = True
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return WARNING, f"unknown ({type(error).__name__}: {error})"
    if not isinstance(answer, dict):
        return INFO, f"not running ({where}); a build starts it outside a sandbox; inside one, run `cad server` outside first"
    from cad_server.engine.cli import workers_text

    # The version the engine runs as, and its environment; the workers as `cad status` counts them:
    # the standby with them.
    version = answer.get("installation") or answer.get("version")
    prefix = answer.get("prefix")
    return OK, (f"{'started' if started else 'running'}, pid {answer.get('pid')}"
                + (f", cad-server {version}" if version else "")
                + (f" from {_home(prefix)}" if isinstance(prefix, str) else "") + f", {workers_text(answer)} ({where})")


def _current() -> list[str]:
    """What this computer runs for clients of 0.11.10 and earlier, comparing nothing: the installation
    ``installations/current`` names, and the flat release folders of that layout on disk, which go with that layout
    (``cad_server._internal.legacy``)."""
    from cad_server._internal import installations, releases

    lines = []
    try:
        record = installations.current()
        named = installations.current_version()
        if record is not None:
            lines.append(f"current  cad-server {record['version']} ({_home(record['prefix'])}): the server clients of "
                         "0.11.10 and earlier reach")
        elif named is not None:
            lines.append(f"current  cad-server {named}, whose installation is gone: a client of 0.11.10 or earlier "
                         "starts its own")
        found = releases.listing()
        if found:
            current = (record or {}).get("version") or named
            said = ", ".join(release["version"] + ("" if release["complete"] else " (incomplete)")
                             + (" (current)" if release["version"] == current else "")
                             for release in found)
            lines.append(f"releases {said} in {_home(str(releases.root()))}: of 0.11.10 or earlier, removed with that "
                         "layout")
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        lines.append(f"current  unknown ({type(error).__name__}: {error})")
    return lines


def _when(stamp: float | None) -> str:
    """A time as a person reads it in a report, ``2026-11-13 09:41``, or ``unknown``."""
    import time

    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp)) if stamp else "unknown"


def _versions() -> list[str]:
    """Every version installed on this computer, a line each (``versions/<version>``): where it is, whether it is
    completely installed, whether its server runs and on which port, when an agent last used it (or, never used, when
    it was installed: ``versions.last_used``), and, for each older than the newest, when the newest's server removes
    it (``versions.clean``). Then what is left of the layout of 0.11.10 and earlier, and whether it can go yet
    (``legacy.unsafe``). Read alone: nothing is started, stopped, made or written (``versions.serves`` asks a door,
    and takes no lock)."""
    import time

    from cad.engine import places
    from cad_server._internal import legacy, versions

    lines: list[str] = []
    try:
        newest = versions.newest()
        now = time.time()
        for name in versions.folders():
            present = places.version_record(name) is not None
            words = [f"cad {name} at {_home(str(places.version_dir(name)))}"
                     + ("" if present else ", not completely installed")]
            if versions.serves(name):
                port = versions.serving(name)
                words.append("its server runs" + (f", pages on port {port}" if port else ""))
            else:
                words.append("its server is not running")
            if present:
                last = versions.last_used(name)
                words.append(f"last used {_when(last)}")
                if name == newest:
                    words.append("the newest: a command with no pin runs it, and its server removes older versions "
                                 f"unused for {round(versions.UNUSED_SECONDS / 86400)} days")
                elif newest is not None and versions.older(name, newest):
                    left = last + versions.UNUSED_SECONDS - now
                    words.append(f"cad {newest}'s server removes it once it has gone unused for "
                                 f"{round(versions.UNUSED_SECONDS / 86400)} days"
                                 + (f" (in {max(1, round(left / 3600))} hours or more)" if left > 0
                                    else " (at its next cleanup)"))
            lines.append("version  " + "; ".join(words))
        if not versions.folders():
            lines.append("version  none installed")
        if legacy.removable():
            why = (legacy.unsafe(newest, read_only=True) if newest is not None
                   else "no version is installed to take it over")
            lines.append("legacy   the layout of 0.11.10 and earlier is here: "
                         + (f"kept, {why}" if why else "safe to remove: the newest version's server removes it at its "
                                                       "next cleanup"))
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        lines.append(f"version  unknown ({type(error).__name__}: {error})")
    return lines


def _command_path_hint(path: str) -> str:
    """How to reach the proxy when PATH does not resolve ``cad`` to it. The person's PATH is the one
    looked in (``installations.lasting``): ``uvx`` puts its ephemeral environment's ``bin`` first on PATH
    for the command it runs, so inside ``uvx ... cad doctor`` that environment's own ``cad`` script would
    otherwise read as shadowing the proxy."""
    from shutil import which

    from cad_server._internal.installations import lasting

    found = which("cad", path=lasting(os.environ.get("PATH", "")))
    if found is not None:
        if os.path.normcase(os.path.realpath(found)) == os.path.normcase(os.path.realpath(path)):
            return ""
        return f"; shadowed on PATH by `{os.path.abspath(found)}`; run `{path}` explicitly"
    folder = _home(os.path.dirname(path))
    return f"; run it as `{path}` until `{folder}` is on your PATH"


def _home(path: str) -> str:
    """``path`` with the home folder spelled ``~``, as a person types it."""
    import os

    home = os.path.expanduser("~")
    return "~" + path[len(home):] if home not in ("", "~") and (path == home or path.startswith(home + os.sep)) else path


def _sharing(check: bool = False) -> str | None:
    """``on`` or ``off`` for the usage stats CAD sends, and why, or ``None`` if it cannot tell; with ``check``
    read alone: no install id made, the state folder not tried (``analytics.status``'s ``keep``, ``probe``)."""
    try:
        from cad_server.cli.telemetry import describe

        if check:
            from cad_server.analytics import status

            return describe(status(probe=False, keep=False))
        return describe()
    except Exception:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return None


KERNEL_OK = "ok"
KERNEL_MISSING = "missing"
KERNEL_FAILED = "failed"


def _kernel_environment() -> tuple[str | None, str]:
    """The CAD kernel environment (``cad_server._internal.base``), never made here: ``(its Python, where it
    is)``, or ``(None, why there is none)``."""
    from cad_server._internal import base

    try:
        installation = base.Installation.here()
        found = base.ensure(installation, make=False)
        if found is None:
            return None, f"{base.where(installation)}, made on first need: the first build or view that needs it"
    except base.Refused as refused:
        return None, str(refused)
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return None, f"{type(error).__name__}: {error}"
    return found.python, ("this installation carries it" if found.own else f"the CAD kernel environment, {found.prefix}")


def _probe_kernel(python: str | None = None, *, read_only: bool = False) -> tuple[str, str]:
    """Import OCP in a fresh interpreter (``python``'s, else this one's): ``(state, detail)``.

    ``state`` is ``KERNEL_OK`` (``detail`` is the module's path),
    ``KERNEL_MISSING`` (no OCP installed: ``ModuleNotFoundError``), or
    ``KERNEL_FAILED`` (installed but would not load; ``detail`` is the last
    non-empty stderr line, the exception). A subprocess, so a kernel that
    crashes the interpreter or takes the ~2.5 s import cannot take the report
    down with it, and so this process never carries the kernel itself.
    ``read_only`` (``--check``): the import writes no bytecode (``-B``).
    """
    import os
    import subprocess

    try:
        # Both ends name utf-8: the child's stdio would otherwise be the ANSI code page
        # on Windows, which cannot carry every path or every localized loader error.
        # ``-P``, as every child cadgen starts: the kernel the installation imports, never a
        # module of that name in the folder the command was run from.
        result = subprocess.run(
            [python or sys.executable, "-P", *(["-B"] if read_only else []), "-c", "import OCP; print(OCP.__file__)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return KERNEL_FAILED, f"{type(error).__name__}: {error}"
    if result.returncode == 0:
        lines = [text for text in result.stdout.splitlines() if text.strip()]
        return KERNEL_OK, lines[-1].strip() if lines else ""
    lines = [text for text in result.stderr.splitlines() if text.strip()]
    detail = lines[-1].strip() if lines else f"exit status {result.returncode}"
    if detail.startswith("ModuleNotFoundError:"):
        return KERNEL_MISSING, detail
    return KERNEL_FAILED, detail


def _setup(check: bool = False) -> list[tuple[str, str]]:
    """The report lines of the setup, each with its status: on a device with no current installation, this
    installation registered and made current when it may (a source tree registers only when named); the
    proxy written; the records whose interpreter is gone, and why a write failed, which in a sandbox is the
    folder being out of reach. With ``check`` (``--check``) nothing is registered or written: what is there
    is said, and what ``cad doctor`` would write."""
    from cad_server._internal import installations as setup

    lines: list[tuple[str, str]] = []
    try:
        version = setup.own_version()
        current = setup.current()
        if check:
            proxy = (setup.proxy_path(), setup.proxy_status(), None)
            registered = ("current" if current is not None and not setup.mine(current)
                          else (*setup.registration(version), None) if version else None)
        elif current is not None and not setup.mine(current):
            registered, proxy = "current", setup.write_proxy()
        elif version:
            registered, proxy = setup.setup(version)
        else:
            registered, proxy = None, (setup.proxy_path(), setup.proxy_status(), None)
        if registered == "current":
            lines.append((OK, f"registry cad-server {current['version']} is the current installation: this one "
                              "registers nothing"))
        elif registered is None:
            lines.append((INFO, f"registry not registered: a source tree registers only as a version it is named "
                                f"({setup.NAME_ENV})"))
        else:
            path, status, error = registered
            if error:
                lines.append((WARNING, f"registry {path} cannot be written here ({error}): run this outside any sandbox"))
            elif check and status == setup.MISSING:
                lines.append((WARNING, f"registry {path} not registered: `cad doctor` registers it"))
            else:
                lines.append((OK, f"registry {path} " + ("registered" if status == setup.REGISTERED else "OK")))
        path, status, error = proxy
        said = {setup.OK: "OK", setup.NEWER: "OK (a later release's)",
                setup.FOREIGN: "is not cad's (left alone): remove it to run cad by it",
                setup.MISSING: "missing", setup.STALE: "stale"}[status]

        path_hint = _command_path_hint(path)
        if error:
            lines.append((WARNING, f"command  {path} {said}; cannot write it here ({error}): run this outside any "
                                   "sandbox"))
        elif status in (setup.MISSING, setup.STALE) and version and check:
            lines.append((WARNING, f"command  {path} {said}: `cad doctor` writes it"))
        elif status in (setup.MISSING, setup.STALE) and version:
            lines.append((OK, f"command  {path} written (was {said}){path_hint}"))
        elif status in (setup.OK, setup.NEWER):
            lines.append((WARNING if path_hint else OK, f"command  {path} {said}{path_hint}"))
        else:
            lines.append((WARNING, f"command  {path} {said}"))
        earlier = setup.earlier_command(os.path.dirname(path)) if setup.WINDOWS else None
        if earlier:
            lines.append((INFO, f"command  {earlier}, the batch file cad.exe replaces, goes at the next `cad doctor`"))
        for record in setup.records():
            if not setup.alive(record):
                lines.append((INFO, f"registry {record['path']} dangling: its interpreter {record['python']} is "
                                    "gone, and nothing reads it"))
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        lines.append((WARNING, f"registry unknown ({type(error).__name__}: {error})"))
    return lines


def _cache() -> str:
    """The engine's document cache, as ``cad status`` says it (``cache_text``): its folder and the
    documents and bytes it keeps -- each file a record names (one no record names is a leftover,
    ``_leftovers``) -- counted from the folders (a listing and a stat each), no engine asked. Nothing
    removes them but a person's delete."""
    from cad_server.engine.cache import FILE
    from cad_server.engine.cli import cache_text
    from cad.engine.ids import is_id
    from cad_server.engine.registry import DOCUMENTS, RECORD
    from cad.engine.places import cache_dir, data_dir

    try:
        root, state = cache_dir(), data_dir()
        count = size = 0
        for name in sorted(os.listdir(root / DOCUMENTS)) if (root / DOCUMENTS).is_dir() else []:
            if not is_id(name) or not (state / DOCUMENTS / name / RECORD).is_file():
                continue
            try:
                size += (root / DOCUMENTS / name / FILE).stat().st_size
            except OSError:
                continue
            count += 1
        return cache_text(root, count, size)
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return f"unknown ({type(error).__name__}: {error})"


def _leftovers():
    """What earlier releases left behind that nothing of cad uses (``cad_server._internal.leftovers``): in the
    state and cache folders of the layout of 0.11.10 and earlier (``places``: a version's own go with it), and what 0.8
    and 0.7 kept outside what 0.10 moved into its own state folder (``cad.engine.places.adopt``), in theirs, named for
    cadgen (``earlier_state_dir``, ``earlier_cache_dir``: the folders named, where ``CAD_STATE_DIR`` and
    ``CAD_CACHE_DIR`` name them)."""
    from cad_server._internal import installations, leftovers
    from cad.engine.places import (appdata_cache_dir, appdata_state_dir, earlier_cache_dir, earlier_state_dir,
                                   engines_dir, legacy_cache_dir, state_dir)

    state, cache = state_dir(), legacy_cache_dir()
    before, before_cache = earlier_state_dir(), earlier_cache_dir()
    prefixes = [record["prefix"] for record in installations.records()]
    return (leftovers.engine_records(state), leftovers.bytecode_folders(cache, prefixes, engines_dir()),
            leftovers.unrecorded(state, cache), leftovers.earlier(before), leftovers.package_environments(cache),
            leftovers.seven(before, before_cache), leftovers.appdata(appdata_state_dir(), appdata_cache_dir()))


def _environments(number: int) -> str:
    from cad_server._internal.leftovers import QUIET_DAYS, count

    return (count(number, "environment of a model's packages", "environments of models' packages")
            + f" unused for {QUIET_DAYS} days")


def _leftover_words(records, bytecode, cached, earlier, packages) -> list[str]:
    """Each class of leftovers, in words: ``3 engine records of an older format``."""
    from cad_server._internal.leftovers import count, size

    said = []
    if records.paths or records.trimmed:
        said.append(count(len(records.paths) + len(records.trimmed), "engine record", "engine records")
                    + " of an older format")
    if bytecode.paths:
        said.append(count(len(bytecode.paths), "bytecode folder", "bytecode folders")
                    + f" of installations no longer registered ({size(bytecode.bytes)})")
    if cached.paths:
        said.append(count(len(cached.paths), "cache folder", "cache folders") + f" with no record ({size(cached.bytes)})")
    if earlier.paths:
        said.append(count(len(earlier.paths), "file", "files") + " an earlier 0.8 build kept "
                    f"({', '.join(path.name for path in earlier.paths)})")
    if packages.paths:
        said.append(_environments(len(packages.paths)))
    return said


def _report_leftovers() -> list[str]:
    """The report's lines of what earlier releases left behind, where there is any: what each is, its size and when it
    was last written. Nothing of cad uses or removes them."""
    from cad_server._internal import installations, leftovers

    try:
        records, bytecode, cached, earlier, packages, seven, appdata = _leftovers()
        launchers = installations.legacy_launchers()
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [f"leftover unknown ({type(error).__name__}: {error})"]
    said = _leftover_words(records, bytecode, cached, earlier, packages)
    if launchers:
        said.append(leftovers.count(len(launchers), "launcher", "launchers") + " earlier releases published beside the "
                    f"cad command ({', '.join(os.path.basename(path) for path in launchers)})")
    lines = [f"leftover {', '.join(said)}: left by earlier releases, and nothing of this one uses them"] if said else []
    if seven.paths:
        lines.append(f"0.7      {leftovers.seven_text(seven)}: cadgen 0.7's, which nothing of this release uses")
    for path in (*appdata.paths, *appdata.recent):
        lines.append(f"0.10     {path}, a folder 0.10.0 kept on Windows, which nothing of this release uses")
    return lines


def main(argv: list[str] | None = None, prog: str = "cad doctor") -> int:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(
        prog=prog,
        description="Check this version of cad and repair it -- write the cad command where it is missing "
                    "or older, register this installation where none is, start its server -- and report what this "
                    "computer runs: the versions installed and when each was last used, the CAD kernel environment "
                    "(made on first need, never here) and the integrations', and the server. --check reports alone, "
                    "changing nothing: what a bug report wants. Exit 1 when the CAD kernel is installed and does not "
                    "load.",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Do everything but start the engine: say only whether one runs.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report alone, read-only: register nothing, write nothing (not the cad command, not a setting) and "
             "start nothing; say what cad doctor would write. What a bug report wants.",
    )
    parser.add_argument("--json", action="store_true",
                        help="the report as one JSON document: each check's name, status (ok, info, warning, failed) "
                             "and detail")
    args = parser.parse_args(argv)

    version, checks = _report(check=args.check, start=not (args.no_server or args.check))
    status = 1 if any(found["status"] == FAILED for found in checks) else 0
    if args.json:
        import json

        sys.stdout.write(json.dumps({"ok": status == 0, "version": version, "checks": checks},
                                    separators=(",", ":")) + "\n")
        return status
    from cad_server._internal.launch import SERVER

    # The whole report on stdout, a failed kernel among it: `cad doctor > report.txt` keeps all of it.
    sys.stdout.write(f"{SERVER} {version}\n")
    for found in checks:
        sys.stdout.write(f"  {found['name']:<8} {found['detail']}\n")
        for hint in found.get("more") or ():
            sys.stdout.write(f"           {hint}\n")
    return status


def _check(name: str, status: str, detail: str, more: list[str] | None = None) -> dict:
    """One line of the report: what it checks, its status (``OK``, ``INFO``, ``WARNING``, ``FAILED``) and
    its words, and the lines under it (a refused kernel's hints)."""
    return {"name": name, "status": status, "detail": detail, **({"more": more} if more else {})}


def _line(line: str, status: str | None = None) -> dict:
    """A report line a helper said whole (``registry ...``, ``version  ...``) as a check: its first word its name;
    its status ``status``, else said by its words -- one the helper could not read ``unknown``, the rest as they
    are."""
    name, _, detail = line.partition(" ")
    detail = detail.lstrip()
    if status is None:
        status = WARNING if detail.startswith("unknown (") else INFO
    return _check(name, status, detail)


def _report(*, check: bool, start: bool) -> tuple[str, list[dict]]:
    """``cad doctor``'s report: the version this installation runs as, and each check in order -- what it
    set up (nothing with ``check``), what the device runs, the cache and the leftovers, the kernel, the
    integrations' environments, the engine (started when ``start``) and sharing."""
    import cad_server
    from cad_server._internal import installations
    from cad_server._internal.installations import own_version

    installed = getattr(cad_server, "__version__", "unknown")
    location = Path(cad_server.__file__).resolve().parent
    checks = [_check("python", INFO, f"{sys.version.split()[0]} ({sys.executable})"),
              _check("install", INFO, str(location))]
    # Its record and the command it is run by (`cad_server._internal.installations`).
    checks += [_line(line, status) for status, line in _setup(check)]
    # What the computer runs for clients of 0.11.10 and earlier: the current installation, and that layout's flat
    # release folders.
    checks += [_line(line) for line in _current()]
    # Every installed version: the one report that reads them all.
    checks += [_line(line) for line in _versions()]
    # The engine's document cache: what it keeps, until a person deletes it.
    cache = _cache()
    checks.append(_check("cache", WARNING if cache.startswith("unknown (") else INFO, cache))
    # What earlier releases left behind, which nothing of this one uses.
    checks += [_line(line) for line in _report_leftovers()]
    checks.append(_kernel(check))
    # The integrations whose operations run in an environment of their own: never made here.
    checks += [_line(line, status) for status, line in _integrations()]
    # One per installation: the same door means the same warm daemon. Started here when none runs.
    checks.append(_check("server", *_server(start=start)))
    sharing = _sharing(check)
    if sharing:
        # Whether CAD's apps send usage stats, as `cad telemetry` says it.
        checks.append(_check("sharing", INFO, sharing))
    # The version this installation runs as: a development install's own name, else its release.
    return own_version() or installed, checks


def _kernel(check: bool) -> dict:
    """The CAD kernel environment, never made here (it is made on first need), and its kernel loaded there
    where it is made: ``FAILED`` -- the one failure of the report, exit 1 -- when it is installed and does
    not load."""
    from cad_server._internal.kernel_load_hint import kernel_load_hint, system_library_hint

    python, where = _kernel_environment()
    if python is None:
        # Not a failure: it is made on first need, and a wheel installed --no-deps (the release smoke
        # test) is still a correct install.
        return _check("kernel", INFO, f"not made — {where}")
    kernel_state, detail = _probe_kernel(python, read_only=True) if check else _probe_kernel(python)
    if kernel_state == KERNEL_OK:
        return _check("kernel", OK, f"OK — OCP at {detail} ({where})")
    if kernel_state == KERNEL_MISSING:
        return _check("kernel", WARNING, f"not installed — OCP is absent from {python} ({where})")
    return _check("kernel", FAILED, f"FAILED — {detail}",
                  list(kernel_load_hint(detail) or system_library_hint(detail) or ()))


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
                lines.append((OK, f"{name} cad[{integration.extra}] {release} in {_home(folder)}"))
            elif base.marked(Path(folder)) is not None:
                lines.append((INFO, f"{name} cad[{integration.extra}] {release} in {_home(folder)} has lost its "
                                    f"Python: made again on first need, {_need(name, integration)}"))
            else:
                lines.append((INFO, f"{name} cad[{integration.extra}] {release}, made on first need in "
                                    f"{_home(folder)}: {_need(name, integration)}"))
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
