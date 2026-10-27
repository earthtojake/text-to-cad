"""The installations of cadgen this user has, and the one ``cadgen`` command that runs them.

A skill runs cadgen in the agent's shell, and that shell is often a sandbox that lets a command
read and execute anything but write only to its working folder and the temporary folder. ``uvx``
cannot start in one: uv writes its cache before it does anything else. The environment uv built
starts fine there. So each installation registers itself, and one command runs whichever the
caller names:

- ``<state>/installations/<version>.json``, the installation's record: ``version``, the absolute
  paths of its ``python`` and its ``cadgen`` console script, its environment (``prefix``) and when
  it registered (``registered``). The state folder's ``Folder`` (``cadgen.engine.registry``) writes
  it, as it writes everything there.
- ``~/.local/bin/cadgen`` (``CADGEN_LAUNCHER_DIR`` moves the folder), the proxy: a short ``sh``
  script that runs the installation registered last with ``-m cadgen._internal.proxy``, which picks
  the installation the command names (``cadgen +0.8.0 ...``) or the one running, and runs its
  ``cadgen`` or, for ``cadgen run``, its ``python``. Every version writes the same file
  (``REVISION``), so the proxy is no installation's. On Windows it is ``cadgen.cmd``, the same logic.

Both are written at install moments only, in two places: the CAD app's server (``cadgen mcp``) as it
starts (:func:`startup`), which the host does outside any sandbox at the moment it installs or
updates the plugin, and ``cadgen doctor``, the skills' one-time step, which says what it found. A
folder either cannot write (a sandbox's) is skipped, silently by the server and said by ``doctor``.
No other command writes either. A file named ``cadgen`` there that is not the proxy (``uv tool
install``'s link) is left alone, and said. ``cadgen doctor --prune`` removes the records whose
interpreter is gone.

An editable install (a checkout's environment) registers nothing by itself: it reports the release's
version, and its record would take a user's place. A development install names its own
(``CADGEN_INSTALLATION_VERSION``), which the ``cadgen`` command sets for it as it runs it
(``named``, ``cadgen._internal.proxy``).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

DIR_ENV = "CADGEN_LAUNCHER_DIR"
NAME_ENV = "CADGEN_INSTALLATION_VERSION"
FOLDER = "installations"
WINDOWS = os.name == "nt"
# The line that makes a file the proxy, and the proxy's revision: a later one is never replaced by an
# earlier, so an older installation's server starting never undoes a newer one's proxy.
MARK = "cadgen proxy: "
REVISION = 3
VERSION = re.compile(r"[0-9][0-9A-Za-z.+_-]*")
# A release's version, as a wheel reports it of itself (``cadgen.__version__``). Any other version a
# record names -- a development install's ``<version>-dev.<time>``, a source tree's -- is a name the
# installation cannot know by itself: the ``cadgen`` command gives it (``named``).
RELEASE = re.compile(r"[0-9]+(\.[0-9]+)*((a|b|rc)[0-9]+)?(\.post[0-9]+)?")

OK = "ok"
MISSING = "missing"
STALE = "stale"  # the proxy, of an earlier revision or changed
NEWER = "newer"  # the proxy of a later revision: left alone
FOREIGN = "foreign"  # a file of that name that cadgen did not write: left alone
REGISTERED = "registered"


def proxy_folder() -> str:
    """uv's user bin folder, ``~/.local/bin`` (``%USERPROFILE%\\.local\\bin`` on Windows)."""
    return os.environ.get(DIR_ENV) or os.path.join(os.path.expanduser("~"), ".local", "bin")


def proxy_path(where: str | None = None, windows: bool = WINDOWS) -> str:
    return os.path.join(where or proxy_folder(), "cadgen.cmd" if windows else "cadgen")


def state():
    """The user's state folder (``cadgen.viewer.recents.state_dir``), as its ``Folder``."""
    from cadgen.engine.registry import Folder
    from cadgen.viewer.recents import state_dir

    return Folder(state_dir())


