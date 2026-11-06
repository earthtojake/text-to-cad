"""``cad doctor`` — set the server up and report it: register the installation, write the ``cad``
command, start the engine, and say what this device runs.

The skills' one-time step (``uvx ... --from cad-server==<version> cad doctor``), and the repair
command. On a device where no installation is current it registers this one
(``<state>/installations/<version>.json``) and makes it current (``cad_server._internal.installations``);
on one where an installation is, it registers nothing. It writes the proxy, ``~/.local/bin/cad``
(on Windows ``cad.exe``, with the Python it runs by), through which the skills run the server, and says what it found: each written, already right, or a
folder it cannot write (a sandbox's), the records of installations whose interpreter is gone, a file in
the proxy's place that is not text-to-cad's, another command shadowing it on PATH, and what earlier
releases left behind that none running now needs (``cad_server._internal.leftovers``: engine records of an older
format, the bytecode of installations no longer registered, cache folders no record names, environments
of models' packages unused for a week), and
cadgen 0.7's store and state files, with their size and when they were last written. ``--prune``
removes those records, the release folders but the current release's and the one before's (one an update
failed to move to among them: ``releases.kept``), the launchers earlier releases published beside the proxy (0.8's ``cadgen``
proxy, ``cadgen-<version>``, ``cadgen-python-<version>``: ``installations.prune_legacy``) and those leftovers, but
any written in the last seven days, a line for each kind; ``--all-versions`` with it removes 0.7's
however recently written. Nothing is removed without ``--prune``.

It says what the device runs, comparing nothing: the current installation, the release folders on
disk (``cad_server._internal.releases``), the last update's switch, the engine running and its release,
the plugin folder every app's plugin comes from (``cad_server._internal.plugin``) and each agent app's
copy of the plugin: the release it pins and where it comes from -- the folder read in place, linked, or
copied, and when (``cad_server._internal.providers``) --, and the agents the Skills CLI copied the
skills for. Registering the current installation writes the plugin folder again, so it repairs one
that is gone.

It says whether the CAD kernel environment, the base the engine's own kernel processes start from
(``cad_server._internal.base``: ``cad[build123d]`` at this release), is made -- it never makes it: it is
made on first need, by the first build or view that needs the kernel; an installation that carries the
kernel itself is its own -- and, where it is, proves the CAD kernel loads there. ``OCP`` is imported in a fresh
interpreter of that environment (never in this one, so the report itself stays stdlib-only and
fast to reach), and a refused load is named for what it is: on Windows 11 that is Smart App
Control blocking the unsigned ``.pyd``, which the bare ``ImportError`` never
says (``cad_server._internal.kernel_load_hint``). Run by an installation that is not the current one, it
leaves the base to the current one's ``cad doctor``. And it says where the engine's server, where
every build runs, keeps its door, and whether it was running or was started -- the current
installation's engine, whatever release this doctor is (``cad.engine.client``). ``--no-server``
does all of it but start the engine, saying whether one runs: a CI job's smoke check, which must leave
no engine behind. It says too where each integration's operations run (``trimesh``'s manufacturing
check, ``kicad``'s commands): this installation's own environment, or ``cad[<integration>]``'s, made on
first need and never here (``integration_env.found``).

``--check`` is the report alone, read-only: it registers nothing, writes nothing -- not the ``cad``
command, not the telemetry notice, not an install id, not the bytecode of the kernel it loads -- and starts
nothing, saying what ``cad doctor`` would write; what a bug report wants. ``--json`` is the report as one
document on stdout, ``{"ok", "version", "checks": [{"name", "status", "detail"}]}``, each check's status
``ok``, ``info``, ``warning`` or ``failed`` (with ``--prune``, ``{"ok", "pruned": [lines]}``). The whole
report goes to stdout, a failed kernel among it.

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
# look (a write a sandbox refused, a command that is not text-to-cad's), and failed (the exit status 1).
OK, INFO, WARNING, FAILED = "ok", "info", "warning", "failed"


def _server(start: bool = True, answered: list | None = None) -> tuple[str, str]:
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
    if answered is not None:
        answered.append(answer)  # what the engine said, for the lines after this one (``_automatic``)
    from cad_server.engine.cli import workers_text

    # The version the engine runs as, and its environment; the workers as `cad status` counts them:
    # the standby with them.
    version = answer.get("installation") or answer.get("version")
    prefix = answer.get("prefix")
    return OK, (f"{'started' if started else 'running'}, pid {answer.get('pid')}"
                + (f", text-to-cad {version}" if version else "")
                + (f" from {_home(prefix)}" if isinstance(prefix, str) else "") + f", {workers_text(answer)} ({where})")


def _current() -> list[str]:
    """What the device runs, comparing nothing: the current installation, the release folders on disk
    and the last update's switch (``cad_server._internal.switch``)."""
    from cad_server._internal import installations, releases, switch

    lines = []
    try:
        record = installations.current()
        named = installations.current_version()
        if record is not None:
            lines.append(f"current  text-to-cad {record['version']} ({_home(record['prefix'])})")
        elif named is not None:
            lines.append(f"current  text-to-cad {named}, whose installation is gone: the next client makes itself current")
        else:
            lines.append("current  none: the first CAD session or `cad setup` makes one current")
        found = releases.listing()
        if found:
            current = (record or {}).get("version") or named
            kept = releases.kept(current) if current else {release["version"] for release in found}
            said = ", ".join(release["version"] + ("" if release["complete"] else " (incomplete)")
                             + (" (current)" if release["version"] == current else
                                " (the release before)" if release["version"] in kept else
                                " (cad doctor --prune removes it)")
                             for release in found)
            lines.append(f"releases {said} in {_home(str(releases.root()))}")
        last = switch.last()
        if last is not None:
            how = (f"to text-to-cad {last.get('to')}" + (f" from {last.get('from')}" if last.get("from") else "")
                   + (f", {last['gapMs']} ms without an engine" if last.get("gapMs") is not None else ""))
            lines.append(f"update   {last.get('at')}: switched {how}" if last.get("ok")
                         else f"update   {last.get('at')}: the switch {how} failed: {last.get('error')}")
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        lines.append(f"current  unknown ({type(error).__name__}: {error})")
    return lines


