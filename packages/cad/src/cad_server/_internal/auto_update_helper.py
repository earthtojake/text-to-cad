"""cad's own update, carried out by a process that is not cad: ``auto_update.trigger`` runs this file's source with
the Python cad's environment was made from (``-I -S``, from its copy in the state folder: never cad's environment, never a module of it), detached and
with no window, and hands it one JSON argument: ``cad`` (the environment's own ``cad`` command), ``target`` (the release
asked for, or null: whatever the upgrade gets), ``prefix`` (the environment), ``record`` (the last attempt's file),
``from``, ``at`` and ``tries``; the installer's commands, ``upgrade`` (cad upgraded to the newest release of the major
of ``from``, never below it; with ``major``, to the newest release of all), ``put_back`` (the release that ran before
installed again) and ``launchers`` (prints the folder its launchers are in); ``installer`` (its name), ``wanted`` (the
release the attempt is for), ``asked`` (a person's own request: a typed update, the viewer's update button) and
``major`` (``cad update --major``), which it keeps in the record for the server to count and judge; ``start``,
whether it starts the server at the end (false where ``cad update`` found none running: it leaves none running);
``log``, the file it writes each command to (none: no log);
``uv_floor``, the oldest uv cad asks for; and, where the installer has a second way, ``pin``, ``bounded``, ``refresh``
and ``no_config`` (``escalate``).

In order: the server stopped (``cad server stop``, which waits until it is gone); unless the environment already holds
``target`` or newer, or (but for ``major``) a release of a higher major than ``from``'s, which a bounded upgrade would
take down (forward only), the upgrade, tried again on failure, until it ends 0 with a release installed that it may end
on (``accepted``: never older than ``from`` and, but for ``major``, of ``from``'s major), ``target`` or newer where
there is one -- for ``major``, any release of a higher major than ``from``'s: the major crossed is what was asked --;
where the last try ended 0 on such a release below ``target``, that one, but for a ``major`` whose ``target`` is of a
higher major (one that did not cross fails); where every try failed and ``cad`` no longer runs (uv removes the whole
tool when an install fails after it has begun), the release that ran before put back (``from``: no way back from a
good update, only what a failed one destroyed); the server started with whatever cad is there, where ``start`` says
so; and the outcome written to ``record`` (``keep``: written beside it, then moved into place): ``installed`` for a
newer release, ``current`` for the one that ran (nothing newer it may take), ``failed`` for anything else, as every
failure is -- and for ``major``, a release of ``from``'s major where ``target``, PyPI's newest, is of a higher one. The
release the record names is the one installed after the upgrade, where it ended well; the one asked for where it did
not. Where the upgrade ended 0 and kept a release below ``target`` (uv's ``kept``), it is tried again in the same run,
another way each time (``escalate``: the index read afresh, then ``target`` asked for by name, whose error says why it
cannot be had, then the upgrade from ``target`` so the installer keeps a range), where the trigger handed those ways
(``pin``). No installer command runs on an environment that is half made (``whole``: a folder with no ``pyvenv.cfg``,
which an install the disk filled under, or one stopped midway, leaves): uv run on one acts on the Python it was made
from and removes that Python's packages; the attempt stops there, ``half_made``. As it runs, the helper writes the time
into the record every ``BEAT_SECONDS`` (``Beat``), by which the server tells it is still underway; it writes no outcome
over another attempt's record (one begun since, by a process that took this one for lost). Where the attempt did not
install what it was for, the record says why in one word (``cause``, one of ``CAUSES``,
told by ``cause_of`` from the upgrade's last try: its exit status, all it printed, the system's error, and which of
the installer's settings are there, by name alone); each command it ran, with its exit status, how long it took and
the end of what it printed, is in the log (``Log``), which stays on the computer. Telling the cause and writing the
log never stop the update: where either fails, the update runs and is recorded as without it. Where the helper itself
raises, the attempt stays as the trigger kept it, marked ``helper_crash`` (``main``). It runs no install command and
counts nothing: the server that starts after it does both (``auto_update.report``, ``plugin_catch_up``). The standard
library alone, and nothing else of cad.

Left as it is: a ``cad server start`` that arrives while this runs (a person's, an agent's, an app's server line) starts
whatever cad is there at that moment; this helper's own start at the end meets it as any start meets a running server.

On Windows an installer cannot remove a ``cad.exe`` that runs (a ``cad update`` waiting, a ``cad server start``), and an
install that meets one fails halfway. A running ``cad.exe`` can be renamed, though, once cad holds it only as a running
program (``cad_server/__init__.py`` takes it off ``sys.path``). So before each try, each ``cad.exe`` of the tool, the
launchers' folder's and the environment's own, is renamed to a name of its own in the launchers' folder, never inside
the environment, which uv deletes when an install fails, and a copy is put back where it was (``set_aside``). The
process keeps running from the renamed file. The renamed files are deleted where they can be, at the start and the end
of each run; one whose process still runs is left for the next (``tidy``). Every command runs with no console window.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# Seconds waited before each try of the install: the first at once.
WAITS = (0, 2, 5, 10, 20)
WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW: no console flashes for uv or cad
# A cad.exe set aside in the launchers' folder (``set_aside``): ``<stamp>`` names the try, ``<n>`` the file.
ASIDE = ".cad.exe.{stamp}.{n}.old"
# How long an install may run.
INSTALL_SECONDS = 900
# How often the helper marks its attempt as still underway (``Beat``): well inside ``auto_update.LOST_SECONDS``.
BEAT_SECONDS = 60
# The detail of an attempt that found cad's environment half made (``whole``), and ran nothing more in it.
HALF_MADE = "cad's environment has no pyvenv.cfg: nothing more was run in it"


def release(text):
    """``X.Y.Z`` as three numbers, or None."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def named(held):
    return ".".join(map(str, held))


