"""``cadgen doctor`` — set cadgen up and report it: register the installation, write the ``cadgen``
command, make the CAD kernel environment, start the engine, and say what this device runs.

The skills' one-time step (``uvx ... --from cadgen==<version> cadgen doctor``), and the repair
command. On a device where no installation is current it registers this one
(``<state>/installations/<version>.json``) and makes it current (``cadgen._internal.installations``);
on one where an installation is, it registers nothing. It writes the proxy, ``~/.local/bin/cadgen``,
through which the skills run cadgen, and says what it found: each written, already right, or a folder
it cannot write (a sandbox's), the records of installations whose interpreter is gone, a file in the
proxy's place that is not cadgen's, another command shadowing it on PATH, and what cadgen left
behind that no cadgen running now needs (``cadgen._internal.leftovers``: engine records of an older
format, the bytecode of installations no longer registered, cache folders no record names), and
cadgen 0.7's store and state files, with their size and when they were last written. ``--prune``
removes those records, the per-version launchers (``cadgen-<version>``, ``cadgen-python-<version>``)
earlier builds published beside the proxy (``installations.prune_legacy``) and those leftovers, but
any written in the last seven days, a line for each kind; ``--all-versions`` with it removes 0.7's
however recently written. Nothing is removed without ``--prune``.

It says what the device runs, comparing nothing: the current installation, the release folders on
disk (``cadgen._internal.releases``), the last update's switch, the engine running and its release,
and each agent app's copy of the plugin and the release it pins (``cadgen._internal.providers``).

It makes the CAD kernel environment, the base every build and the engine's own kernel
processes start from (``cadgen._internal.base``: ``cadgen[kernel]`` at this release),
when it is not made -- an installation that carries the kernel itself is its own -- saying what uv
does as it works, so the first build after an install waits on nothing; ``--no-server`` says only
whether it is made. Then it proves the CAD kernel loads there. ``OCP`` is imported in a fresh
interpreter of that environment (never in this one, so the report itself stays stdlib-only and
fast to reach), and a refused load is named for what it is: on Windows 11 that is Smart App
Control blocking the unsigned ``.pyd``, which the bare ``ImportError`` never
says (``cadgen._internal.kernel_load_hint``). Run by an installation that is not the current one, it
leaves the base to the current one's ``cadgen doctor``. And it says where the engine's server, where
every build runs, keeps its door, and whether it was running or was started -- the current
installation's engine, whatever release this doctor is (``cadgen.engine.client``). ``--no-server``
does all of it but start the engine and make the CAD kernel environment, saying whether each is there:
a CI job's smoke check, which must leave no engine behind.

Exit codes: 0 = done; 4 = the kernel is installed but cannot be loaded (the report says why when it
can tell). A kernel environment that is not made, or cannot be made here (no uv, no network), is
reported, not failed: a no-deps install of the wheel (what the release workflow smoke-tests) is
still a correct install, and the first build makes it.

stdlib-only on purpose: this must work when the heavy dependency set is broken.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _server(start: bool = True) -> str:
    """The device's engine server (``cadgen.engine.daemon``): where its door is, and whether one is
    running, from which installation -- started when none is and ``start``, through the client's own
    start (the current installation's), which in a sandbox that cannot start one says so."""
    try:
        from cadgen.engine import places
        from cadgen.engine.client import request

        where = places.address()
        answer = request({"op": "status"}, start=False)
        started = False
        if not isinstance(answer, dict) and start:
            try:
                answer = request({"op": "status"}, start=True)
            except ConnectionError as error:
                return f"not running ({where}): {error}"
            started = True
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return f"unknown ({type(error).__name__}: {error})"
    if not isinstance(answer, dict):
        return f"not running ({where}); a build starts it outside a sandbox; inside one, run `cadgen server` outside first"
    from cadgen.engine.cli import workers_text

    # The version the engine runs as, and its environment; the workers as `cadgen status` counts them:
    # the standby with them.
    version = answer.get("installation") or answer.get("version")
    prefix = answer.get("prefix")
    return (f"{'started' if started else 'running'}, pid {answer.get('pid')}"
            + (f", cadgen {version}" if version else "") + (f" from {_home(prefix)}" if isinstance(prefix, str) else "")
            + f", {workers_text(answer)} ({where})")


def _current() -> list[str]:
    """What the device runs, comparing nothing: the current installation, the release folders on disk
    and the last update's switch (``cadgen._internal.switch``)."""
    from cadgen._internal import installations, releases, switch

    lines = []
    try:
        record = installations.current()
        named = installations.current_version()
        if record is not None:
            lines.append(f"current  cadgen {record['version']} ({_home(record['prefix'])})")
        elif named is not None:
            lines.append(f"current  cadgen {named}, whose installation is gone: the next client makes itself current")
        else:
            lines.append("current  none: the first CAD session or `cadgen setup` makes one current")
        found = releases.listing()
        if found:
            said = ", ".join(release["version"] + ("" if release["complete"] else " (incomplete)")
                             + (" (current)" if release["version"] == (record or {}).get("version") else "")
                             for release in found)
            lines.append(f"releases {said} in {_home(str(releases.root()))}")
        last = switch.last()
        if last is not None:
            how = (f"to cadgen {last.get('to')}" + (f" from {last.get('from')}" if last.get("from") else "")
                   + (f", {last['gapMs']} ms without an engine" if last.get("gapMs") is not None else ""))
            lines.append(f"update   {last.get('at')}: switched {how}" if last.get("ok")
                         else f"update   {last.get('at')}: the switch {how} failed: {last.get('error')}")
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        lines.append(f"current  unknown ({type(error).__name__}: {error})")
    return lines


def _apps() -> list[str]:
    """Each agent app's copy of the plugin and the release it pins, as the app says it
    (``cadgen._internal.providers``), comparing nothing."""
    try:
        from cadgen._internal import providers

        machine = providers.Machine.here()
        found = providers.detect(machine)
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [f"apps     unknown ({type(error).__name__}: {error})"]
    lines = []
    for name, app in found.items():
        if not app.present:
            continue
        ours, stores = app.ours(), app.stores()
        if ours is not None:
            lines.append(f"app      {app.label}: " + (f"cadgen {ours.version or '?'}" if name == "claude-desktop"
                                                     else ours.words(machine)))
        elif stores:
            lines.append(f"app      {app.label}: {stores[0].words(machine)}, which its store updates")
    return lines


def _command_path_hint(path: str) -> str:
    """How to reach the proxy when PATH does not resolve ``cadgen`` to it. The running
    interpreter's own environment is left out of the lookup: ``uvx`` puts its ephemeral
    environment's ``bin`` first on PATH for the command it runs, so inside ``uvx ... cadgen doctor``
    the environment's own ``cadgen`` script would otherwise read as shadowing the proxy."""
    from shutil import which

    prefix = os.path.realpath(sys.prefix)
    entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep)
               if entry and not os.path.realpath(entry).startswith(prefix + os.sep)]
    found = which("cadgen", path=os.pathsep.join(entries))
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


