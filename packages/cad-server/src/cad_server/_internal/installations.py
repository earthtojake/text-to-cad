"""The installations of text-to-cad this user has, the one of them that is ``current``, and the one
``cad`` command that runs it.

A skill runs the ``cad`` command in the agent's shell, and that shell is often a sandbox that lets a command
read and execute anything but write only to its working folder and the temporary folder. ``uvx``
cannot start in one: uv writes its cache before it does anything else. The environment uv built
starts fine there. So an installation registers itself, and one command runs the current one:

- ``<state>/installations/<version>.json``, the installation's record: ``version``, the absolute
  paths of its ``python`` and of its console script (``cad``), its environment (``prefix``) and
  when it registered (``registered``). The state folder's ``Folder`` (``cad_server.engine.registry``) writes
  it, as it writes everything there.
- ``<state>/installations/current``, the version of the installation that is the device's for a client of
  0.11.10 and earlier: its engine is the one such a client starts or attaches to. From the first pinned release it is the mirror of
  the default channel's pointer (``cad_server._internal.pointers.mirror``), written with it by every move of the
  default channel (``cad setup``, ``cad update``, the install command run again); a client of 0.11.10 or earlier
  that finds none -- no installation before it -- points it at itself once (``bootstrap``).
- ``~/.local/bin/cad`` (``CAD_LAUNCHER_DIR`` moves the folder), the proxy -- the ``cad`` command --, a short
  ``sh`` script every future version is run through, so what it does is small and kept stable. It reads only
  the first argument. A pin, ``cad +<version>[@<channel>] ...``, runs that version's own ``cad`` (its code
  marker, ``versions/<version>/code/cad-version.json``, names it) with the whole command line, which reads the pin
  (``cad_server._internal.pins``); a version not installed is installed by its own release first (``uvx ...
  --from cad-server==<version> cad setup --add --quiet``), unless its channel's pointer names a newer one already
  (stale: said, nothing installed); and it never runs another version for a pin. With no pin, the default
  channel's version (``pointers.default``'s rule): its pointer; else, where the install command has run, the
  installation the layout of 0.11.10 and earlier names current, run as that layout's command ran it (``python -m
  cad_server._internal.proxy``); else the newest version installed. Every version writes the same file
  (``REVISION``), so the proxy is no installation's, and one of an earlier revision never replaces one of a later.
  On Windows it is ``cad.exe``, the same logic in Python, run by a Python of its own beside it
  (``cad-launcher``): see "the Windows command" below.

The records and the proxy are written at install moments only: ``cad setup`` (the release it
sets up), ``cad setup --add`` (the proxy alone, ``versions.add``), ``cad doctor``, the skills' one-time step, which
says what it found, and the CAD app's
server (``cad-mcp``) as it starts (:func:`startup`), which the host does outside any sandbox:
that one writes the proxy, and registers itself only where no installation is current. A folder
either cannot write (a sandbox's) is skipped, silently by the server and said by ``doctor``. No
other command writes either. A file named ``cadgen`` there that is not the proxy (``uv tool
install``'s link) is left alone, and said. ``cad doctor --prune`` removes the records whose
interpreter is gone.

An editable install (a checkout's environment) registers nothing by itself: it reports the release's
version, and its record would take a user's place. A development install names its own
(``CAD_INSTALLATION_VERSION``), which the ``cad`` command sets for it as it runs it
(``named``, ``cad_server._internal.proxy``).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from cad.engine.places import VERSION, alive, installation_record

DIR_ENV = "CAD_LAUNCHER_DIR"
NAME_ENV = "CAD_INSTALLATION_VERSION"
FOLDER = "installations"  # ``cad.engine.places.INSTALLATIONS``, which clients read
WINDOWS = os.name == "nt"
# The line that makes a file the proxy, and the proxy's revision: a later one is never replaced by an
# earlier, so an older installation's server starting never undoes a newer one's proxy. 8: its line with
# no installation names cad-server. 9: the cmd reads a record whose paths are not ASCII. 10: the cmd reads
# the state folder in the user's own folder, out of the local application data (``cad.engine.places``).
# 11: on Windows, cad.exe and a Python of its own in place of cad.cmd, a batch file (the sh is 9's). 12: the pin,
# ``cad +<version>[@<channel>]``, and the versions in their own folders (``versions``, ``pointers``).
MARK = "cad proxy: "
REVISION = 12
# The file that names the current installation's version, in the state folder.
CURRENT = f"{FOLDER}/current"
# A release's version, as a wheel reports it of itself (``cad_server.__version__``). Any other version a
# record names -- a development install's ``<version>-dev.<time>``, a source tree's -- is a name the
# installation cannot know by itself: the ``cad`` command gives it (``named``).
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
    return os.path.join(where or proxy_folder(), EXE if windows else "cad")


def state():
    """The user's state folder (``cad.engine.places.state_dir``), as its ``Folder``."""
    from cad_server.engine.registry import Folder
    from cad.engine.places import state_dir

    return Folder(state_dir())


def packaged() -> str | None:
    """The Windows app package this process runs inside, by its full name, else None. Every process an
    MSIX-packaged app starts (the Claude desktop app's shell among them) inherits its package, and what it
    creates under ``AppData`` Windows writes into the package's own ``LocalCache`` instead, which only that
    app's processes see. CAD keeps its own folders out of it (``cad.engine.places``), but uv installs its
    Python there: a first install made inside a package is one no terminal and no other app can run."""
    if not WINDOWS:
        return None
    import ctypes

    try:
        current = ctypes.windll.kernel32.GetCurrentPackageFullName
    except (AttributeError, OSError):
        return None
    length = ctypes.c_uint32(0)
    # ERROR_INSUFFICIENT_BUFFER (122) asks for the name's length; APPMODEL_ERROR_NO_PACKAGE, not packaged.
    if current(ctypes.byref(length), None) != 122:
        return None
    name = ctypes.create_unicode_buffer(length.value)
    return (name.value or None) if current(ctypes.byref(length), name) == 0 else None