def installed(prefix):
    """The release of cad the tool environment at ``prefix`` holds now (the newest, after an install that failed
    midway), or None."""
    found = [release(path.name[len("cad-"):-len(".dist-info")]) for pattern in
             ("lib/python*/site-packages/cad-*.dist-info", "Lib/site-packages/cad-*.dist-info")
             for path in Path(prefix).glob(pattern)]
    return max((held for held in found if held is not None), default=None)


def whole(prefix):
    """Whether an installer may act on the environment at ``prefix``: there is none (the installer makes it afresh), or
    it holds its ``pyvenv.cfg``. A folder without one is half made, and uv run on it acts on the Python it was made
    from."""
    path = Path(prefix)
    return not path.exists() or (path / "pyvenv.cfg").is_file()


def run(command, timeout):
    """``(exit status, all it printed, stdout and stderr together)``; status None where it could not run or did not end
    in time, and then the error's type and words (``TimeoutExpired: ...``, ``FileNotFoundError: ...``), which
    ``classify`` reads."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{type(error).__name__}: {error}"
    return done.returncode, done.stdout or ""


def last_line(text):
    """The last line of ``text`` that holds anything, stripped; "" for none."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def bin_folder(told, run):
    """The installer's launchers' folder, where the tool's ``cad`` command is (uv: ``uv tool dir --bin``, which reads
    ``UV_TOOL_BIN_DIR`` as uv's install does), or None."""
    code, said = run(told["launchers"], 60)
    folder = last_line(said)
    return Path(folder) if code == 0 and folder and Path(folder).is_dir() else None


def set_aside(told, folder):
    """Windows, before a try of the install: the launchers' folder's ``cad.exe`` and the environment's own
    (``told["cad"]``) each renamed to a name of its own in ``folder``, the launchers' folder, and a copy put back where
    it was. A rename that fails (no such file, another volume) is skipped. What was set aside."""
    stamp = f"{os.getpid()}-{time.time_ns()}"
    moved = []
    for n, exe in enumerate((folder / "cad.exe", Path(told["cad"]))):
        aside = folder / ASIDE.format(stamp=stamp, n=n)
        try:
            os.replace(exe, aside)
        except OSError:
            continue
        moved.append(aside)
        try:
            shutil.copy2(aside, exe)
        except OSError:
            pass
    return moved


def tidy(folder):
    """Every ``cad.exe`` set aside in ``folder`` deleted that can be; one whose process still runs refuses, and is left
    for the next run."""
    for aside in folder.glob(ASIDE.format(stamp="*", n="*")):
        try:
            aside.unlink()
        except OSError:
            pass