def _sharing() -> str | None:
    """``on`` or ``off`` for the usage stats CAD sends, and why, or ``None`` if it cannot tell."""
    try:
        from cadgen.cli.telemetry import describe

        return describe()
    except Exception:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return None


KERNEL_OK = "ok"
KERNEL_MISSING = "missing"
KERNEL_FAILED = "failed"


def _kernel_environment(make: bool) -> tuple[str | None, str]:
    """The CAD kernel environment (``cadgen._internal.base``), made first when it is not and
    ``make``, each line of uv's work said as it goes: ``(its Python, where it is)``, or ``(None, why there
    is none)``."""
    from cadgen._internal import base

    def say(line: str) -> None:
        sys.stdout.write(f"  kernel   {line}\n")
        sys.stdout.flush()

    try:
        installation = base.Installation.here()
        found = base.ensure(installation, make=make, told=say)
        if found is None:
            return None, f"{base.where(installation)}, not made: cadgen doctor, or the first build, makes it"
    except base.Refused as refused:
        return None, str(refused)
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return None, f"{type(error).__name__}: {error}"
    return found.python, ("this installation carries it" if found.own else f"the CAD kernel environment, {found.prefix}")


def _probe_kernel(python: str | None = None) -> tuple[str, str]:
    """Import OCP in a fresh interpreter (``python``'s, else this one's): ``(state, detail)``.

    ``state`` is ``KERNEL_OK`` (``detail`` is the module's path),
    ``KERNEL_MISSING`` (no OCP installed: ``ModuleNotFoundError``), or
    ``KERNEL_FAILED`` (installed but would not load; ``detail`` is the last
    non-empty stderr line, the exception). A subprocess, so a kernel that
    crashes the interpreter or takes the ~2.5 s import cannot take the report
    down with it, and so this process never carries the kernel itself.
    """
    import os
    import subprocess

    try:
        # Both ends name utf-8: the child's stdio would otherwise be the ANSI code page
        # on Windows, which cannot carry every path or every localized loader error.
        # ``-P``, as every child cadgen starts: the kernel the installation imports, never a
        # module of that name in the folder the command was run from.
        result = subprocess.run(
            [python or sys.executable, "-P", "-c", "import OCP; print(OCP.__file__)"],
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


def _setup() -> list[str]:
    """The report lines of the setup: on a device with no current installation, this installation
    registered and made current when it may (a source tree registers only when named); the proxy
    written; the records whose interpreter is gone, and why a write failed, which in a sandbox is the
    folder being out of reach."""
    from cadgen._internal import installations as setup

    lines = []
    try:
        version = setup.own_version()
        current = setup.current()
        if current is not None and not setup.mine(current):
            registered, proxy = "current", setup.write_proxy()
        elif version:
            registered, proxy = setup.setup(version)
        else:
            registered, proxy = None, (setup.proxy_path(), setup.proxy_status(), None)
        if registered == "current":
            lines.append(f"registry cadgen {current['version']} is the current installation: this one registers "
                         "nothing")
        elif registered is None:
            lines.append(f"registry not registered: a source tree registers only as a version it is named "
                         f"({setup.NAME_ENV})")
        else:
            path, status, error = registered
            lines.append(f"registry {path} " + (f"cannot be written here ({error}): run this outside any sandbox" if error
                                                else "registered" if status == setup.REGISTERED else "OK"))
        path, status, error = proxy
        said = {setup.OK: "OK", setup.NEWER: "OK (a later cadgen's)",
                setup.FOREIGN: "is not cadgen's (left alone): remove it to run cadgen +<version> by it",
                setup.MISSING: "missing", setup.STALE: "stale"}[status]

        path_hint = _command_path_hint(path)
        if error:
            lines.append(f"command  {path} {said}; cannot write it here ({error}): run this outside any sandbox")
        elif status in (setup.MISSING, setup.STALE) and version:
            lines.append(f"command  {path} written (was {said}){path_hint}")
        elif status in (setup.OK, setup.NEWER):
            lines.append(f"command  {path} {said}{path_hint}")
        else:
            lines.append(f"command  {path} {said}")
        for record in setup.records():
            if not setup.alive(record):
                lines.append(f"registry {record['path']} dangling: its interpreter {record['python']} is gone "
                             "(cadgen doctor --prune removes it)")
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        lines.append(f"registry unknown ({type(error).__name__}: {error})")
    return lines


def _cache() -> str:
    """The engine's document cache, as ``cadgen status`` says it (``cache_text``): its folder and the
    documents and bytes it keeps -- each file a record names (one no record names is a leftover,
    ``_leftovers``) -- counted from the folders (a listing and a stat each), no engine asked. Nothing
    removes them but a person's delete."""
    from cadgen.engine.cache import FILE
    from cadgen.engine.cli import cache_text
    from cadgen.engine.ids import is_id
    from cadgen.engine.registry import DOCUMENTS, RECORD
    from cadgen.engine.places import cache_dir, state_dir

    try:
        root, state = cache_dir(), state_dir()
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
    """What cadgen left behind that no cadgen running now needs (``cadgen._internal.leftovers``):
    the state and cache folders, and each class found in them."""
    from cadgen._internal import installations, leftovers
    from cadgen.engine.places import cache_dir, engine_dir, state_dir

    state, cache = state_dir(), cache_dir()
    prefixes = [record["prefix"] for record in installations.records()]
    return (state, cache, leftovers.engine_records(state),
            leftovers.bytecode_folders(cache, prefixes, engine_dir()), leftovers.unrecorded(state, cache),
            leftovers.earlier(state), leftovers.seven(state, cache))


def _leftover_words(records, bytecode, cached, earlier) -> list[str]:
    """Each class of leftovers that may go, in words: ``3 engine records of an older format``."""
    from cadgen._internal.leftovers import count, size

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
    return said


def _report_leftovers() -> list[str]:
    """The report's lines of what ``--prune`` would remove, when there is any, and of cadgen 0.7's
    leftovers, when there are any: their size, when they were last written, and when they go."""
    from cadgen._internal import leftovers

    try:
        _state, _cache, records, bytecode, cached, earlier, seven = _leftovers()
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [f"leftover unknown ({type(error).__name__}: {error})"]
    said = _leftover_words(records, bytecode, cached, earlier)
    lines = [f"leftover {', '.join(said)}: cadgen doctor --prune removes them"] if said else []
    if seven.paths:
        when = ("cadgen doctor --prune removes it" if leftovers.quiet(seven) else
                f"cadgen doctor --prune removes it once nothing has written it for {leftovers.QUIET_DAYS} days, "
                "or now with --all-versions")
        lines.append(f"0.7      {leftovers.seven_text(seven)}: {when}")
    return lines


def _prune_leftovers(all_versions: bool = False) -> list[str]:
    """What cadgen left behind that no cadgen needs, removed: a line for each class it removed, and
    for cadgen 0.7's leftovers, removed or kept (``all_versions``: removed whenever last written)."""
    from cadgen._internal import leftovers
    from cadgen._internal.leftovers import count, size

    state, _cache, records, bytecode, cached, earlier, seven = _leftovers()
    lines = []
    removed, trimmed = leftovers.remove_engine_records(state, records)
    if removed:
        lines.append(f"removed {count(removed, 'engine record', 'engine records')} of an older format")
    if trimmed:
        lines.append(f"removed the page token {count(trimmed, 'engine record', 'engine records')} still carried "
                     "(the port each rolled to is kept)")
    gone = leftovers.remove(bytecode.paths)
    if gone:
        lines.append(f"removed {count(gone, 'bytecode folder', 'bytecode folders')} of installations no longer "
                     f"registered ({size(bytecode.bytes)})")
    gone = leftovers.remove(cached.paths)
    if gone:
        lines.append(f"removed {count(gone, 'cache folder', 'cache folders')} with no record ({size(cached.bytes)})")
    for path in earlier.paths:
        if leftovers.remove([path]):
            lines.append(f"removed {path}, a file an earlier 0.8 build kept")
    if seven.paths and (all_versions or leftovers.quiet(seven)):
        left = [path for path in seven.paths if leftovers.remove([path]) == 0]
        lines.append(f"removed {leftovers.seven_text(seven)}" + "".join(f"; could not remove {path}" for path in left))
    elif seven.paths:
        lines.append(f"kept {leftovers.seven_text(seven)}: a cadgen 0.7 still installed may use it; it goes once "
                     f"nothing has written it for {leftovers.QUIET_DAYS} days, or now with --all-versions")
    return lines


def main(argv: list[str] | None = None, prog: str = "cadgen doctor") -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Set cadgen up (register it, write the cadgen command, make the CAD kernel environment, "
                    "start the engine) and report what this device runs: the current installation, the "
                    "releases on disk, the engine and each agent app's plugin.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove the record of every registered installation whose interpreter is gone, the "
             "per-version launchers earlier builds published beside the cadgen command, engine records of an "
             "older format, the bytecode folders of installations no longer registered, cache folders with "
             "no record and cadgen 0.7's store and state files (none written in the last 7 days), and exit.",
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="With --prune: remove cadgen 0.7's store and state files too, however recently they were written "
             "(without it they go once nothing has written them for 7 days). Only once no cadgen 0.7 is "
             "installed in any agent app.",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Do everything but start the engine and make the CAD kernel environment: say only whether each is there.",
    )
    args = parser.parse_args(argv)
    if args.all_versions and not args.prune:
        parser.error("--all-versions goes with --prune")

    if args.prune:
        from cadgen._internal import installations

        removed = installations.prune()
        for path in removed:
            sys.stdout.write(f"removed {path}\n")
        if not removed:
            sys.stdout.write("no registered installation has lost its interpreter\n")
        # And the per-version launchers earlier 0.8 builds published beside the cadgen command.
        for path in installations.prune_legacy():
            sys.stdout.write(f"removed {path}, a launcher the cadgen command replaces\n")
        # And what no cadgen needs any more: old engine records, bytecode, cache folders no record names.
        for line in _prune_leftovers(args.all_versions):
            sys.stdout.write(f"{line}\n")
        return 0

    import cadgen
    from cadgen._internal import installations
    from cadgen._internal.installations import own_version

    installed = getattr(cadgen, "__version__", "unknown")
    location = Path(cadgen.__file__).resolve().parent
    # The version this installation runs as: a development install's own name, else its release.
    sys.stdout.write(f"cadgen {own_version() or installed}\n")
    sys.stdout.write(f"  python   {sys.version.split()[0]} ({sys.executable})\n")
    sys.stdout.write(f"  install  {location}\n")
    # Its record and the command the skills run it by (`cadgen._internal.installations`).
    for line in _setup():
        sys.stdout.write(f"  {line}\n")
    # What the device runs: the current installation, the release folders, the last switch.
    for line in _current():
        sys.stdout.write(f"  {line}\n")
    # The engine's document cache: what it keeps, until a person deletes it.
    sys.stdout.write(f"  cache    {_cache()}\n")
    # What --prune would remove: nothing is removed without it.
    for line in _report_leftovers():
        sys.stdout.write(f"  {line}\n")

    from cadgen._internal.kernel_load_hint import kernel_load_hint

    # The CAD kernel environment, made here when it is not (but with --no-server), and its kernel loaded
    # there, before the engine starts: an engine that finds it made starts its standby there, which
    # loads the kernel while nobody waits. The current installation's doctor makes the current one's.
    current = installations.current()
    if current is not None and not installations.mine(current):
        python, where = None, f"the current installation's (cadgen {current['version']}): its `cadgen doctor` checks it"
    else:
        python, where = _kernel_environment(make=not args.no_server)
    kernel_state, detail = _probe_kernel(python) if python is not None else (KERNEL_MISSING, where)
    kernel_loaded = kernel_state != KERNEL_FAILED
    status = 0 if kernel_loaded else 4
    if kernel_state == KERNEL_OK:
        sys.stdout.write(f"  kernel   OK — OCP at {detail} ({where})\n")
    elif python is None:
        # Not a failure: the first build makes it, and a wheel installed --no-deps (the release smoke
        # test) is still a correct install.
        sys.stdout.write(f"  kernel   not made — {detail}\n")
    elif kernel_state == KERNEL_MISSING:
        sys.stdout.write(f"  kernel   not installed — OCP is absent from {python} ({where})\n")
    else:
        sys.stderr.write(f"  kernel   FAILED — {detail}\n")
        for hint in kernel_load_hint(detail) or ():
            sys.stderr.write(f"           {hint}\n")
    # One per installation: the same door means the same warm daemon. Started here when none runs.
    sys.stdout.write(f"  server   {_server(start=not args.no_server)}\n")
    sharing = _sharing()
    if sharing:
        # Whether CAD's apps send usage stats, as `cadgen telemetry` says it.
        sys.stdout.write(f"  sharing  {sharing}\n")
    # Each agent app's copy of the plugin, and the release it pins.
    for line in _apps():
        sys.stdout.write(f"  {line}\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