def packaged_words(package: str) -> str:
    """What ``cad setup`` says of a first install made inside ``package``."""
    return (f"this shell runs inside the Windows app package {package}, which keeps what it installs under "
            "AppData, uv's Python among it, to itself: no terminal and no other agent app could run it")


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
    console = os.path.join(scripts, "cad.exe" if WINDOWS else "cad")
    if not (python and os.path.isfile(console)):
        return None
    return os.path.abspath(console), os.path.abspath(python), os.path.abspath(sys.prefix)


def editable() -> bool:
    """Whether this text-to-cad is imported from outside its environment: a checkout's source tree
    (an editable install, or a path on ``PYTHONPATH``). A string compare, no metadata read."""
    import cad_server

    here = os.path.normcase(os.path.abspath(os.path.dirname(cad_server.__file__)))
    prefix = os.path.normcase(os.path.abspath(sys.prefix))
    return not here.startswith(prefix.rstrip(os.sep) + os.sep)


def own_version() -> str | None:
    """The version this installation registers as: a development install's own name, else the
    version its environment is registered as (``cad.engine.places.installation``, the name its
    client, engine and workers go by), else the installed version -- or ``None`` for a source tree
    never registered, which registers nothing by itself."""
    named = os.environ.get(NAME_ENV)
    if named:
        return named if VERSION.fullmatch(named) else None
    from cad.engine import places
    from cad.engine.previous import version

    found = places._registered(str(state().root), os.path.normcase(os.path.realpath(sys.prefix)), version())
    if found:
        return found
    if editable():
        return None
    from cad_server import __version__

    return __version__


def _inside(version: str) -> str:
    if not VERSION.fullmatch(version or ""):
        raise ValueError(f"not a version: {version!r}")
    return f"{FOLDER}/{version}.json"