def accepted(held, before, major):
    """Whether the upgrade may end on release ``held``: never older than ``before``, the release that ran, and, but for
    ``major`` (``cad update --major``), of ``before``'s major. Any release where ``before`` is not known."""
    if held is None:
        return False
    return before is None or (held >= before and (major or held[0] == before[0]))


def install(told, command, wanted, run, sleep, folder=None, accept=lambda held: held is not None, settle=False,
            enough=lambda held: False, waits=WAITS, early=False):
    """``command`` run, tried at each of ``waits``, each ``cad.exe`` set aside first where ``folder`` (the launchers'
    folder, on Windows) is given, until it ends 0 with a release of cad installed that ``accept`` takes, ``wanted`` or
    newer where it is given, or one ``enough`` takes (``major``: a higher major than ``from``'s): ``(the release
    installed, or None, the installer's last line, (the last try's exit status, all it printed, the release it left))``.
    With ``settle``, where the last try ended 0 on a release ``accept`` takes, below ``wanted``, that release: nothing
    newer is to be had; with ``early`` too, at the first such try, which another way follows (``escalate``). None, and
    nothing more run, where the environment is half made (``whole``): the last line of the try that left it so."""
    detail, settled, last = "not tried", None, (None, "", None)
    for wait in waits:
        sleep(wait)
        if not whole(told["prefix"]):
            return None, detail if last[1] else HALF_MADE, last  # the words of the try that left it so, where one did
        if folder is not None:
            set_aside(told, folder)
        code, said = run(command, INSTALL_SECONDS)
        detail = last_line(said) if code is not None else said
        held = installed(told["prefix"])
        last = (code, said, held)
        if code == 0 and accept(held) and (wanted is None or held >= wanted or enough(held)):
            return held, detail, last
        settled = held if settle and code == 0 and accept(held) else None
        if code == 0:
            detail = (f"it installed {named(held)}, not {named(wanted)}" if accept(held) else
                      f"it installed {named(held) if held else 'no cad'}, which it may not end on")
        if early and settled is not None:
            break
    return settled, detail, last


def escalate(told, target, run, sleep, folder, accept, environ=None):
    """The upgrade, which ended 0 and kept a release below ``target``, tried again in the same run, once each way: with
    ``refresh`` (uv's ``--refresh``: the index read afresh, not from its cache), then ``pin`` (``cad==<target>``,
    whose error names why where it cannot be had: no such release, the Python, the platform) and, where that installed
    it, ``bounded`` (the upgrade from ``target``, ``cad>=<target>,<N>``: never below it), so the installer keeps a
    range for a person's own upgrade. Each with ``no_config`` too (uv's ``--no-config``: its settings' files not read)
    only where none of the installer's settings that decide what it can reach or take is there (``settings``): never
    past an index, a TLS setting, offline or exclude-newer the person set, so the cause stays theirs. ``(the release
    the environment holds where ``accept`` takes it, else None, the last line that says why, the try that says why)``,
    as ``install`` gives."""
    flags = [*told.get("refresh", ()), *(() if settings(told.get("installer", "uv"), environ) else
                                         told.get("no_config", ()))]
    upgrade, pin, bounded = ([*command[:-1], *flags, command[-1]]
                             for command in (told["upgrade"], told["pin"], told["bounded"]))
    detail, last = "not tried", (None, "", None)
    for command in (upgrade, pin):
        got, detail, last = install(told, command, target, run, sleep, folder, accept=accept, settle=True,
                                    waits=(0,))
        if last[0] != 0:
            break
        if got is not None and got >= target:
            if command is pin:
                again = install(told, bounded, target, run, sleep, folder, accept=accept, settle=True, waits=(0,))
                if again[2][0] != 0:
                    detail, last = again[1], again[2]
            break
    held = installed(told["prefix"])
    return (held if accept(held) and whole(told["prefix"]) else None), detail, last