def _plugin() -> list[str]:
    """The plugin folder every app's plugin comes from (``cad_server._internal.plugin``): its release and
    when it was written, or that there is none."""
    try:
        from cad_server._internal import plugin

        where = plugin.folder()
        found = plugin.written(where)
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [f"plugin   unknown ({type(error).__name__}: {error})"]
    if found is None:
        return [f"plugin   {_home(str(where))}: not written; `cad setup` writes it, and points the apps at it"]
    return [f"plugin   {_home(str(where))}: text-to-cad {found['version'] or '?'}, written {found['at']}"]


def _apps() -> list[str]:
    """Each agent app's copy of the plugin, the release it pins and where it comes from -- the plugin folder
    read in place, linked or copied, and when -- as the app says it (``cad_server._internal.providers``),
    comparing nothing; and, as the receipt says, the store's copies ``cad setup`` replaced with ours and
    the agents the Skills CLI copied the skills for."""
    try:
        import json

        from cad_server._internal import plugin, providers
        from cad.engine.places import state_dir

        machine = providers.Machine.here()
        found = providers.detect(machine, folder=plugin.folder())
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [f"apps     unknown ({type(error).__name__}: {error})"]
    lines = []
    for name, app in found.items():
        if not app.present:
            continue
        ours, stores = app.ours(), app.stores()
        if ours is not None:
            origin = ours.origin(machine)
            lines.append(f"app      {app.label}: " + (f"text-to-cad {ours.version or '?'}" if name == "claude-desktop"
                                                     else ours.words(machine)) + (f", {origin}" if origin else ""))
        elif stores:
            lines.append(f"app      {app.label}: {stores[0].words(machine)}, which its store updates")
    try:
        receipt = json.loads((Path(state_dir()) / "install-receipt.json").read_text(encoding="utf-8"))
        skills = receipt.get("skills") if isinstance(receipt, dict) else None
    except (OSError, ValueError):
        receipt, skills = None, None
    for gone in providers.replaced(receipt if isinstance(receipt, dict) else None):
        lines.append(f"app      {providers.label(gone['app'])}: {gone['store']}: the directory's copy, replaced by "
                     "cad setup"
                     + (f" ({str(gone['at']).replace('T', ' ').rstrip('Z')[:16]})" if gone.get("at") else ""))
    for agent, got in (skills or {}).items() if isinstance(skills, dict) else ():
        if agent in providers.SKILLS_AGENTS and isinstance(got, dict):
            lines.append(f"app      {providers.label(agent)}: the skills of text-to-cad {got.get('release') or '?'}, "
                         f"copied into {providers.shown(got.get('folder') or '?', machine)} by the Skills CLI"
                         + (f" ({str(got['at']).replace('T', ' ').rstrip('Z')[:16]})" if got.get("at") else ""))
    return lines