def targets() -> tuple[str, str, str] | None:
    """This installation's console script, python and environment, or ``None`` without a console
    script. The python is the environment's own path, never resolved: resolving it reaches the base
    interpreter, which is not this environment."""
    if sys.prefix != sys.base_prefix:
        scripts = os.path.join(sys.prefix, "Scripts" if WINDOWS else "bin")
        python = os.path.join(scripts, "python.exe" if WINDOWS else "python")
        if not os.path.isfile(python):
            python = sys.executable
    else:  # not a virtual environment: rare, and sysconfig costs a few milliseconds
        import sysconfig

        scripts = sysconfig.get_path("scripts")
        python = sys.executable
    console = os.path.join(scripts, "cadgen.exe" if WINDOWS else "cadgen")
    if not (python and os.path.isfile(console)):
        return None
    return os.path.abspath(console), os.path.abspath(python), os.path.abspath(sys.prefix)


def editable() -> bool:
    """Whether this cadgen is imported from outside its environment: a checkout's source tree
    (an editable install, or a path on ``PYTHONPATH``). A string compare, no metadata read."""
    import cadgen

    here = os.path.normcase(os.path.abspath(os.path.dirname(cadgen.__file__)))
    prefix = os.path.normcase(os.path.abspath(sys.prefix))
    return not here.startswith(prefix.rstrip(os.sep) + os.sep)


def own_version() -> str | None:
    """The version this installation registers as: a development install's own name, else the
    version its environment is registered as (``cadgen.engine.daemon.installation``, the name its
    client, engine and workers go by), else the installed version -- or ``None`` for a source tree
    never registered, which registers nothing by itself."""
    named = os.environ.get(NAME_ENV)
    if named:
        return named if VERSION.fullmatch(named) else None
    from cadgen.engine import daemon
    from cadgen.engine.previous import version

    found = daemon._registered(str(state().root), os.path.normcase(os.path.realpath(sys.prefix)), version())
    if found:
        return found
    if editable():
        return None
    from cadgen import __version__

    return __version__


def _inside(version: str) -> str:
    if not VERSION.fullmatch(version or ""):
        raise ValueError(f"not a cadgen version: {version!r}")
    return f"{FOLDER}/{version}.json"


def _parse(data: bytes | None) -> dict | None:
    try:
        record = json.loads(data) if data is not None else None
    except ValueError:
        return None
    if not isinstance(record, dict) or not all(isinstance(record.get(key), str)
                                               for key in ("version", "python", "cadgen", "prefix")):
        return None
    return record