def update(told, run=run, sleep=time.sleep, windows=WINDOWS, environ=None):
    """The update ``told`` asks for; its outcome as the record keeps it, with its ``cause`` where it did not install
    what it was for (``cause_of``). Each command it runs is written to the log (``Log``, where ``told`` names one)."""
    log = Log(told.get("log"))
    log.begin(told)
    run = log.running(run)
    target, before, restored = release(told["target"]), release(told["from"]), None
    major = told.get("major") is True
    folder = bin_folder(told, run) if windows else None
    if folder is not None:
        tidy(folder)
    stopped = run([told["cad"], "server", "stop"], 120)[0]
    held = installed(told["prefix"])
    above = held is not None and before is not None and not major and held[0] > before[0]
    last = None
    accept = lambda found: accepted(found, before, major)  # noqa: E731
    if not whole(told["prefix"]):
        outcome, detail, got = "failed", HALF_MADE, None
    elif held is not None and ((target is not None and held >= target) or above):
        outcome, detail, got = "current", f"cad {named(held)} is installed", held
    else:
        # ``major``: crossing to a higher major is what was asked, whatever release of it the upgrade got; where no
        # higher major was the target (none is out, or PyPI could not say), it ends as a bounded update does.
        crossed = lambda found: major and found is not None and before is not None and found[0] > before[0]  # noqa: E731
        second = "pin" in told and target is not None and not major
        got, detail, last = install(told, told["upgrade"], target, run, sleep, folder, accept=accept, enough=crossed,
                                    settle=not (major and crossed(target)), early=second)
        if second and got is not None and got < target:
            got, detail, last = escalate(told, target, run, sleep, folder, accept, environ)
        outcome = "failed" if got is None else "installed" if before is None or got > before else "current"
        if got is None and whole(told["prefix"]) and run([told["cad"], "--version"], 60)[0] != 0:
            restored = install(told, told["put_back"], before, run, sleep, folder)[0] is not None
    cause = None
    try:
        cause = cause_of(told, outcome, got, last, stopped, run, environ, log)
    except Exception as error:  # noqa: BLE001 - a cause that cannot be told leaves the record as it was
        log.write(f"the cause could not be told: {type(error).__name__}: {error}")
    start = told.get("start", True) is not False
    code, said = run([told["cad"], "server", "start"], 120) if start else (None, "")
    said = last_line(said) if code is not None else said
    if folder is not None:
        tidy(folder)
    found = {"release": named(got) if got is not None else told["target"] or "latest", "from": told["from"],
             "at": told["at"], "tries": told.get("tries", 1), "ended": time.time(), "outcome": outcome,
             "detail": detail, **({} if restored is None else {"restored": restored}),
             **({} if cause is None else {"cause": cause}),
             **({"started": said if code == 0 else f"not started: {said}"} if start else {"start": False}),
             **{name: told[name] for name in ("installer", "wanted", "asked", "major") if name in told}}
    log.end(found)
    return found


# --- why an attempt did not install what it was for: one word ------------------------------------------------------

# Every word a record's ``cause`` holds, a closed list. The helper tells most of them from the upgrade's last try
# (``cause_of``); ``helper_start`` is the trigger's (its helper could not start), ``lost`` a reader's (an attempt still
# underway and silent, its helper gone without a word), ``no_installer`` and ``no_python`` the reasons none begins
# (``auto_update.blocked``); ``packaged`` (cad inside a Windows app's private copy of AppData) is kept for the check
# that tells it. Each word is said in plain words by ``auto_update.SAID``.
CAUSES = ("timeout", "no_program", "in_use", "denied", "disk_full", "half_made", "network", "offline", "no_release",
          "python", "platform", "config_exclude", "config_index", "config_tls", "uv_old", "kept", "server_running",
          "helper_start", "helper_crash", "lost", "no_installer", "no_python", "packaged", "unknown")