def _command_path_hint(path: str) -> str:
    """How to reach the proxy when PATH does not resolve ``cad`` to it. The person's PATH is the one
    looked in (``providers.lasting``): ``uvx`` puts its ephemeral environment's ``bin`` first on PATH
    for the command it runs, so inside ``uvx ... cad doctor`` -- and the install command's ``cad
    setup`` -- that environment's own ``cad`` script would otherwise read as shadowing the proxy."""
    from shutil import which

    from cad_server._internal.providers import lasting

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


def _automatic(status: dict | None = None) -> str | None:
    """Automatic updates, on or off and why, the feed's last read and next, and what the engine running
    is getting ready (its ``status``, as the server line asked it: ``cad_server.auto_updates.describe``), or
    ``None`` if it cannot tell."""
    try:
        from cad_server import auto_updates

        engine = status.get("update") if isinstance(status, dict) else None
        return auto_updates.describe(engine if isinstance(engine, dict) else None)
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
            lines.append((OK, f"registry text-to-cad {current['version']} is the current installation: this one "
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
                setup.FOREIGN: "is not text-to-cad's (left alone): remove it to run cad by it",
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
                lines.append((WARNING, f"registry {record['path']} dangling: its interpreter {record['python']} is "
                                       "gone (cad doctor --prune removes it)"))
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
    from cad.engine.places import cache_dir, state_dir

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


def _leftovers(gone=frozenset()):
    """What earlier releases left behind that none running now needs (``cad_server._internal.leftovers``):
    the state and cache folders, and each class found in them -- read as if the installations whose prefixes
    are ``gone`` were no longer registered (``--prune``'s plan, before it removes them). What 0.8 and 0.7 kept
    outside what 0.10 moved into its own state folder (``cad.engine.places.adopt``) is in theirs, named for
    cadgen (``earlier_state_dir``, ``earlier_cache_dir``: the folders named, where ``CAD_STATE_DIR`` and
    ``CAD_CACHE_DIR`` name them)."""
    from cad_server._internal import installations, leftovers
    from cad.engine.places import (appdata_cache_dir, appdata_state_dir, cache_dir, earlier_cache_dir,
                                   earlier_state_dir, engine_dir, state_dir)

    state, cache = state_dir(), cache_dir()
    before, before_cache = earlier_state_dir(), earlier_cache_dir()
    prefixes = [record["prefix"] for record in installations.records() if record["prefix"] not in gone]
    return (state, cache, leftovers.engine_records(state),
            leftovers.bytecode_folders(cache, prefixes, engine_dir()), leftovers.unrecorded(state, cache),
            leftovers.earlier(before), leftovers.package_environments(cache), leftovers.seven(before, before_cache),
            leftovers.appdata(appdata_state_dir(), appdata_cache_dir()))


def _environments(number: int) -> str:
    from cad_server._internal.leftovers import QUIET_DAYS, count

    return (count(number, "environment of a model's packages", "environments of models' packages")
            + f" unused for {QUIET_DAYS} days")


def _leftover_words(records, bytecode, cached, earlier, packages) -> list[str]:
    """Each class of leftovers that may go, in words: ``3 engine records of an older format``."""
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
    """The report's lines of what ``--prune`` would remove, when there is any, and of cadgen 0.7's
    leftovers, when there are any: their size, when they were last written, and when they go."""
    from cad_server._internal import leftovers

    try:
        _state, _cache, records, bytecode, cached, earlier, packages, seven, appdata = _leftovers()
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [f"leftover unknown ({type(error).__name__}: {error})"]
    said = _leftover_words(records, bytecode, cached, earlier, packages)
    lines = [f"leftover {', '.join(said)}: cad doctor --prune removes them"] if said else []
    if seven.paths:
        when = ("cad doctor --prune removes it" if leftovers.quiet(seven) else
                f"cad doctor --prune removes it once nothing has written it for {leftovers.QUIET_DAYS} days, "
                "or now with --all-versions")
        lines.append(f"0.7      {leftovers.seven_text(seven)}: {when}")
    for path in appdata.paths:
        lines.append(f"0.10     {path}, a folder 0.10.0 kept on Windows: cad doctor --prune removes it")
    for path in appdata.recent:
        lines.append(f"0.10     {path}, a folder 0.10.0 kept on Windows: cad doctor --prune removes it once "
                     f"nothing has written it for {leftovers.QUIET_DAYS} days")
    return lines


def _prune_plan(all_versions: bool = False) -> list[str]:
    """What ``--prune`` removes, a line per kind with its count, read and nothing removed: what it asks
    consent for (``cad_server._internal.consent``). The leftovers are read as they will be once the records
    and release folders it removes first are gone (``_leftovers``' ``gone``): the bytecode of an installation
    it takes out is among them."""
    from cad_server._internal import installations, leftovers, releases
    from cad_server._internal.leftovers import count

    lines = []
    records = installations.records()
    dangling = [record for record in records if not installations.alive(record)]
    if dangling:
        lines.append(f"{count(len(dangling), 'installation record', 'installation records')} whose interpreter is gone")
    folders: list[dict] = []
    if installations.current_version():
        kept = releases.kept()
        folders = [found for found in releases.listing() if found["version"] not in kept]
        if folders:
            lines.append(f"{count(len(folders), 'release folder', 'release folders')} but the current release's and "
                         f"the one before's: {', '.join(found['version'] for found in folders)}")
    legacy = installations.legacy_launchers()
    if legacy:
        lines.append(f"{count(len(legacy), 'launcher', 'launchers')} earlier releases published beside the cad command: "
                     f"{', '.join(os.path.basename(path) for path in legacy)}")

    def inside(prefix: str) -> bool:
        return any(os.path.realpath(prefix).startswith(os.path.realpath(found["path"]) + os.sep) for found in folders)

    gone = {record["prefix"] for record in records if record in dangling or inside(record["prefix"])}
    _state, _cache, engine_records, bytecode, cached, earlier, packages, seven, appdata = _leftovers(gone)
    lines += _leftover_words(engine_records, bytecode, cached, earlier, packages)
    if seven.paths and (all_versions or leftovers.quiet(seven)):
        lines.append(leftovers.seven_text(seven))
    lines += [f"{path}, a folder 0.10.0 kept on Windows" for path in appdata.paths]
    return lines


def _prune_leftovers(all_versions: bool = False) -> list[str]:
    """What cadgen left behind that no cadgen needs, removed: a line for each class it removed, and
    for cadgen 0.7's leftovers, removed or kept (``all_versions``: removed whenever last written)."""
    from cad_server._internal import leftovers
    from cad_server._internal.leftovers import count, size

    state, _cache, records, bytecode, cached, earlier, packages, seven, appdata = _leftovers()
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
    gone = leftovers.remove(packages.paths)
    if gone:
        lines.append(f"removed {_environments(gone)}")
    if seven.paths and (all_versions or leftovers.quiet(seven)):
        left = [path for path in seven.paths if leftovers.remove([path]) == 0]
        lines.append(f"removed {leftovers.seven_text(seven)}" + "".join(f"; could not remove {path}" for path in left))
    elif seven.paths:
        lines.append(f"kept {leftovers.seven_text(seven)}: a cadgen 0.7 still installed may use it; it goes once "
                     f"nothing has written it for {leftovers.QUIET_DAYS} days, or now with --all-versions")
    for path in appdata.paths:
        lines.append(f"removed {path}, a folder 0.10.0 kept on Windows" if leftovers.remove([path])
                     else f"could not remove {path}, a folder 0.10.0 kept on Windows")
    return lines


def main(argv: list[str] | None = None, prog: str = "cad doctor") -> int:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(
        prog=prog,
        description="Set the server up -- register this installation where none is current, write the cad command, "
                    "start the engine -- and report what this device runs: the current installation, the releases "
                    "on disk, the CAD kernel environment (made on first need, never here) and the integrations', "
                    "the engine and each agent app's plugin. --check reports alone, changing nothing: what a bug "
                    "report wants. Exit 1 when the CAD kernel is installed and does not load.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove the record of every registered installation whose interpreter is gone, the "
             "per-version launchers earlier builds published beside the cad command, engine records of an "
             "older format, the bytecode folders of installations no longer registered, cache folders with "
             "no record, environments of models' packages and cadgen 0.7's store and state files (none written "
             "or used in the last 7 days), and exit.",
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
                             "and detail; with --prune, what it removed")
    from cad_server._internal.consent import add_yes

    add_yes(parser, "with --prune, remove what it lists")
    args = parser.parse_args(argv)
    if args.all_versions and not args.prune:
        parser.error("--all-versions goes with --prune")
    if args.check and args.prune:
        parser.error("--check changes nothing and --prune removes: give one")

    if args.prune:
        return _prune(args, prog)

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


def _prune(args, prog: str) -> int:
    """``cad doctor --prune``: its plan said and asked first (``_prune_plan``; nothing is asked when there is
    nothing to remove), then a line for what it removed of each kind -- on stdout, or under ``--json`` as one
    document, ``{"ok": true, "pruned": [lines]}``."""
    import json

    from cad_server._internal import installations
    from cad_server._internal.cli_errors import Failure, write
    from cad_server._internal.consent import confirm, retry

    plan = _prune_plan(args.all_versions)
    if plan:
        try:
            confirm(f"removing {len(plan)} kind{'' if len(plan) == 1 else 's'} of leftovers", "Remove them?",
                    yes=bool(args.yes), as_json=bool(args.json),
                    command=retry(prog, ["--prune", *(["--all-versions"] if args.all_versions else []),
                                         *(["--json"] if args.json else [])]),
                    preview=[f"{prog} --prune removes what no release running now needs:",
                             *(f"  {line}" for line in plan), "This cannot be undone."])
        except Failure as failure:
            return write(failure, prog=prog, as_json=bool(args.json))
    lines = []
    removed = installations.prune()
    lines += [f"removed {path}" for path in removed]
    if not removed:
        lines.append("no registered installation has lost its interpreter")
    # And the release folders but the current one's and the one before's (``releases.kept``): one an update
    # failed to move to among them, its failure still recorded. None while no installation is current.
    from cad_server._internal import releases

    if installations.current_version():
        lines += [f"removed {path}" for path in releases.collect(releases.kept())]
    # And the launchers earlier releases published beside the cad command: 0.8's proxy among them.
    lines += [f"removed {path}, a launcher the cad command replaces" for path in installations.prune_legacy()]
    # And what no cadgen needs any more: old engine records, bytecode, cache folders no record names.
    lines += _prune_leftovers(args.all_versions)
    if args.json:
        sys.stdout.write(json.dumps({"ok": True, "pruned": lines}, separators=(",", ":")) + "\n")
    else:
        sys.stdout.write("".join(f"{line}\n" for line in lines))
    return 0


def _check(name: str, status: str, detail: str, more: list[str] | None = None) -> dict:
    """One line of the report: what it checks, its status (``OK``, ``INFO``, ``WARNING``, ``FAILED``) and
    its words, and the lines under it (a refused kernel's hints)."""
    return {"name": name, "status": status, "detail": detail, **({"more": more} if more else {})}


def _line(line: str, status: str | None = None) -> dict:
    """A report line a helper said whole (``registry ...``, ``app      Claude Code: ...``) as a check: its first
    word its name; its status ``status``, else said by its words -- one the helper could not read ``unknown``,
    a switch that failed a warning, the rest as they are."""
    name, _, detail = line.partition(" ")
    detail = detail.lstrip()
    if status is None:
        status = WARNING if detail.startswith("unknown (") or (name == "update" and " failed: " in detail) else INFO
    return _check(name, status, detail)


def _report(*, check: bool, start: bool) -> tuple[str, list[dict]]:
    """``cad doctor``'s report: the version this installation runs as, and each check in order -- what it
    set up (nothing with ``check``), what the device runs, the cache and the leftovers, the kernel, the
    integrations' environments, the engine (started when ``start``), updates and sharing, the plugin and
    each app's copy of it."""
    import cad_server
    from cad_server._internal import installations
    from cad_server._internal.installations import own_version

    installed = getattr(cad_server, "__version__", "unknown")
    location = Path(cad_server.__file__).resolve().parent
    checks = [_check("python", INFO, f"{sys.version.split()[0]} ({sys.executable})"),
              _check("install", INFO, str(location))]
    # Its record and the command the skills run it by (`cad_server._internal.installations`).
    checks += [_line(line, status) for status, line in _setup(check)]
    # What the device runs: the current installation, the release folders, the last switch.
    checks += [_line(line) for line in _current()]
    # The engine's document cache: what it keeps, until a person deletes it.
    cache = _cache()
    checks.append(_check("cache", WARNING if cache.startswith("unknown (") else INFO, cache))
    # What --prune would remove: nothing is removed without it.
    checks += [_line(line) for line in _report_leftovers()]
    checks.append(_kernel(check))
    # The integrations whose operations run in an environment of their own: never made here.
    checks += [_line(line, status) for status, line in _integrations()]
    # One per installation: the same door means the same warm daemon. Started here when none runs.
    answered: list = []
    checks.append(_check("server", *_server(start=start, answered=answered)))
    automatic = _automatic(answered[0] if answered else None)
    if automatic:
        # Whether the engine updates by itself, as `cad update auto` says it.
        checks.append(_check("updates", INFO, f"automatic {automatic}"))
    sharing = _sharing(check)
    if sharing:
        # Whether CAD's apps send usage stats, as `cad telemetry` says it.
        checks.append(_check("sharing", INFO, sharing))
    # The plugin folder, and each agent app's copy of the plugin: the release it pins and where it comes from.
    checks += [_line(line, OK if line.startswith("plugin") and ", written " in line else None) for line in _plugin()]
    checks += [_line(line) for line in _apps()]
    # The version this installation runs as: a development install's own name, else its release.
    return own_version() or installed, checks


def _kernel(check: bool) -> dict:
    """The CAD kernel environment, never made here (it is made on first need), and its kernel loaded there
    where it is made: ``FAILED`` -- the one failure of the report, exit 1 -- when it is installed and does
    not load. The current installation's doctor checks the current one's."""
    from cad_server._internal import installations
    from cad_server._internal.kernel_load_hint import kernel_load_hint

    current = installations.current()
    if current is not None and not installations.mine(current):
        python, where = None, f"the current installation's (text-to-cad {current['version']}): its `cad doctor` checks it"
    else:
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
    return _check("kernel", FAILED, f"FAILED — {detail}", list(kernel_load_hint(detail) or ()))


def _integrations() -> list[tuple[str, str]]:
    """Each integration whose operations run in an environment of their own (``cad[<integration>]``, made on
    first need: ``cad_server._internal.integration_env``) -- this installation's own where it carries it, else
    that environment, made or where it will be -- read, never made: what a manufacturing check (trimesh) or a
    KiCad command (kicad) runs in. The CAD kernel's is the kernel line's."""
    try:
        from cad.registry import INTEGRATIONS
        from cad_server._internal import integration_env

        lines = []
        for name, integration in INTEGRATIONS.items():
            if name == "build123d" or not integration.extra:
                continue
            state, folder, release = integration_env.found(name)
            if state == "carried":
                lines.append((OK, f"{name} this installation carries it (cad[{integration.extra}])"))
            elif state == "made":
                lines.append((OK, f"{name} cad[{integration.extra}] {release} in {_home(folder)}"))
            else:
                lines.append((INFO, f"{name} cad[{integration.extra}] {release}, made on first need in "
                                    f"{_home(folder)}: the first command that needs it"))
        return lines
    except Exception as error:  # noqa: BLE001 - a report line, never a reason for the report to fail
        return [(WARNING, f"extras unknown ({type(error).__name__}: {error})")]


if __name__ == "__main__":
    raise SystemExit(main())