def register(version: str, found: tuple[str, str, str] | None = None, folder=None) -> tuple[str, str]:
    """Write the record of this installation as ``version``: ``(path, status)``, ``REGISTERED`` or
    ``OK`` when the record already names it. ``OSError`` when the state folder cannot be written."""
    folder = folder or state()
    found = found or targets()
    inside = _inside(version)
    path = str(folder.path(inside))
    if found is None:
        raise OSError(f"this installation has no console script to register ({sys.prefix})")
    console, python, prefix = found
    before = installation_record(folder.read(inside))
    if before and (before["cad"], before["python"], before["prefix"]) == (console, python, prefix):
        return path, OK
    record = {"version": version, "python": python, "cad": console, "prefix": prefix,
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


def registration(version: str, found: tuple[str, str, str] | None = None, folder=None) -> tuple[str, str]:
    """What ``register`` would find, read and nothing written (``cad doctor --check``): ``(path, OK)`` when
    the record of ``version`` names this installation as it is, else ``(path, MISSING)``, which ``register``
    writes."""
    folder = folder or state()
    found = found or targets()
    inside = _inside(version)
    before = installation_record(folder.read(inside))
    named = found is not None and before and (before["cad"], before["python"], before["prefix"]) == tuple(found)
    return str(folder.path(inside)), OK if named else MISSING


def _forget_read() -> None:
    """The records changed in this process: the version its environment is registered as
    (``cad.engine.places.registered``, read once per process), and the version it belongs to
    (``places.versioned``), are read again."""
    from cad.engine import places

    places._registered.cache_clear()
    places._versioned.cache_clear()


def _same_place(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def records(folder=None) -> list[dict]:
    """Every installation's record, each with its file (``path``)."""
    folder = folder or state()
    found = []
    for name in folder.names(FOLDER):
        if name.endswith(".json") and VERSION.fullmatch(name[:-5]):
            record = installation_record(folder.read(f"{FOLDER}/{name}"))
            if record is not None and record["version"] == name[:-5]:
                found.append({**record, "path": str(folder.path(f"{FOLDER}/{name}"))})
    return found


def named(record: dict) -> str | None:
    """The version the ``cad`` command tells the installation of ``record`` it runs as
    (``NAME_ENV``): a development or source registration's, which it cannot know by itself (it
    reports its release's); None for a release, which knows."""
    return None if RELEASE.fullmatch(record["version"]) else record["version"]


def here(folder=None) -> dict | None:
    """The record the ``cad`` command runs this installation by: one naming this environment
    (``sys.prefix``) whose interpreter and console script are there (``alive``) -- the version it runs as
    (``cad.engine.places.installation``) where that one is, else the one registered last. ``None`` for an
    installation no record names."""
    mine = [record for record in records(folder) if _same_place(record["prefix"], sys.prefix) and alive(record)]
    if not mine:
        return None
    from cad.engine.places import installation

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
# 0.8's proxy, ``cadgen`` (``cadgen.cmd``), which the ``cad`` command replaces.
EARLIER_PROXY, EARLIER_MARK = "cadgen", "cadgen proxy: "
# The key 0.8's installation records name their console script by (this release's say ``cad``).
EARLIER_CONSOLE = "cadgen"


def appdata() -> list[dict]:
    """0.10.0's installations on Windows, each by its record in the state folder it kept in the local
    application data (``cad.engine.places.appdata_state_dir``), as ``earlier`` reads 0.8's: read only so
    ``cad setup`` stops the engine 0.10.0 runs from there by its own ``cad stop``, once."""
    from cad.engine.places import appdata_state_dir

    folder = appdata_state_dir()
    return earlier(folder, console="cad") if folder is not None else []


def earlier(folder: Path | None = None, console: str = EARLIER_CONSOLE) -> list[dict]:
    """0.8's installations, each by its record where 0.8 left it: ``installations/<version>.json`` in 0.8's
    state folder (``folder``; by default where what 0.8 left is looked for,
    ``cad.engine.places.earlier_state_dir``), its ``version``, ``python``, console script
    (``EARLIER_CONSOLE``) and environment (``prefix``), with its file (``path``). No record of this
    release's is one. Read only to clean 0.8 up: ``cad setup`` stops 0.8's server by 0.8's own stop, and
    ``cad doctor --prune`` takes out the launchers 0.8 published (``prune_legacy``)."""
    from cad.engine.places import earlier_state_dir

    where = Path(folder or earlier_state_dir()) / FOLDER
    try:
        names = sorted(os.listdir(where))
    except OSError:
        return []
    found = []
    for name in names:
        if not (name.endswith(".json") and VERSION.fullmatch(name[:-5])):
            continue
        try:
            record = json.loads((where / name).read_bytes())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get("version") == name[:-5] and all(
                isinstance(record.get(key), str) for key in ("python", console, "prefix")):
            found.append({**record, "path": str(where / name)})
    return found


def _marked(path: str, mark: str) -> bool:
    """Whether ``path`` is a file whose first lines carry ``mark``: a launcher of ours."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(4096)
    except (OSError, ValueError):
        return False
    return any(mark in line for line in head.splitlines()[:3])


def _legacy_python(path: str) -> bool:
    """Whether ``path`` is a python launcher an earlier build wrote: it carries ``LEGACY_MARK``."""
    return _marked(path, LEGACY_MARK)


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
    """Whether the symlink ``path`` leads into the environment of an installation 0.8 registered (``earlier``)."""
    place = os.path.dirname(os.path.dirname(os.path.realpath(path)))
    return any(_same_place(record["prefix"], place) for record in earlier())


def prune_legacy(where: str | None = None, windows: bool = WINDOWS) -> list[str]:
    """Remove the launchers earlier releases published in the proxy's folder (``where``): those
    ``legacy_launchers`` finds. The paths removed."""
    removed = []
    for path in legacy_launchers(where, windows):
        try:
            os.remove(path)
        except OSError:
            continue
        removed.append(path)
    return removed


def legacy_launchers(where: str | None = None, windows: bool = WINDOWS) -> list[str]:
    """The launchers earlier releases published in the proxy's folder (``where``), read and none removed:
    0.8's proxy, ``cadgen`` carrying ``EARLIER_MARK``, each ``cadgen-python-<version>`` carrying
    ``LEGACY_MARK``, and each ``cadgen-<version>`` symlink into a cadgen environment (on Windows the ``.exe``
    copy beside a marked ``.cmd``). Anything else there -- the proxy, another program's file -- is not one."""
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
    found = []
    for name in names:
        path = os.path.join(folder, name)
        stem = name[:-4] if windows and name.lower().endswith((".cmd", ".exe")) else name
        if stem == EARLIER_PROXY and (name.lower().endswith(".cmd") if windows else name == stem):
            legacy = not os.path.islink(path) and _marked(path, EARLIER_MARK)
        elif stem.startswith("cadgen-python-"):
            legacy = stem[len("cadgen-python-"):] in marked
        elif stem.startswith("cadgen-") and VERSION.fullmatch(stem[len("cadgen-"):]):
            version = stem[len("cadgen-"):]
            # A symlink into a cadgen environment is an earlier build's only beside its marked python,
            # or pointing nowhere now, or into an environment 0.8 registered: a person's own
            # ``cadgen-0.7`` into a venv of theirs is theirs.
            legacy = (_legacy_console(path) and (version in marked or not os.path.exists(path)
                                                 or _registered_environment(path))) \
                or (windows and name.lower().endswith(".exe") and version in marked)
        else:
            legacy = False
        if legacy:
            found.append(path)
    return found


def forget(version: str, folder=None) -> None:
    """Remove the record of ``version`` (a development install's, as it is taken out)."""
    (folder or state()).remove(_inside(version))
    _forget_read()


# --- current ----------------------------------------------------------------------------------


def current_version(folder=None) -> str | None:
    """The version ``current`` names, whether or not its installation is there, or None."""
    data = (folder or state()).read(CURRENT)
    named = data.decode("utf-8", "replace").strip() if data is not None else ""
    return named if VERSION.fullmatch(named) else None


def current(folder=None) -> dict | None:
    """The current installation's record, while its interpreter and console script are there
    (``alive``): the one every client's engine is (``cad.engine.client``). None with none current,
    or one that is gone (its folder removed, uv's cache cleaned): a client then points ``current`` at
    itself (``bootstrap``)."""
    folder = folder or state()
    version = current_version(folder)
    if version is None:
        return None
    record = installation_record(folder.read(_inside(version)))
    if record is None or record["version"] != version or not alive(record):
        return None
    return {**record, "path": str(folder.path(_inside(version)))}


def point(version: str, folder=None) -> None:
    """``current`` pointed at ``version`` (registered), replaced whole: a reader sees the one before or this
    one. The file is the version alone, no line end: ``cmd``'s ``set /p`` reads it as it is."""
    folder = folder or state()
    _inside(version)  # a version, or ValueError
    folder.write(CURRENT, version.encode("utf-8"))


def unregistered() -> str:
    """Why a client of this installation's starts no engine -- no installation is current, and it runs in
    no base an installation made (``cad.engine.client._start``) -- in the words a process of cad-server's
    own says it in (``cad.engine.said.UNREGISTERED``): what is true of this installation, and the command
    that registers it, ``cad doctor``. One its records name but none is current is made current by it; a
    source tree registers only as a version it is named (``NAME_ENV``)."""
    from cad_server._internal.launch import COMMAND, SERVER

    if here() is not None:
        return (f"no {SERVER} is current on this computer: run `{COMMAND} doctor` once, which makes this one "
                "current, then run this again")
    if own_version() is None:
        from cad.engine.previous import version

        return (f"this {SERVER} is a source tree, which registers only as a version it is named: run "
                f"`{COMMAND} doctor` once with {NAME_ENV}={version()}-dev.0 set, then run this again")
    return (f"this {SERVER} is not registered on this computer: run `{COMMAND} doctor` once, which registers it, "
            "then run this again")


def mine(record: dict | None) -> bool:
    """Whether ``record`` names this process's own installation (its environment, as it registers it)."""
    if record is None:
        return False
    found = targets()
    return _same_place(record["prefix"], found[2] if found is not None else sys.prefix)


def bootstrap(version: str, folder=None) -> bool:
    """``current`` pointed at ``version`` (this installation, registered) when no live installation is
    current: the first client on a device makes its own installation the device's, once. Whether it did."""
    folder = folder or state()
    if current(folder) is not None:
        return False
    point(version, folder)
    return True


# --- the proxy --------------------------------------------------------------------------------

_SH = """#!/bin/sh
# {mark}{revision}
# The cad command. `cad +<version>[@<channel>] ...` runs that version of text-to-cad and no other: its own cad,
# which reads the pin. A version not installed is installed first, by its own release, unless its channel is
# on a newer one already. With no pin: the default channel's version. Every release with pinned commands writes this
# same
# file (cad setup, cad setup --add, cad doctor); a release whose revision is older never replaces it.
if [ -n "$CAD_STATE_DIR" ]; then state=$CAD_STATE_DIR
elif [ "$(uname -s)" = Darwin ]; then state="$HOME/Library/Application Support/cad"
else state="${{XDG_STATE_HOME:-$HOME/.local/state}}/cad"
fi
say() {{ printf 'cad: %s\\n' "$1" >&2; exit "$2"; }}
# Whether version $1 is installed: its code marker, written last, and its Python and cad: a release's where every
# release puts them, so no path is parsed; a development version's as its marker names them (a key a line, JSON's
# escapes undone).
present() {{
  [ -f "$state/versions/$1/code/cad-version.json" ] || return 1
  case $1 in
  *[!0-9.abcoprst]*)
    python=$(record python "$state/versions/$1/code/cad-version.json")
    cad=$(record cad "$state/versions/$1/code/cad-version.json") ;;
  *)
    python=$state/versions/$1/code/server/bin/python
    cad=$state/versions/$1/code/server/bin/cad ;;
  esac
  [ -x "$python" ] && [ -f "$cad" ]
}}
# The path key $1 of the record $2 names (a key a line), its JSON escapes undone.
record() {{
  sed -n 's/^ *"'"$1"'": "\\(.*\\)",\\{{0,1\\}}$/\\1/p' "$2" 2>/dev/null | sed 's/\\\\\\(.\\)/\\1/g'
}}
# Version $1, as present found it, run with the arguments after it: a name of characters no release has (a
# development build's) told to it, which its code cannot know; none told to a release.
run() {{
  case $1 in
  *[!0-9.abcoprst]*) CAD_INSTALLATION_VERSION=$1; export CAD_INSTALLATION_VERSION ;;
  *) unset CAD_INSTALLATION_VERSION ;;
  esac
  shift
  exec "$python" "$cad" "$@"
}}
# Whether version $1 is older than version $2, as the versions order them (versions.order) for the names releases and
# development builds have: their release numbers, then a development build (-dev.<stamp>) after its release, by its
# stamp (a tie is not older).
older() {{
  awk -v a="$1" -v b="$2" 'function n(v) {{ sub(/[^0-9.].*/, "", v); return v }}
function d(v) {{ if (match(v, /-dev\\.[0-9]+$/)) return substr(v, RSTART + 5) + 0; return -1 }}
BEGIN {{ x = split(n(a), p, "."); y = split(n(b), q, ".")
  for (i = 1; i <= x || i <= y; i++) {{ if (p[i] + 0 < q[i] + 0) exit 0; if (p[i] + 0 > q[i] + 0) exit 1 }}
  if (d(a) < d(b)) exit 0; exit 1 }}'
}}
# The version file $1 names on its first line (a pointer, installations/current), as now; else now is empty.
named() {{
  now=$(sed -n '1p' "$1" 2>/dev/null)
  case $now in ''|[!0-9]*|*[!0-9A-Za-z.+_-]*) now= ;; esac
}}
# Version $1 installed by its own release (`cad setup --add`, run by uvx), then run with the arguments after it.
install() {{
  case $1 in *[!0-9.abcoprst]*) say "{development}" 3 ;; esac
  uvx=$(command -v uvx 2>/dev/null)
  for found in "$HOME/.local/bin/uvx" "$HOME/.cargo/bin/uvx"; do
    [ -z "$uvx" ] && [ -x "$found" ] && uvx=$found
  done
  if [ -z "$uvx" ]; then
    why="uv is not installed"
  else
    why=$(unset CAD_INSTALLATION_VERSION; "$uvx" --no-config --managed-python --python {python} \\
      --from "{server}==$1" {command} setup --add --quiet </dev/null 2>&1) && present "$1" && run "$@"
    why=$(printf '%s\\n' "$why" | sed '/^[[:space:]]*$/d' | tail -n 1)
    [ -n "$why" ] || why="it said nothing"
  fi
  say "{not_installed}" 3
}}
case $1 in
+*)
  version=${{1#+}}
  channel=
  case $version in *@*) channel=${{version#*@}}; version=${{version%%@*}} ;; esac
  case $version in ''|[!0-9]*|*[!0-9A-Za-z.+_-]*) say "{bad_pin}" 2 ;; esac
  case $1 in
  *@*)
    case $channel in default) channel= ;; ''|[!a-z0-9]*|*[!a-z0-9._-]*) say "{bad_channel}" 2 ;; esac
    [ ${{#channel}} -le 32 ] || say "{bad_channel}" 2 ;;
  esac
  # Installed: its own cad reads the pin, and moves its channel to it, or says it is stale.
  present "$version" && run "$version" "$@"
  # Not installed: stale where its channel is on a newer version already, else installed.
  if [ -n "$channel" ]; then named "$state/channels/$channel"; else named "$state/default"; fi
  if [ -n "$now" ] && older "$version" "$now"; then
    if [ -n "$channel" ]; then say "{stale_named}" 4; fi
    say "{stale_default}" 4
  fi
  install "$version" "$@"
  ;;
esac
# No pin: the default channel's version (its pointer); with none, the installation the layout of 0.11.10 and earlier
# names current where the install command has run here (its receipt), run as that layout's command ran it; else the
# newest version installed that has started, else the newest installed.
named "$state/default"
if [ -n "$now" ]; then
  present "$now" && run "$now" "$@"
  install "$now" "$@"
fi
if [ -f "$state/install-receipt.json" ]; then
  named "$state/installations/current"
  python=$(record python "$state/installations/$now.json")
  cad=$(record cad "$state/installations/$now.json")
  [ -n "$now" ] && [ -x "$python" ] && [ -f "$cad" ] && exec "$python" -P -m cad_server._internal.proxy "$@"
fi
newest=
started=
for marker in "$state"/versions/*/code/cad-version.json; do
  name=${{marker%/code/cad-version.json}}
  name=${{name##*/}}
  present "$name" || continue
  if [ -z "$newest" ] || ! older "$name" "$newest"; then newest=$name; fi
  [ -f "$state/versions/$name/data/format.json" ] || continue
  if [ -z "$started" ] || ! older "$name" "$started"; then started=$name; fi
done
# The newest that has started: one never started runs its channel's first use before anything else.
[ -n "$started" ] && newest=$started
[ -n "$newest" ] && present "$newest" && run "$newest" "$@"
printf '%s\\n' '{refusal}' >&2
exit 1
"""

# --- the Windows command ----------------------------------------------------------------------
#
# On Windows the command is ``cad.exe``, the launcher pip puts in front of every console script --
# distlib's stub (``_stub``) -- then a shebang naming the command's own Python, then a zip whose
# ``__main__.py`` (``_MAIN``) chooses as the sh does. The stub runs ``<python> -I <cad.exe> <the arguments
# as given>``: they reach Python through CreateProcess, never through cmd, so ``>``, ``&``, ``^``, ``!`` and
# ``%NAME%`` are characters, and Ctrl+C asks nothing. The shebang names its Python relative to the stub's
# own folder (``<launcher_dir>``): ``cad-launcher`` beside it (``INTERPRETER``), a virtual environment with
# nothing installed that uv makes once of the writing installation's interpreter. So the file is the same
# bytes from every release and every state folder, and an update or a switch never rewrites it: only a
# later revision does, and a Python that no longer starts (``_interpreter_ok``) is made again. A ``cad.exe`` that runs -- ``cad update``
# runs through it -- cannot be replaced or removed, but it can be renamed: it is set aside
# (``cad.exe.<hex>.old``) and the new one put in its place, and what was set aside goes at a later write
# (``_sweep``). The batch file of revisions before (``EARLIER_CMD``) goes once ``cad.exe`` is in place.
EXE = "cad.exe"
EARLIER_CMD = "cad.cmd"
INTERPRETER = "cad-launcher"
_SHEBANG = f"#!<launcher_dir>\\{INTERPRETER}\\Scripts\\python.exe -I\n"
ASIDE = ".old"

_MAIN = '''# {mark}{revision}
# The cad command on Windows (cad.exe), as the sh is elsewhere: `cad +<version>[@<channel>] ...` runs that version
# of text-to-cad and no other, its own cad, which reads the pin; a version not installed is installed first, by its
# own release, unless its channel is on a newer one already. With no pin: the default channel's version. Every
# release with pinned commands writes this same file; a release whose revision is older never replaces it. The standard
# library alone: its Python has nothing else.
import json
import os
import re
import shutil
import subprocess
import sys

VERSION = re.compile(r"[0-9][0-9A-Za-z.+_-]*")
CHANNEL = re.compile(r"[a-z0-9][a-z0-9._-]{{0,31}}")
# The characters of a release's name: one installed from the index, and run with no name told.
RELEASED = re.compile(r"[0-9.abcoprst]+")
NAME = "CAD_INSTALLATION_VERSION"
BAD_PIN, BAD_CHANNEL = {bad_pin!r}, {bad_channel!r}
STALE_DEFAULT, STALE_NAMED = {stale_default!r}, {stale_named!r}
NOT_INSTALLED, DEVELOPMENT = {not_installed!r}, {development!r}


def say(words, code):
    sys.stderr.write("cad: " + words + "\\n")
    return code


def named(path):
    """The version file ``path`` names on its first line (a pointer, installations/current), or None."""
    try:
        with open(path, encoding="utf-8") as handle:
            found = handle.readline().strip()
    except (OSError, ValueError):
        return None
    return found if VERSION.fullmatch(found) else None


def record(path):
    """The Python and cad a version's code marker (or an installation's record) names, while both are there."""
    try:
        with open(path, encoding="utf-8") as handle:
            found = json.load(handle)
        python, cad = found["python"], found["cad"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(python, str) and isinstance(cad, str) and os.path.isfile(python) and os.path.isfile(cad):
        return python, cad
    return None


def present(state, version):
    """Whether version ``version`` is installed: its code marker's Python and cad, else None."""
    return record(os.path.join(state, "versions", version, "code", "cad-version.json"))


def older(one, other):
    """Whether version ``one`` is older than ``other``, as the versions order them for the names releases and
    development builds have: their release numbers, then a development build (-dev.<stamp>) after its release, by
    its stamp (a tie is not older)."""
    def key(version):
        numbers = [int(part or 0) for part in re.match(r"[0-9.]*", version).group().split(".")]
        build = re.search(r"-dev\\.([0-9]+)$", version)
        return numbers, int(build.group(1)) if build else -1

    (first, one_build), (second, other_build) = key(one), key(other)
    size = max(len(first), len(second))
    first, second = first + [0] * (size - len(first)), second + [0] * (size - len(second))
    return (first, one_build) < (second, other_build)


def wait(child):
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:  # Ctrl+C reaches the version too: it decides, this waits for it
            continue


def run(version, found, args):
    """Version ``version``'s cad, as ``present`` found it, run with ``args``: a name of characters no release has
    (a development build's) told to it, which its code cannot know; none told to a release."""
    environment = dict(os.environ)
    if RELEASED.fullmatch(version):
        environment.pop(NAME, None)
    else:
        environment[NAME] = version
    # The arguments as Windows gave them to this process, as a list: Python quotes them for the next.
    return wait(subprocess.Popen([found[1], *args], env=environment))


def uvx():
    found = shutil.which("uvx")
    if found:
        return found
    home = os.path.expanduser("~")
    for folder in (os.path.join(home, ".local", "bin"), os.path.join(home, ".cargo", "bin")):
        for name in ("uvx.exe", "uvx"):
            if os.path.isfile(os.path.join(folder, name)):
                return os.path.join(folder, name)
    return None


def install(state, version, args):
    """Version ``version`` installed by its own release (`cad setup --add`, run by uvx), then run with ``args``."""
    if not RELEASED.fullmatch(version):
        return say(DEVELOPMENT % {{"version": version}}, 3)
    command = uvx()
    if command is None:
        why = "uv is not installed"
    else:
        environment = dict(os.environ)
        environment.pop(NAME, None)
        try:
            done = subprocess.run([command, "--no-config", "--managed-python", "--python", {python!r}, "--from",
                                   {server!r} + "==" + version, {command!r}, "setup", "--add", "--quiet"],
                                  env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            said, code = done.stdout or "", done.returncode
        except OSError as error:
            said, code = str(error), 1
        found = present(state, version) if code == 0 else None
        if found:
            return run(version, found, args)
        lines = [line.strip() for line in said.splitlines() if line.strip()]
        why = lines[-1] if lines else "it said nothing"
    return say(NOT_INSTALLED % {{"version": version, "why": why}}, 3)


def main():
    # The state folder as cad.engine.places says it: in the user's own folder, out of the local
    # application data an app package virtualizes.
    state = os.environ.get("CAD_STATE_DIR") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "cad")
    args = sys.argv[1:]
    if args and args[0].startswith("+"):
        version, at, channel = args[0][1:].partition("@")
        if not VERSION.fullmatch(version):
            return say(BAD_PIN % {{"word": args[0]}}, 2)
        if at and channel == "default":
            channel = ""
        elif at and not CHANNEL.fullmatch(channel):
            return say(BAD_CHANNEL % {{"word": args[0]}}, 2)
        # Installed: its own cad reads the pin, and moves its channel to it, or says it is stale.
        found = present(state, version)
        if found:
            return run(version, found, args)
        # Not installed: stale where its channel is on a newer version already, else installed.
        now = named(os.path.join(state, "channels", channel) if channel else os.path.join(state, "default"))
        if now and older(version, now):
            return say((STALE_NAMED if channel else STALE_DEFAULT) % {{"version": version, "channel": channel,
                                                                         "now": now}}, 4)
        return install(state, version, args)
    # No pin: the default channel's version (its pointer); with none, the installation the layout of 0.11.10 and earlier
    # names current where the install command has run here (its receipt), run as that layout's command ran it;
    # else the newest version installed that has started, else the newest installed.
    now = named(os.path.join(state, "default"))
    if now:
        found = present(state, now)
        return run(now, found, args) if found else install(state, now, args)
    if os.path.isfile(os.path.join(state, "install-receipt.json")):
        now = named(os.path.join(state, "installations", "current"))
        found = record(os.path.join(state, "installations", now + ".json")) if now else None
        if found:
            return wait(subprocess.Popen([found[0], "-P", "-m", "cad_server._internal.proxy", *args]))
    try:
        names = sorted(os.listdir(os.path.join(state, "versions")))
    except OSError:
        names = []
    newest = started = None
    for name in names:
        if VERSION.fullmatch(name) and present(state, name):
            if newest is None or not older(name, newest):
                newest = name
            # The newest that has started: one never started runs its channel's first use before anything else.
            if os.path.isfile(os.path.join(state, "versions", name, "data", "format.json")) and (
                    started is None or not older(name, started)):
                started = name
    newest = started or newest
    if newest:
        return run(newest, present(state, newest), args)
    sys.stderr.write({refusal!r} + "\\n")
    return 1


sys.exit(main())
'''


def _main_text() -> str:
    """The ``__main__.py`` of ``cad.exe``: the same from every version of this revision. Its refusals are
    ``cad_server._internal.pins``' words, the same as a version says them, filled in as it runs."""
    from cad_server._internal import pins
    from cad_server._internal.launch import COMMAND, PYTHON, SERVER
    from cad_server._internal.proxy import NONE_INSTALLED

    return _MAIN.format(mark=MARK, revision=REVISION, refusal=NONE_INSTALLED, python=PYTHON, server=SERVER,
                        command=COMMAND, bad_pin=pins.bad_pin("%(word)s"), bad_channel=pins.bad_channel("%(word)s"),
                        stale_default=pins.stale("%(version)s", None, "%(now)s"),
                        stale_named=pins.stale("%(version)s", "%(channel)s", "%(now)s"),
                        not_installed=pins.not_installed("%(version)s", "%(why)s", "nt"),
                        development=pins.development("%(version)s"))


def _archive() -> bytes:
    """What follows the stub in ``cad.exe``: the shebang and the zip of ``__main__.py``, byte for byte the same
    wherever it is made (a fixed date, a fixed system)."""
    import io
    import zipfile

    stream = io.BytesIO()
    entry = zipfile.ZipInfo("__main__.py", date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 0
    entry.external_attr = 0o644 << 16
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(entry, _main_text().encode("utf-8"))
    return _SHEBANG.encode("utf-8") + stream.getvalue()


def _stub() -> bytes:
    """distlib's console launcher for this machine's Windows, the one pip writes for every console script:
    ``t64-arm.exe`` on Windows on ARM, else ``t64.exe`` (``t32.exe`` for a 32-bit Python)."""
    import struct
    import sysconfig
    from importlib.resources import files

    if sysconfig.get_platform() == "win-arm64":
        name = "t64-arm.exe"
    else:
        name = "t64.exe" if struct.calcsize("P") == 8 else "t32.exe"
    try:
        return files("distlib").joinpath(name).read_bytes()
    except (ImportError, OSError) as missing:
        raise OSError(f"distlib's launcher {name} is not installed beside cad-server ({missing})") from None


def executable() -> bytes:
    """The bytes of ``cad.exe``."""
    return _stub() + _archive()


def interpreter_folder(where: str | None = None) -> str:
    """The cad command's Python on Windows: ``cad-launcher``, beside ``cad.exe``."""
    return os.path.join(where or proxy_folder(), INTERPRETER)


def _interpreter_ok(folder: str) -> bool:
    """Whether the cad command's Python at ``folder`` starts: its ``python.exe``, and the interpreter its
    ``pyvenv.cfg`` names as its home."""
    if not os.path.isfile(os.path.join(folder, "Scripts", "python.exe")):
        return False
    try:
        with open(os.path.join(folder, "pyvenv.cfg"), encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.partition("=")
                if key.strip().lower() == "home":
                    return os.path.isfile(os.path.join(value.strip(), "python.exe"))
    except (OSError, ValueError):
        pass
    return False


def _make_interpreter(folder: str) -> None:
    """The cad command's Python made at ``folder``: a virtual environment of this installation's interpreter,
    nothing installed, made by uv as every environment of the server's is (``base``), offline (the interpreter
    is here), beside its place and then moved there. ``OSError`` when it cannot be."""
    import shutil
    import subprocess

    from cad._internal.atomic_replace import temp_suffix
    from cad_server._internal import base

    try:
        uv = base.find_uv()
    except base.Refused as refused:
        raise OSError(str(refused)) from None
    temporary = folder + temp_suffix()
    step = [uv, "--no-config", "--offline", "--quiet", "venv", "--no-project", "--python", sys.executable, temporary]
    done = subprocess.run(step, cwd=os.path.dirname(folder), stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0 or not _interpreter_ok(temporary):
        shutil.rmtree(temporary, ignore_errors=True)
        lines = [line.strip() for line in (done.stderr or done.stdout or "").splitlines() if line.strip()]
        raise OSError(f"uv could not make the cad command's Python ({lines[-1] if lines else done.returncode})")
    if os.path.lexists(folder):
        _discard(_aside(folder))  # one that cannot start: nothing runs from it
    try:
        os.rename(temporary, folder)
    except OSError:
        shutil.rmtree(temporary, ignore_errors=True)
        if not _interpreter_ok(folder):  # another process put its own there meanwhile: that one
            raise


def _aside(path: str) -> str:
    """``path`` renamed beside itself out of the way (``<name>.<hex>.old``): Windows renames a program that
    runs, and neither replaces nor removes it. The new name."""
    aside = f"{path}.{os.urandom(4).hex()}{ASIDE}"
    os.rename(path, aside)
    return aside


def _discard(path: str) -> bool:
    """``path`` removed, a file or a folder: whether it is gone (a program that still runs stays)."""
    import shutil

    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError:
        return not os.path.lexists(path)
    return True


def _sweep(where: str) -> None:
    """What a write or an uninstall set aside while it still ran (``_aside``), removed where it no longer does."""
    try:
        names = os.listdir(where)
    except OSError:
        return
    for name in names:
        if name.endswith(ASIDE) and name.startswith((f"{EXE}.", f"{INTERPRETER}.")):
            _discard(os.path.join(where, name))


def _put(path: str, data: bytes) -> None:
    """``data`` written beside ``path``, then renamed onto it (``replace_atomic``)."""
    from cad._internal.atomic_replace import replace_atomic, temp_suffix

    temporary = f"{path}{temp_suffix()}"
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
        replace_atomic(temporary, path)
    finally:
        if os.path.lexists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _write_exe(path: str, data: bytes) -> None:
    """``data`` written to ``path`` whole, a ``cad.exe`` that runs set aside first (``_aside``): Windows
    refuses to replace it -- this very command, as `cad update` runs through it -- but renames it."""
    try:
        _put(path, data)
        return
    except PermissionError:
        if not os.path.isfile(path):
            raise
    aside = _aside(path)
    try:
        _put(path, data)
    except OSError:
        try:
            os.rename(aside, path)
        except OSError:
            pass
        raise
    _discard(aside)


def _write_windows(where: str, path: str) -> None:
    """``cad.exe`` and its Python, each written where it is not as this revision writes it."""
    folder = interpreter_folder(where)
    if not _interpreter_ok(folder):
        _make_interpreter(folder)
    data = executable()
    try:
        with open(path, "rb") as handle:
            same = handle.read() == data
    except OSError:
        same = False
    if not same:
        _write_exe(path, data)


def earlier_command(where: str | None = None) -> str | None:
    """The Windows cad command of a revision before (``cad.cmd``, a batch file) where it is text-to-cad's."""
    path = os.path.join(where or proxy_folder(), EARLIER_CMD)
    return path if os.path.isfile(path) and _revision(path) is not None else None


def _exe_status(path: str) -> str:
    if not os.path.lexists(path):
        return MISSING
    if os.path.islink(path):
        return FOREIGN
    import zipfile

    try:
        with zipfile.ZipFile(path) as archive:
            head = archive.read("__main__.py")[:512].decode("utf-8", "replace")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return FOREIGN  # no zip, or one with no __main__.py of ours: uv's or pip's cad.exe, a person's own
    revision = _revision_in(head)
    if revision is None:
        return FOREIGN
    if revision > REVISION:
        return NEWER
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return STALE
    # The stub is whichever distlib wrote it: what follows it is this revision's, or it is stale.
    same = data.startswith(b"MZ") and data.endswith(_archive())
    return OK if same and _interpreter_ok(interpreter_folder(os.path.dirname(path))) else STALE


def remove_proxy(where: str | None = None, windows: bool = WINDOWS) -> tuple[list[str], list[str]]:
    """The cad command removed (an uninstall's): ``(removed, left)``. On Windows its Python and a ``cad.cmd``
    of a revision before go with it, and a ``cad.exe`` that runs -- the uninstall's own -- is set aside
    (``_aside``): no command any more, removed by a later write, or by hand once it ends (``left``).
    ``OSError`` when the command cannot be taken out of its place."""
    where = where or proxy_folder()
    path = proxy_path(where, windows)
    if not windows:
        os.unlink(path)
        return [path], []
    _sweep(where)
    removed, left = [], []
    if _exe_status(path) not in (MISSING, FOREIGN):  # a cad.exe not ours (``uv tool install``'s) stays
        if _discard(path):
            removed.append(path)
        else:
            aside = _aside(path)
            removed.append(path)
            if not _discard(aside):
                left.append(aside)
    earlier = earlier_command(where)
    if earlier and _discard(earlier):
        removed.append(earlier)
    folder = interpreter_folder(where)
    if os.path.lexists(folder):
        if _discard(folder):
            removed.append(folder)
        else:
            try:
                left.append(_aside(folder))  # its python.exe runs this uninstall
            except OSError:
                left.append(folder)
    return removed, left


def script(windows: bool = WINDOWS) -> str:
    """The proxy's text: the same from every version of this revision. On Windows, ``cad.exe``'s
    ``__main__.py`` (the file is ``executable``)."""
    if windows:
        return _main_text()
    from cad_server._internal import pins
    from cad_server._internal.launch import COMMAND, PYTHON, SERVER
    from cad_server._internal.proxy import NONE_INSTALLED

    # Its refusals are ``pins``' words, the same as a version says them, said in double quotes with the
    # script's variables where the version, channel, reason and word go.
    # A backtick is said as one (escaped): the stale line names `cad update`.
    words = {key: text.replace("`", "\\`") for key, text in {
        "bad_pin": pins.bad_pin("$1"), "bad_channel": pins.bad_channel("$1"),
        "stale_default": pins.stale("$version", None, "$now"),
        "stale_named": pins.stale("$version", "$channel", "$now"),
        "not_installed": pins.not_installed("$1", "$why", "posix"), "development": pins.development("$1")}.items()}
    for text in words.values():
        bare = text.replace("\\`", "")
        for variable in ("$channel", "$version", "$now", "$why", "$1"):
            bare = bare.replace(variable, "")
        if set(bare) & set('"`$\\'):
            raise ValueError(f"the cad command cannot say {text!r} in double quotes")
    if "'" in NONE_INSTALLED:
        raise ValueError("the cad command says its refusal in single quotes")
    return _SH.format(mark=MARK, revision=REVISION, python=PYTHON, server=SERVER, command=COMMAND,
                      refusal=NONE_INSTALLED, **words)


def _revision_in(head: str) -> int | None:
    """The revision a proxy's first lines carry (``MARK``), or ``None`` when they carry none."""
    for line in head.splitlines()[:3]:
        at = line.find(MARK)
        if at >= 0:
            try:
                return int(line[at + len(MARK):].strip())
            except ValueError:
                return None
    return None


def _revision(path: str) -> int | None:
    """The revision of the proxy script at ``path``, or ``None`` when it is not the proxy."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(512)
    except (OSError, ValueError):
        return None
    return _revision_in(head)


def proxy_status(path: str | None = None, windows: bool = WINDOWS) -> str:
    path = path or proxy_path(windows=windows)
    if windows:
        return _exe_status(path)
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
    folder it cannot write is not raised but returned as the error, for ``cad doctor`` to say. On
    Windows, what earlier writes set aside goes (``_sweep``), and so does a ``cad.cmd`` of a revision
    before once ``cad.exe`` is in place: at the write after the one that put it there, as a ``cad.cmd``
    that ran the write (``cad update`` through it) is a batch file cmd reads on after it."""
    where = where or proxy_folder()
    path = proxy_path(where, windows)
    status = proxy_status(path, windows)
    if windows:
        _sweep(where)
        earlier = earlier_command(where)
        if earlier and status in (OK, NEWER):
            _discard(earlier)
    if status not in (MISSING, STALE):
        return path, status, None
    from cad._internal.atomic_replace import replace_atomic, temp_suffix

    temporary = f"{path}{temp_suffix()}"
    try:
        os.makedirs(where, exist_ok=True)
        if windows:
            _write_windows(where, path)
        else:
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


def setup(version: str, *, make_current: bool = False) -> tuple[tuple[str, str, str | None], tuple[str, str, str | None]]:
    """Register this installation as ``version`` and write the proxy: each ``(path, status, error)``.
    With ``make_current`` (a development install), it is pointed at as ``current``; else only when no
    live installation is (``bootstrap``). On a device 0.8 set up, what this release keeps of its state
    folder -- the person's settings, documents and Recents, and setup's receipt -- is moved into this
    one's first (``cad.engine.places.adopt_earlier``)."""
    from cad.engine.places import adopt_earlier

    adopt_earlier()
    try:
        path, status = register(version)
        registered: tuple[str, str, str | None] = (path, status, None)
        if make_current:
            point(version)
        else:
            bootstrap(version)
    except (OSError, ValueError) as failure:
        try:
            where = str(state().path(_inside(version)))
        except (OSError, ValueError):
            where = version
        registered = (where, MISSING, f"{type(failure).__name__}: {getattr(failure, 'strerror', None) or failure}")
    else:
        write_plugin()
    return registered, write_proxy()


def write_plugin() -> bool:
    """The plugin folder written from this installation (``cad_server._internal.plugin``) when it is the
    current one and a release's -- a development install (named, ``NAME_ENV``) or a source tree writes it
    only when asked, by ``cad plugin``: whether it was written. Silent, and never a failure of the
    registration it rides on: ``cad doctor`` says how the folder is."""
    if os.environ.get(NAME_ENV) or editable() or not mine(current()):
        return False
    try:
        from cad_server._internal import plugin

        plugin.write()
    except Exception:  # noqa: BLE001 - a registration never fails on the folder
        return False
    return True


def startup() -> None:
    """As the CAD app's server starts, silently: the proxy written, and where no installation is current
    (the device's first), this one registered and made current (``bootstrap``). Where one is, this server
    attaches to its engine (``cad.engine.client``) and registers nothing: an app that moved its plugin
    to another release moves no device's engine."""
    try:
        if current() is not None:
            write_proxy()
            return
        version = own_version()
        if version:
            setup(version)
    except Exception:  # noqa: BLE001 - a registration never fails the server it rides on
        pass


if __name__ == "__main__":
    # ``python -m cad_server._internal.installations``: what an agent app's stdio transport runs on a device with
    # no installation current (``cad_mcp.engine.register``), with this installation's Python.
    startup()