# What an installer's output says, tried in order, the first match winning: uv's and pip's own words (pipx prints
# pip's), and the system's for an error of the file system (``os error N`` is uv's spelling, ``[Errno N]`` and
# ``[WinError N]`` Python's). Read with each run of white space made one space: uv wraps its messages.
SAYS = (
    ("uv_old", (r"unexpected argument '", r"unrecognized subcommand", r"unexpected value '")),
    ("in_use", (r"os error 32\b", r"WinError 32\b", r"being used by another process", r"os error 16\b",
                r"resource busy", r"text file busy", r"os error 26\b")),
    ("disk_full", (r"os error 28\b", r"Errno 28\b", r"os error 112\b", r"WinError 112\b", r"no space left on device",
                   r"not enough space on the disk", r"disk quota exceeded", r"os error 122\b")),
    ("offline", (r"network was disabled", r"network is disabled")),
    ("network", (r"failed to fetch", r"error sending request", r"dns error", r"tcp connect", r"connection refused",
                 r"connection reset", r"timed out", r"tunnel error", r"certificate", r"NewConnectionError",
                 r"failed to establish a new connection", r"could not connect", r"name resolution",
                 r"name or service not known", r"no such host is known", r"network is unreachable", r"ProxyError",
                 r"SSLError", r"request failed after \d+ retr")),
    ("denied", (r"os error 5\b", r"WinError 5\b", r"access is denied", r"permission denied", r"os error 13\b",
                r"Errno 13\b", r"operation not permitted")),
    ("python", (r"requires Python", r"requires a different Python", r"require a different python version",
                r"Requires-Python")),
    ("platform", (r"no wheels with a matching", r"platform tag", r"ABI tag", r"implementation tag",
                  r"not a supported wheel on this platform")),
    ("no_release", (r"no solution found when resolving", r"not found in the package registry", r"no version of cad",
                    r"could not find a version that satisfies", r"no matching distribution found",
                    r"requirements are unsatisfiable")),
)
_SAYS = tuple((word, re.compile("|".join(patterns), re.IGNORECASE)) for word, patterns in SAYS)
# Where an index's words name PyPI's own hosts, a network failure is the network's, whatever index a setting adds.
PYPI_HOSTS = re.compile(r"pypi\.org|pythonhosted\.org", re.IGNORECASE)
TLS_WORDS = re.compile(r"certificate|SSL|TLS", re.IGNORECASE)


def classify(code, output):
    """The cause an installer's run says, from its exit status and all it printed (``run``'s): ``timeout`` and
    ``no_program`` where it did not end or could not start, else the first of ``SAYS`` its words match, else
    ``unknown``. None where it ended 0."""
    if code == 0:
        return None
    text = output or ""
    if code is None:
        if text.startswith("TimeoutExpired"):
            return "timeout"
        if text.startswith(("FileNotFoundError", "NotADirectoryError")):
            return "no_program"
        if text.startswith("PermissionError"):
            return "denied"
    flat = " ".join(text.split())
    return next((word for word, says in _SAYS if says.search(flat)), "unknown")


# The settings of an installer that decide what it can reach or take, by name (``settings``): uv's environment
# variables and the keys of its ``uv.toml``; pip's (pipx runs pip) and the keys of its ``pip.conf``. Read for whether
# they are there, never for what they hold.
SETTINGS = {
    "uv": {
        "config_exclude": ("UV_EXCLUDE_NEWER", "exclude-newer", "exclude-newer-package"),
        "config_index": ("UV_INDEX", "UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "UV_FIND_LINKS",
                         "UV_NO_INDEX", "UV_INDEX_STRATEGY", "index", "index-url", "extra-index-url", "find-links",
                         "no-index", "index-strategy"),
        "config_tls": ("UV_NATIVE_TLS", "UV_SYSTEM_CERTS", "UV_INSECURE_HOST", "SSL_CERT_FILE", "SSL_CERT_DIR",
                       "native-tls", "system-certs", "allow-insecure-host"),
        "offline": ("UV_OFFLINE", "offline"),
    },
    "pipx": {
        "config_index": ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_FIND_LINKS", "PIP_NO_INDEX", "index-url",
                         "extra-index-url", "find-links", "no-index"),
        "config_tls": ("PIP_CERT", "PIP_TRUSTED_HOST", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "cert", "trusted-host"),
    },
}


UV_SYSTEM = ("/etc/uv/uv.toml",)  # uv's system-wide settings beside ``$XDG_CONFIG_DIRS``'s, on Linux and macOS
PIP_SYSTEM = ("/etc/xdg/pip/pip.conf", "/etc/pip.conf")  # pip's