def register(version: str, found: tuple[str, str, str] | None = None, folder=None) -> tuple[str, str]:
    """Write the record of this installation as ``version``: ``(path, status)``, ``REGISTERED`` or
    ``OK`` when the record already names it. ``OSError`` when the state folder cannot be written."""
    folder = folder or state()
    found = found or targets()
    inside = _inside(version)
    path = str(folder.path(inside))
    if found is None:
        raise OSError(f"this cadgen has no console script to register ({sys.prefix})")
    console, python, prefix = found
    before = _parse(folder.read(inside))
    if before and (before["cadgen"], before["python"], before["prefix"]) == (console, python, prefix):
        return path, OK
    record = {"version": version, "python": python, "cadgen": console, "prefix": prefix,
              "registered": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    # One key a line, the python's alone: the proxy's sh reads that line (``script``).
    text = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    folder.write(inside, text.encode("utf-8"))
    # An environment holds one cadgen: the record of another version in it (an upgrade in place,
    # ``pip install -U``, ``uv tool upgrade``) names code that is gone, and would run this one as it.
    for other in records(folder):
        if other["version"] != version and _same_place(other["prefix"], prefix):
            folder.remove(_inside(other["version"]))
    _forget_read()
    return path, REGISTERED


def _forget_read() -> None:
    """The records changed in this process: the version its environment is registered as
    (``cadgen.engine.daemon.registered``, read once per process) is read again."""
    from cadgen.engine import daemon

    daemon._registered.cache_clear()


def _same_place(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def records(folder=None) -> list[dict]:
    """Every installation's record, each with its file (``path``)."""
    folder = folder or state()
    found = []
    for name in folder.names(FOLDER):
        if name.endswith(".json") and VERSION.fullmatch(name[:-5]):
            record = _parse(folder.read(f"{FOLDER}/{name}"))
            if record is not None and record["version"] == name[:-5]:
                found.append({**record, "path": str(folder.path(f"{FOLDER}/{name}"))})
    return found


def named(record: dict) -> str | None:
    """The version the ``cadgen`` command tells the installation of ``record`` it runs as
    (``NAME_ENV``): a development or source registration's, which it cannot know by itself (it
    reports its release's); None for a release, which knows."""
    return None if RELEASE.fullmatch(record["version"]) else record["version"]


def alive(record: dict) -> bool:
    return os.path.isfile(record["python"]) and os.path.isfile(record["cadgen"])


def here(folder=None) -> dict | None:
    """The record the ``cadgen`` command runs this installation by: one naming this environment
    (``sys.prefix``) whose interpreter and console script are there (``alive``) -- the version it runs as
    (``cadgen.engine.daemon.installation``) where that one is, else the one registered last. ``None`` for an
    installation no record names."""
    mine = [record for record in records(folder) if _same_place(record["prefix"], sys.prefix) and alive(record)]
    if not mine:
        return None
    from cadgen.engine.daemon import installation

    running = installation()
    return next((record for record in mine if record["version"] == running), None) \
        or max(mine, key=lambda record: str(record.get("registered") or ""))


def prune(folder=None) -> list[str]:
    """Remove every record whose interpreter is gone; return their files."""
    folder = folder or state()
    removed = []
    for record in records(folder):
        if not alive(record):
            folder.remove(_inside(record["version"]))
            removed.append(record["path"])
    _forget_read()
    return removed


# The per-version launchers an earlier 0.8 build published beside the proxy: ``cadgen-<version>``
# (a symlink to an environment's console script; on Windows a copy, ``.exe``) and
# ``cadgen-python-<version>`` (a script whose first lines carry ``LEGACY_MARK``).
LEGACY_MARK = "cadgen launcher: "


def _legacy_python(path: str) -> bool:
    """Whether ``path`` is a python launcher an earlier build wrote: it carries ``LEGACY_MARK``."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(4096)
    except (OSError, ValueError):
        return False
    return any(LEGACY_MARK in line for line in head.splitlines()[:3])


def _legacy_console(path: str) -> bool:
    """Whether ``path`` is a console launcher an earlier build wrote: a symlink, even a dangling
    one, to a cadgen environment's console script (``.../bin/cadgen``)."""
    if not os.path.islink(path):
        return False
    try:
        target = os.readlink(path)
    except OSError:
        return False
    parts = target.replace("\\", "/").rstrip("/").split("/")
    return parts[-1:] == ["cadgen"] and parts[-2:-1] == ["bin"]


def _registered_environment(path: str) -> bool:
    """Whether the symlink ``path`` leads into the environment of a registered installation."""
    place = os.path.dirname(os.path.dirname(os.path.realpath(path)))
    try:
        return any(_same_place(record["prefix"], place) for record in records())
    except OSError:
        return False


def prune_legacy(where: str | None = None, windows: bool = WINDOWS) -> list[str]:
    """Remove the per-version launchers earlier 0.8 builds published in the proxy's folder (``where``):
    each ``cadgen-python-<version>`` carrying ``LEGACY_MARK``, and each ``cadgen-<version>`` symlink
    into a cadgen environment (on Windows the ``.exe`` copy beside a marked ``.cmd``). Anything else
    there -- the proxy, another program's file -- is left alone. The paths removed."""
    folder = where or proxy_folder()
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    marked = set()
    for name in names:
        stem = name[:-4] if windows and name.lower().endswith(".cmd") else name
        if stem.startswith("cadgen-python-") and VERSION.fullmatch(stem[len("cadgen-python-"):]) \
                and _legacy_python(os.path.join(folder, name)):
            marked.add(stem[len("cadgen-python-"):])
    removed = []
    for name in names:
        path = os.path.join(folder, name)
        stem = name[:-4] if windows and name.lower().endswith((".cmd", ".exe")) else name
        if stem.startswith("cadgen-python-"):
            legacy = stem[len("cadgen-python-"):] in marked
        elif stem.startswith("cadgen-") and VERSION.fullmatch(stem[len("cadgen-"):]):
            version = stem[len("cadgen-"):]
            # A symlink into a cadgen environment is an earlier build's only beside its marked python,
            # or pointing nowhere now, or into an environment registered here: a person's own
            # ``cadgen-0.7`` into a venv of theirs is theirs.
            legacy = (_legacy_console(path) and (version in marked or not os.path.exists(path)
                                                 or _registered_environment(path))) \
                or (windows and name.lower().endswith(".exe") and version in marked)
        else:
            legacy = False
        if legacy:
            try:
                os.remove(path)
            except OSError:
                continue
            removed.append(path)
    return removed


def forget(version: str, folder=None) -> None:
    """Remove the record of ``version`` (a development install's, as it is taken out)."""
    (folder or state()).remove(_inside(version))
    _forget_read()


# --- the proxy --------------------------------------------------------------------------------

_SH = """#!/bin/sh
# {mark}{revision}
# The cadgen command: runs the installation of cadgen that `+<version>`, CADGEN_VERSION or
# a running engine names (cadgen._internal.proxy), through the one registered last.
# Every cadgen writes this same file as it registers (cadgen doctor, the CAD app's server).
if [ -n "$CADGEN_STATE_DIR" ]; then state=$CADGEN_STATE_DIR
elif [ "$(uname -s)" = Darwin ]; then state="$HOME/Library/Application Support/cadgen"
else state="${{XDG_STATE_HOME:-$HOME/.local/state}}/cadgen"
fi
for name in $(CDPATH= cd "$state/installations" 2>/dev/null && ls -t -- *.json 2>/dev/null); do
  record="$state/installations/$name"
  python=$(sed -n 's/^ *"python": "\\(.*\\)",\\{{0,1\\}}$/\\1/p' "$record")
  console=$(sed -n 's/^ *"cadgen": "\\(.*\\)",\\{{0,1\\}}$/\\1/p' "$record")
  # Alive as ``alive`` says it: its python and its console script (an uninstalled cadgen leaves the python).
  [ -x "$python" ] && [ -f "$console" ] && exec "$python" -P -m cadgen._internal.proxy "$@"
done
case $1 in +?*) version=${{1#+}} ;; *) version= ;; esac
echo "cadgen${{version:+ $version}} is not installed: run \\`uvx --no-config --managed-python --python 3.13 \\
--from cadgen${{version:+==$version}} cadgen doctor\\` once, outside any sandbox or with its permission" >&2
exit 1
"""

_CMD = """@echo off\r
rem {mark}{revision}\r
rem The cadgen command: runs the installation of cadgen that +<version>, CADGEN_VERSION or\r
rem a running engine names (cadgen._internal.proxy), through the one registered last.\r
setlocal EnableDelayedExpansion\r
if defined CADGEN_STATE_DIR (set "state=!CADGEN_STATE_DIR!") else if defined LOCALAPPDATA (set "state=!LOCALAPPDATA!\\cadgen-state") else (set "state=!USERPROFILE!\\AppData\\Local\\cadgen-state")\r
rem A record's python and cadgen lines are: space "KEY": "PATH", -- split at each quote, PATH is the\r
rem fourth piece. Alive as alive() says it: its python and its console script (an uninstalled cadgen\r
rem leaves the python), else the next record.\r
for /f "delims=" %%n in ('dir /b /o-d "!state!\\installations\\*.json" 2^>nul') do (\r
  set "python="\r
  set "console="\r
  for /f usebackq^ tokens^=4^ delims^=^" %%p in (`findstr /c:"\\"python\\":" "!state!\\installations\\%%n"`) do set "python=%%p"\r
  for /f usebackq^ tokens^=4^ delims^=^" %%c in (`findstr /c:"\\"cadgen\\":" "!state!\\installations\\%%n"`) do set "console=%%c"\r
  if defined python if defined console (\r
    set "python=!python:\\\\=\\!"\r
    set "console=!console:\\\\=\\!"\r
    if exist "!python!" if exist "!console!" goto run\r
  )\r
)\r
echo cadgen is not installed: run `uvx --no-config --managed-python --python 3.13 --from cadgen cadgen doctor` once, outside any sandbox or with its permission 1>&2\r
exit /b 1\r
:run\r
endlocal & "%python%" -P -m cadgen._internal.proxy %*\r
exit /b %errorlevel%\r
"""


def script(windows: bool = WINDOWS) -> str:
    """The proxy's text: the same from every version of this revision."""
    return (_CMD if windows else _SH).format(mark=MARK, revision=REVISION)


def _revision(path: str) -> int | None:
    """The revision of the proxy at ``path``, or ``None`` when it is not the proxy."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(512)
    except (OSError, ValueError):
        return None
    for line in head.splitlines()[:3]:
        at = line.find(MARK)
        if at >= 0:
            try:
                return int(line[at + len(MARK):].strip())
            except ValueError:
                return None
    return None


def proxy_status(path: str | None = None, windows: bool = WINDOWS) -> str:
    path = path or proxy_path(windows=windows)
    if not os.path.lexists(path):
        return MISSING
    revision = None if os.path.islink(path) else _revision(path)
    if revision is None:
        return FOREIGN
    if revision > REVISION:
        return NEWER
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            same = handle.read() == script(windows)
    except OSError:
        same = False
    return OK if same else STALE


def write_proxy(where: str | None = None, windows: bool = WINDOWS) -> tuple[str, str, str | None]:
    """Write the proxy when it is missing or stale: ``(path, status before, error or None)``. A
    folder it cannot write is not raised but returned as the error, for ``cadgen doctor`` to say."""
    where = where or proxy_folder()
    path = proxy_path(where, windows)
    status = proxy_status(path, windows)
    if status not in (MISSING, STALE):
        return path, status, None
    from cadgen._internal.atomic_replace import replace_atomic, temp_suffix

    temporary = f"{path}{temp_suffix()}"
    try:
        os.makedirs(where, exist_ok=True)
        with open(temporary, "w", encoding="utf-8", newline="") as handle:
            handle.write(script(windows))
        os.chmod(temporary, 0o755)
        replace_atomic(temporary, path)
    except OSError as failure:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        return path, status, f"{type(failure).__name__}: {failure.strerror or failure}"
    return path, status, None


def setup(version: str) -> tuple[tuple[str, str, str | None], tuple[str, str, str | None]]:
    """Register this installation as ``version`` and write the proxy: each ``(path, status, error)``."""
    try:
        path, status = register(version)
        registered: tuple[str, str, str | None] = (path, status, None)
    except (OSError, ValueError) as failure:
        try:
            where = str(state().path(_inside(version)))
        except (OSError, ValueError):
            where = version
        registered = (where, MISSING, f"{type(failure).__name__}: {getattr(failure, 'strerror', None) or failure}")
    return registered, write_proxy()


def startup() -> None:
    """As the CAD app's server starts: register this installation and write the proxy, silently."""
    try:
        version = own_version()
        if version:
            setup(version)
    except Exception:  # noqa: BLE001 - a registration never fails the server it rides on
        pass