def setting_files(installer, environ, windows=WINDOWS):
    """The files the installer reads its settings from, where they are: uv's ``uv.toml`` (``UV_CONFIG_FILE`` alone
    where it is set; none where ``UV_NO_CONFIG`` is), the person's and the system's; pip's ``pip.conf`` (``pip.ini`` on
    Windows), ``PIP_CONFIG_FILE``'s, the person's and the system's."""
    home = Path(environ.get("USERPROFILE" if windows else "HOME") or Path.home())
    config = Path(environ.get("XDG_CONFIG_HOME") or home / ".config")
    shared = [Path(environ[name]) for name in ("APPDATA", "PROGRAMDATA") if windows and environ.get(name)]
    if installer == "uv":
        if environ.get("UV_NO_CONFIG"):
            return []
        if environ.get("UV_CONFIG_FILE"):
            found = [Path(environ["UV_CONFIG_FILE"])]
        elif windows:
            found = [folder / "uv" / "uv.toml" for folder in shared]
        else:
            system = [Path(folder) for folder in (environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":") if folder]
            found = [config / "uv" / "uv.toml", *(folder / "uv" / "uv.toml" for folder in system),
                     *map(Path, UV_SYSTEM)]
    else:
        found = [Path(environ["PIP_CONFIG_FILE"])] if environ.get("PIP_CONFIG_FILE") else []
        if windows:
            found += [folder / "pip" / "pip.ini" for folder in shared]
        else:
            found += [config / "pip" / "pip.conf", home / ".pip" / "pip.conf", *map(Path, PIP_SYSTEM)]
    return [path for path in found if path.is_file()]


def _keys(path):
    """The names of the settings a ``uv.toml`` (its top-level keys: ``[[index]]`` is ``index``; a ``[pip]`` table is
    for ``uv pip`` alone) or a ``pip.conf`` (every option, in any section) holds; none where it cannot be read."""
    try:
        if path.suffix == ".toml":
            import tomllib

            return set(tomllib.loads(path.read_text(encoding="utf-8")))
        import configparser

        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding="utf-8")
        return {option for section in parser.sections() for option in parser.options(section)}
    except Exception:  # noqa: BLE001 - a file that cannot be read holds nothing that is known
        return set()


def settings(installer, environ=None, windows=WINDOWS):
    """Which of ``SETTINGS`` the installer has, by the cause each can bring: ``{cause: [the names found]}``, an
    environment variable by its name, a file's key as ``<key> (<file>)``. Never a value."""
    environ = os.environ if environ is None else environ
    known = SETTINGS.get(installer, {})
    files = [(path, _keys(path)) for path in setting_files(installer, environ, windows)]
    found = {}
    for cause, names in known.items():
        hits = [name for name in names if name.isupper() and environ.get(name) is not None]
        hits += [f"{name} ({path})" for path, keys in files for name in names if not name.isupper() and name in keys]
        if hits:
            found[cause] = hits
    return found


def refine(cause, output, found):
    """A cause the installer's settings explain better (``found``: ``settings``): a network failure where a TLS
    setting is there and the words are of a certificate, ``config_tls``; one of an index other than PyPI's where an
    index setting is there, ``config_index``; a release not found, or the one that ran kept, where a setting hides
    newer releases, ``config_exclude``, or adds an index, ``config_index``; either where uv is set offline,
    ``offline``."""
    text = output or ""
    if cause == "network":
        if "config_tls" in found and TLS_WORDS.search(text):
            return "config_tls"
        if "config_index" in found and not PYPI_HOSTS.search(text):
            return "config_index"
    if cause in ("no_release", "kept", "network") and "offline" in found:
        return "offline"
    if cause in ("no_release", "kept"):
        for setting in ("config_exclude", "config_index"):
            if setting in found:
                return setting
    return cause


def uv_release(text):
    """The release ``uv --version`` printed (``uv 0.13.8 (...)``), as numbers, or None."""
    match = re.search(r"\buv (\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def cause_of(told, outcome, got, last, stopped, run, environ=None, log=None):
    """Why the attempt did not install what it was for, one of ``CAUSES``, or None where it did (or nothing newer was
    asked: the environment already held it). The environment half made (``whole``), ``half_made``, whatever came
    before; ended 0 on the release that ran, though a newer one was wanted, ``kept``; else what the upgrade's last try
    said (``classify``), where ``cad server stop`` did not end 0 and the try was refused a file, ``server_running``;
    where uv's words say nothing known and uv is older than cad asks (``told["uv_floor"]``), ``uv_old``; then what the
    installer's settings explain (``refine``)."""
    if outcome != "installed" and not whole(told["prefix"]):
        return "half_made"
    if last is None or outcome == "installed":
        return None
    code, output, held = last
    if code == 0:  # it ended well on a release it did not end on: the one that ran (kept), or one it may not take
        cause = "kept" if held is not None and held == release(told["from"]) else "unknown"
    else:
        cause = classify(code, output)
    if cause in ("in_use", "denied", "unknown") and stopped not in (0, None):
        cause = "server_running"
    floor = release(told.get("uv_floor") or "")
    if cause == "unknown" and told.get("installer", "uv") == "uv" and floor is not None:
        said = run([told["upgrade"][0], "--version"], 60)
        held_uv = uv_release(said[1]) if said[0] == 0 else None
        if held_uv is not None and held_uv < floor:
            cause = "uv_old"
    found = settings(told.get("installer", "uv"), environ)
    if found and log is not None:
        log.write("the installer's settings found (names only): " + "; ".join(
            f"{name}: {', '.join(names)}" for name, names in sorted(found.items())))
    return refine(cause, output, found)


# --- the log: each command of the last two runs, on this computer alone ------------------------------------------

LOG_BYTES = 64 * 1024  # how much of each command's output the log keeps: its end


class Log:
    """The run written to ``path`` as it goes (``auto-update.log`` in the state folder), the run before moved to
    ``auto-update.1.log`` first: each command, its exit status, how long it took and the last ``LOG_BYTES`` of what it
    printed; then the outcome and its cause. Nothing of it is sent anywhere. With no ``path``, nothing is written;
    every write that fails is let go, and a log that cannot be written writes nothing more: the update runs and is
    recorded all the same."""

    def __init__(self, path):
        self.path = path

    def write(self, text):
        if not self.path:
            return
        try:
            with open(self.path, "a", encoding="utf-8", errors="replace") as handle:
                handle.write(text.rstrip("\n") + "\n")
        except Exception:  # noqa: BLE001 - the helper never fails of its log
            self.path = None

    def begin(self, told):
        if not self.path:
            return
        try:
            path = Path(self.path)
            try:
                os.replace(path, path.with_name(f"{path.stem}.1{path.suffix}"))
            except OSError:
                pass
            with open(path, "w", encoding="utf-8") as handle:
                wanted = told.get("wanted")
                handle.write(f"cad's update, begun {_when(time.time())}: from {told.get('from')} to "
                             f"{told.get('target') or 'the newest it may take'}"
                             f"{f' (for {wanted})' if wanted and wanted != told.get('target') else ''}, by "
                             f"{told.get('installer', 'uv')}, {'typed' if told.get('asked') else 'automatic'}"
                             f"{', --major' if told.get('major') else ''}, try {told.get('tries', 1)}\n")
        except Exception:  # noqa: BLE001 - the helper never fails of its log
            self.path = None

    def running(self, run):
        """``run``, each command it runs written to the log as it ends."""
        def each(command, timeout):
            began = time.monotonic()
            code, said = run(command, timeout)
            self.ran(command, code, time.monotonic() - began, said)
            return code, said
        return each

    def ran(self, command, code, seconds, said):
        if not self.path:
            return
        try:
            data = (said or "").encode("utf-8", errors="replace")
            cut = len(data) - LOG_BYTES
            text = data[max(cut, 0):].decode("utf-8", errors="ignore")
            lines = [f"$ {' '.join(map(str, command))}",
                     f"  {'exit ' + str(code) if code is not None else 'did not run to its end'} after {seconds:.1f} s"
                     + (f" (its first {cut} bytes left out)" if cut > 0 else "")]
            lines += [f"  | {line}" for line in text.rstrip().splitlines()]
            self.write("\n".join(lines))
        except Exception:  # noqa: BLE001 - the helper never fails of its log
            pass

    def end(self, found):
        self.write(f"ended {_when(found.get('ended') or time.time())}: {found.get('outcome')}"
                   + (f", the cause: {found['cause']}" if found.get("cause") else "")
                   + (f"; {found['detail']}" if found.get("detail") else ""))


def _when(at):
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(at))


# Seconds waited before each further try of moving the record into place, where Windows refuses it while another
# process has the record open (a server reading it): then the plain write.
REPLACE_WAITS = (0.05, 0.1, 0.2, 0.4, 0.8)


def keep(path, record, replace=os.replace, sleep=time.sleep):
    """``record`` written to a file of its own beside ``path``, then moved into its place (``os.replace``), so a reader
    never finds it half written; where the move is refused, tried again after each of ``REPLACE_WAITS``, then
    ``record`` written to ``path`` itself. Never raises: the helper never dies of its record."""
    text = json.dumps(record, sort_keys=True)
    staged = f"{path}.{os.getpid()}.tmp"
    try:
        with open(staged, "w", encoding="utf-8") as handle:
            handle.write(text)
        for wait in (0, *REPLACE_WAITS):
            sleep(wait)
            try:
                replace(staged, path)
                return
            except OSError:
                continue
    except OSError:
        pass
    try:
        os.remove(staged)
    except OSError:
        pass
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass


def ours(told):
    """Whether the record is still this attempt's (its ``at``), or there is none to read: an attempt begun since, by a
    process that took this one for lost, keeps it, and this one was counted ``lost`` as that began."""
    try:
        with open(told["record"], encoding="utf-8") as handle:
            found = json.load(handle)
    except (OSError, ValueError):
        return True
    return not isinstance(found, dict) or found.get("at") == told.get("at")


class Beat:
    """The attempt marked as still underway every ``BEAT_SECONDS`` as the helper runs (its record's ``beat``), from a
    thread of its own, so a command that runs for minutes beats too; only while the record is this attempt's and
    underway. ``stop()``: no beat after it, so the outcome is the record's last word. Never raises."""

    def __init__(self, told, every=BEAT_SECONDS):
        self.told, self.every, self.done = told, every, threading.Event()
        self.thread = threading.Thread(target=self.run, name="cad-update-beat", daemon=True)
        try:
            self.thread.start()
        except RuntimeError:  # no thread to be had: the update runs all the same, lost should it outlast the wait
            pass

    def run(self):
        while not self.done.wait(self.every):
            self.mark()

    def mark(self):
        """One beat: the record's ``beat`` now, where the record is this attempt's and underway."""
        try:
            with open(self.told["record"], encoding="utf-8") as handle:
                found = json.load(handle)
            if isinstance(found, dict) and found.get("at") == self.told.get("at") \
                    and found.get("outcome") == "underway":
                keep(self.told["record"], {**found, "beat": time.time()})
        except Exception:  # noqa: BLE001 - a beat missed is one minute nearer lost, nothing more
            pass

    def stop(self):
        self.done.set()
        if self.thread.ident is not None:
            self.thread.join(30)


def crashed(told, error):
    """The record of an attempt whose helper raised: the attempt the trigger kept, still ``underway`` (so it holds and
    ends as an attempt whose helper died always has), with ``cause`` ``helper_crash`` and the error as its ``detail``;
    None where the record is not that attempt's."""
    try:
        with open(told["record"], encoding="utf-8") as handle:
            found = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or found.get("at") != told.get("at") or found.get("outcome") != "underway":
        return None
    return {**found, "cause": "helper_crash", "detail": f"{type(error).__name__}: {error}"}


def main(told):
    """The update ``told`` asks for, beating as it runs (``Beat``), its record kept where it is still this attempt's
    (``ours``); where the helper itself raises, the attempt kept as it was, marked ``helper_crash`` (``crashed``), and
    the error written to the log."""
    beat = Beat(told)
    try:
        found = update(told)
    except Exception as error:  # noqa: BLE001 - said in the record, never a silent end
        try:
            import traceback

            Log(told.get("log")).write("the helper stopped with an error:\n" + traceback.format_exc())
            found = crashed(told, error)
        except Exception:  # noqa: BLE001 - nothing more to say: the attempt stays as the trigger kept it
            found = None
    beat.stop()
    if found is not None and ours(told):
        keep(told["record"], found)


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
