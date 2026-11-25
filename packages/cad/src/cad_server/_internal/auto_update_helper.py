"""cad's own update, carried out: the worker ``auto_update.trigger`` starts, detached and with no window, as ``python -P
-m cad_server._internal.auto_update_helper <told>`` by the environment's own interpreter, so it runs the release that
is current, whose files nothing changes. ``told`` is one JSON argument: ``record`` (the attempt's file), ``log``,
``from`` (the release that runs), ``at``, ``tries``, ``wanted``, ``asked``, ``major``, ``start`` (a server wanted at the
end though none runs), ``target`` (the release asked for, or null), ``requirement`` (what uv builds: ``cad==<target>``;
with no target the bound of ``from``'s major, or for ``major`` its floor alone), ``cad`` (the environment's own ``cad``
command), ``uv`` (the uv it builds with) and ``installer`` (who made the environment, kept in the record).

In order (``update``):

1. **Build** (the record's ``phase``: ``building``, kept as uv builds). Where the environment runs ``target`` or newer
   already (``store.active``: another update got there first), nothing is built: outcome ``current``, and a server of
   an older release, or of another environment, is replaced by this one's (``replace``). Else the stored release
   ``target`` where it is there and runs (``store.sound``: run once now, since another Python may have built it, or a
   file of it be gone), or the requirement built and run once in a folder of the store (``store.build``,
   ``store.verify``) and judged: never older than ``from`` and, but for ``major``, of ``from``'s major
   (``accepted``); ``from`` itself is ``current``, nothing newer; then named (``store.publish``, which removes a
   stored release of that name that no longer runs). Nothing that runs is touched, so a failure here leaves cad as it
   was. A resumed attempt (its record kept as ``switching``, ``auto_update._claim``) finds its stored release this
   way, and builds it again only where it no longer runs.
2. **Ready, or on** (``settle``): in one step under the state folder's lock, where the record is still this
   attempt's, underway, and says ``"switch": false``, the attempt ends here, outcome ``ready``: the release stored and
   checked, nothing pointing at it, and the store's tidying keeps it. Else, a person's ask during the build included
   (the record's ``asked``), on to the switch.
3. **Switch** (``phase``: ``switching``, kept before anything stops; while it lasts a server of the release being
   left starts none in the next one's place, ``auto_update.leaving``). The pointer read as it is, for the way back.
   Where a server answers, it is asked to stop once nothing is in flight, and waited for (``client.drain``,
   ``DRAIN_SECONDS``); one still there after them is replaced by the new release's start all the same, its work cut
   short. Then the environment pointed at the release (``store.point``) and the release run: ``cad server start`` where
   a server ran or ``start`` asks for one, which must end 0 with a server whose greeting names the release; else ``cad
   --version``, which must say it.
4. **Way back** (``phase``: ``restoring``). Where that fails, the pointer put back exactly as it was read
   (``store.restore``), a server of another release that answers by then stopped (``clear``: the new release's, come
   up late), and the server of the release before started where one is wanted: outcome ``failed``, cause
   ``start_failed`` (the server) or ``broken`` (the command), ``restored`` whether the release before runs again.
   Where it is the pointer that could not be written, nothing was switched: the same way back, and the cause is the
   write's (``denied``, ``disk_full``), which the schedule tries again.
5. **Outcome**, kept in the record: ``installed``, ``current`` or ``failed``, with ``detail``, ``cause`` where it did
   not install what it was for (one of ``CAUSES``), ``restored``, and ``started`` (``"start": false`` where no server
   was wanted) -- or ``ready``, kept as step 2 decided it; then the store tidied (``store.clean``), the release built
   kept where it was installed or is ready.

No step is tried twice in a run: the schedule tries a failed release again (``auto_update.next_try``). uv stopped at
its deadline leaves only a folder that is no release yet. Why a build failed is told from uv's words (``cause_of``:
its exit status, all it printed, the system's error, and which of uv's settings are there, by name alone). As it runs
the worker writes the time into the record every ``BEAT_SECONDS`` (``Beat``), by which the server tells it is
underway, never over another attempt's record, and, as every write of the record that another process may make at
the same moment, under the state folder's lock (``held``: done without it where it cannot be taken); where it
raises, the attempt stays underway, marked ``helper_crash`` (``main``). Each command it runs, its exit status, how
long it took and the end of what it printed go to the log (``Log``), which stays on the computer; neither the log nor
the cause can stop the update. It counts nothing and runs no install command: the server that runs after it does
both (``auto_update.report``, ``plugin_catch_up``).
"""

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW: no console flashes for uv or cad
# How often the worker marks its attempt as still underway (``Beat``): well inside ``auto_update.LOST_SECONDS``.
BEAT_SECONDS = 60
# How long a server is given to end what is in flight before the switch goes on without it.
DRAIN_SECONDS = 600.0
# How long ``cad server start`` and ``cad --version`` may take, and a question to the server.
RUN_SECONDS, ASK_SECONDS = 120.0, 30.0


def release(text):
    """``X.Y.Z`` as three numbers, or None."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def named(held):
    return ".".join(map(str, held))


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


def accepted(held, before, major):
    """Whether the update may end on release ``held``: never older than ``before``, the release that ran, and, but for
    ``major`` (``cad update --major``), of ``before``'s major. Any release where ``before`` is not known."""
    if held is None:
        return False
    return before is None or (held >= before and (major or held[0] == before[0]))


def update(told, run=run, mark=lambda phase: None):
    """The update ``told`` asks for (see the module); its outcome as the record keeps it. ``mark``: the record's phase
    kept (``Beat.mark``)."""
    from cad_server._internal import store

    log = Log(told.get("log"))
    log.begin(told)
    run = log.running(run)
    before, target = release(told["from"]), release(told.get("target"))
    held = release(store.active())
    built = None
    if held is not None and before is not None and (held >= target if target is not None else held > before):
        found = {"release": named(held), "outcome": "current", "detail": f"cad {named(held)} is installed",
                 **replace(told, run, named(held), log, mark)}
    else:
        found = build(told, run, log, mark)
        built = found.pop("path", None)
        if built is not None:
            done, asked = settle(told, found, built)
            if done is not None:
                found = done
            else:
                told = {**told, "asked": asked}
                mark("switching")
                found = switch(told, run, built, found, log, mark)
    store.clean(keep=[built] if found["outcome"] in ("installed", "ready") else [])
    if found["outcome"] != "ready":
        found = {**found, "from": told["from"], "at": told["at"], "tries": told.get("tries", 1), "ended": time.time(),
                 **{name: told[name] for name in ("installer", "wanted", "asked", "major") if name in told}}
    log.end(found)
    return found


def settle(told, found, path):
    """Once the build gave a stored release (``found``: its ``release``, at ``path``), the one step, under the state
    folder's lock, that decides whether the attempt goes on to the switch. Where the record is still this attempt's,
    underway, and says ``"switch": false`` (the server's own, getting the release ready alone), the attempt ends there:
    its outcome ``ready`` kept whole in that same step, as ``update`` composes every outcome, so the beat writes nothing
    after it and no ask can fall between the look and the write: ``(that outcome, False)``. Else ``(None, asked)``:
    the switch, as a person's where the record says so now (a person's ask during the build made the attempt theirs:
    ``auto_update._claim``), as the worker was told where the record is not this attempt's."""
    with held(told):
        kept = _read(told)
        if kept is None or kept.get("outcome") != "underway":
            return None, told.get("asked") is True
        if kept.get("switch") is not False:
            return None, kept.get("asked") is True
        done = {**found, "outcome": "ready", "switch": False,
                "detail": f"cad {found['release']} is ready in {path}, and nothing points at it yet",
                "from": told["from"], "at": told["at"], "tries": told.get("tries", 1), "ended": time.time(),
                **{name: told[name] for name in ("installer", "wanted", "major") if name in told}, "asked": False}
        keep(told["record"], done)
    return done, False


def build(told, run, log, mark=lambda phase: None):
    """Step 1 (see the module): ``{"path", "release"}``, the stored release to switch to; else how the attempt ended.
    The phase ``building`` kept (``mark``) only where uv builds: a resumed attempt, kept as ``switching``, says so
    only where its stored release no longer runs."""
    from cad_server._internal import store

    before, major, target = release(told["from"]), told.get("major") is True, told.get("target")
    path = store.folder(target) if release(target) is not None else None
    if path is not None and store.sound(path, run=run):
        return {"path": path, "release": target}
    mark("building")
    wanted = target or "latest"
    try:
        staged = store.build(told["requirement"], uv=told["uv"], run=run)
        got = store.verify(staged, run=run)
    except store.Failed as failed:
        said = last_line(failed.output)
        if failed.step == "verify":
            return {"release": wanted, "outcome": "failed", "cause": "broken",
                    "detail": f"the release built did not run: {said or f'exit {failed.code}'}"}
        return {"release": wanted, "outcome": "failed", "cause": cause_of(failed.code, failed.output, log),
                "detail": said or "uv said nothing"}
    if not accepted(release(got), before, major):
        store.remove(staged)
        return {"release": got, "outcome": "failed", "cause": "unknown",
                "detail": f"it built cad {got}, which it may not end on"}
    if release(got) == before:
        store.remove(staged)
        return {"release": got, "outcome": "current", "detail": f"cad {got} is the newest release it may take"}
    try:
        return {"path": store.publish(staged, got, run=run), "release": got}
    except OSError as error:
        store.remove(staged)
        said = f"{type(error).__name__}: {error}"
        return {"release": got, "outcome": "failed", "cause": cause_of(None, said, log), "detail": said}


def answering():
    """The server that answers now: ``(its release, the environment it runs from)``, either None where it does not
    say; or None where none answers."""
    from cad.engine import client

    try:
        connection = client._connect()  # noqa: SLF001 - any release
    except ConnectionError:
        return None
    if connection is None:
        return None
    try:
        status = client._within(ASK_SECONDS, lambda: client._exchange(  # noqa: SLF001
            connection, {"op": "status", "internal": True}))
    except (ConnectionError, OSError, ValueError):
        status = None
    return connection.release, status.get("prefix") if isinstance(status, dict) else None


def drain(server, log):
    """The server that answers stopped once nothing is in flight, waited for ``DRAIN_SECONDS`` at most, and that
    written to the log; one still there is replaced by the next start, its work cut short."""
    from cad.engine import client

    began = time.monotonic()
    try:
        gone = client.drain(DRAIN_SECONDS)
    except ConnectionError as error:
        gone = False
        log.write(f"the server could not be asked to stop: {error}")
    log.write(f"the cad server {server[0] or ''} asked to stop once nothing is in flight: "
              + (f"gone after {time.monotonic() - began:.1f} s" if gone else
                 "still there, and the next start replaces it"))


def runs(told, run, wanted, server):
    """Whether release ``wanted`` runs now, by the environment's ``cad`` command: ``cad server start``, ending 0 with a
    server whose greeting names it (``server``); else ``cad --version`` saying it. ``(whether it does, what was
    said)``."""
    if not server:
        code, said = run([told["cad"], "--version"], RUN_SECONDS)
        return code == 0 and last_line(said) == f"cad {wanted}", said
    code, said = run([told["cad"], "server", "start"], RUN_SECONDS)
    found = answering() if code == 0 else None
    return found is not None and found[0] == wanted, said


def started(wanted, ok, said):
    """The record's word for the server: ``started``, the start's last line (``not started: ...`` where it failed), or
    ``"start": false`` where none was ``wanted``."""
    if not wanted:
        return {"start": False}
    return {"started": last_line(said) if ok else f"not started: {last_line(said) or 'no server answered'}"}


def switch(told, run, path, built, log, mark=lambda phase: None):
    """Steps 3 and 4 (see the module): the environment switched to the stored release at ``path`` (``built``: its
    ``release``), and back where it does not run (the record's phase ``restoring`` kept first, ``mark``: the release
    before is the one to start again)."""
    from cad_server._internal import store

    kept = store.pointer()
    previous = (store.pointed() or {}).get("path")
    server = answering()
    if server is not None:
        drain(server, log)
    wanted = server is not None or told.get("start") is True
    unwritten = None  # the pointer's own failure: nothing was switched
    try:
        store.point(path, previous=previous)
    except OSError as error:
        unwritten = f"{type(error).__name__}: {error}"
    ok, said = (False, unwritten) if unwritten else runs(told, run, built["release"], wanted)
    if ok:
        return {**built, "outcome": "installed", "detail": f"cad {built['release']} runs from {path}",
                **started(wanted, True, said)}
    mark("restoring")
    try:
        store.restore(kept)
        clear(told["from"], log)
        back, again = runs(told, run, told["from"], wanted)
    except OSError as error:
        back, again = False, f"the pointer could not be put back: {type(error).__name__}: {error}"
    if unwritten:
        cause, detail = cause_of(None, unwritten, log), f"the pointer could not be written: {unwritten}"
    else:
        cause = "start_failed" if wanted else "broken"
        detail = f"cad {built['release']} did not {'start' if wanted else 'run'}: {last_line(said) or 'no word'}"
    return {**built, "outcome": "failed", "cause": cause, "restored": back, "detail": detail,
            **started(wanted, back, again)}


def clear(before, log):
    """On the way back: a server of another release than ``before`` that answers now -- the new release's, come up
    after its start was given up on -- stopped at once. Left there, every command of ``before``, which the environment
    runs again, would be refused as one of another release, and a start of ``before`` would join it and replace
    nothing. Never raises."""
    from cad.engine import client

    try:
        found = answering()
        if found is None or found[0] == before:
            return
        client.sweep(stop=True, seconds=RUN_SECONDS)
        log.write(f"the cad server {found[0] or ''} that answered after the switch failed was stopped")
    except Exception as error:  # noqa: BLE001 - the way back goes on: the start of the release before says what is there
        log.write(f"a server that answered after the switch failed could not be stopped: {type(error).__name__}: {error}")


def replace(told, run, held, log, mark=lambda phase: None):
    """Where the environment runs release ``held`` already: a server of an older release, or one of ``held`` from
    another environment (a copy the bridge hands over from), drained and replaced by this environment's (the record's
    phase ``switching`` kept first, ``mark``, so a command that finds no server meanwhile waits for the next); else,
    where none answers and ``start`` asks for one, one started. The record's word for the server."""
    from cad.engine.client import newer

    server = answering()
    here = os.path.normcase(os.path.realpath(sys.prefix))
    elsewhere = server is not None and isinstance(server[1], str) \
        and os.path.normcase(os.path.realpath(server[1])) != here
    if server is not None and not (server[0] is None or newer(held, server[0]) or server[0] == held and elsewhere):
        return {}
    if server is None and told.get("start") is not True:
        return {"start": False}
    mark("switching")
    if server is not None:
        drain(server, log)
    ok, said = runs(told, run, held, True)
    return started(True, ok, said)


# --- why an attempt did not install what it was for: one word ------------------------------------------------------

# Every word a record's ``cause`` holds, a closed list. The worker tells most of them: from uv's words where the build
# failed (``cause_of``), ``broken`` where the release built did not run, ``start_failed`` where its server did not
# start; ``helper_start`` is the trigger's (its worker could not start), ``lost`` a reader's (an attempt still
# underway and silent), ``no_installer`` and ``no_switch`` the reasons none begins (``auto_update.blocked``);
# ``packaged`` (cad inside a Windows app's private copy of AppData) is kept for the check that tells it. Each word is
# said in plain words by ``auto_update.SAID``.
CAUSES = ("timeout", "no_program", "in_use", "denied", "disk_full", "network", "offline", "no_release", "python",
          "platform", "config_exclude", "config_index", "config_tls", "broken", "start_failed", "helper_start",
          "helper_crash", "lost", "no_installer", "no_switch", "packaged", "unknown")

# What uv's output says, tried in order, the first match winning: uv's own words, and the system's for an error of the
# file system (``os error N`` is uv's spelling, ``[Errno N]`` and ``[WinError N]`` Python's). Read with each run of
# white space made one space: uv wraps its messages.
SAYS = (
    ("in_use", (r"os error 32\b", r"WinError 32\b", r"being used by another process", r"os error 16\b",
                r"resource busy", r"text file busy", r"os error 26\b")),
    ("disk_full", (r"os error 28\b", r"Errno 28\b", r"os error 112\b", r"WinError 112\b", r"no space left on device",
                   r"not enough space on the disk", r"disk quota exceeded", r"os error 122\b")),
    ("offline", (r"network was disabled", r"network is disabled")),
    ("network", (r"failed to fetch", r"error sending request", r"dns error", r"tcp connect", r"connection refused",
                 r"connection reset", r"timed out", r"tunnel error", r"certificate", r"failed to establish",
                 r"could not connect", r"name resolution", r"name or service not known", r"no such host is known",
                 r"network is unreachable", r"request failed after \d+ retr")),
    ("denied", (r"os error 5\b", r"WinError 5\b", r"access is denied", r"permission denied", r"os error 13\b",
                r"Errno 13\b", r"operation not permitted")),
    ("python", (r"requires Python", r"requires a different Python", r"require a different python version",
                r"Requires-Python")),
    ("platform", (r"no wheels with a matching", r"platform tag", r"ABI tag", r"implementation tag")),
    ("no_release", (r"no solution found when resolving", r"not found in the package registry", r"no version of cad",
                    r"requirements are unsatisfiable")),
)
_SAYS = tuple((word, re.compile("|".join(patterns), re.IGNORECASE)) for word, patterns in SAYS)
# Where an index's words name PyPI's own hosts, a network failure is the network's, whatever index a setting adds.
PYPI_HOSTS = re.compile(r"pypi\.org|pythonhosted\.org", re.IGNORECASE)
TLS_WORDS = re.compile(r"certificate|SSL|TLS", re.IGNORECASE)


def classify(code, output):
    """The cause a run says, from its exit status and all it printed (``run``'s): ``timeout`` and ``no_program`` where
    it did not end or could not start, else the first of ``SAYS`` its words match, else ``unknown``. None where it
    ended 0."""
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


# uv's settings that decide what it can reach or take, by name (``settings``): its environment variables and the keys
# of its ``uv.toml``. Read for whether they are there, never for what they hold.
SETTINGS = {
    "config_exclude": ("UV_EXCLUDE_NEWER", "exclude-newer", "exclude-newer-package"),
    "config_index": ("UV_INDEX", "UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "UV_FIND_LINKS",
                     "UV_NO_INDEX", "UV_INDEX_STRATEGY", "index", "index-url", "extra-index-url", "find-links",
                     "no-index", "index-strategy"),
    "config_tls": ("UV_NATIVE_TLS", "UV_SYSTEM_CERTS", "UV_INSECURE_HOST", "SSL_CERT_FILE", "SSL_CERT_DIR",
                   "native-tls", "system-certs", "allow-insecure-host"),
    "offline": ("UV_OFFLINE", "offline"),
}
UV_SYSTEM = ("/etc/uv/uv.toml",)  # uv's system-wide settings beside ``$XDG_CONFIG_DIRS``'s, on Linux and macOS


def setting_files(environ, windows=WINDOWS):
    """The ``uv.toml`` files uv reads its settings from, where they are: ``UV_CONFIG_FILE`` alone where it is set, none
    where ``UV_NO_CONFIG`` is, else the person's and the system's."""
    if environ.get("UV_NO_CONFIG"):
        return []
    home = Path(environ.get("USERPROFILE" if windows else "HOME") or Path.home())
    config = Path(environ.get("XDG_CONFIG_HOME") or home / ".config")
    if environ.get("UV_CONFIG_FILE"):
        found = [Path(environ["UV_CONFIG_FILE"])]
    elif windows:
        found = [Path(environ[name]) / "uv" / "uv.toml" for name in ("APPDATA", "PROGRAMDATA") if environ.get(name)]
    else:
        system = [Path(folder) for folder in (environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":") if folder]
        found = [config / "uv" / "uv.toml", *(folder / "uv" / "uv.toml" for folder in system), *map(Path, UV_SYSTEM)]
    return [path for path in found if path.is_file()]


def _keys(path):
    """The names of the settings a ``uv.toml`` holds (its top-level keys: ``[[index]]`` is ``index``); none where it
    cannot be read."""
    try:
        import tomllib

        return set(tomllib.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a file that cannot be read holds nothing that is known
        return set()


def settings(environ=None, windows=WINDOWS):
    """Which of ``SETTINGS`` uv has, by the cause each can bring: ``{cause: [the names found]}``, an environment
    variable by its name, a file's key as ``<key> (<file>)``. Never a value."""
    environ = os.environ if environ is None else environ
    files = [(path, _keys(path)) for path in setting_files(environ, windows)]
    found = {}
    for cause, names in SETTINGS.items():
        hits = [name for name in names if name.isupper() and environ.get(name) is not None]
        hits += [f"{name} ({path})" for path, keys in files for name in names if not name.isupper() and name in keys]
        if hits:
            found[cause] = hits
    return found


def refine(cause, output, found):
    """A cause uv's settings explain better (``found``: ``settings``): a network failure where a TLS setting is there
    and the words are of a certificate, ``config_tls``; one of an index other than PyPI's where an index setting is
    there, ``config_index``; a release not found where a setting hides newer releases, ``config_exclude``, or adds an
    index, ``config_index``; either where uv is set offline, ``offline``."""
    text = output or ""
    if cause == "network":
        if "config_tls" in found and TLS_WORDS.search(text):
            return "config_tls"
        if "config_index" in found and not PYPI_HOSTS.search(text):
            return "config_index"
    if cause in ("no_release", "network") and "offline" in found:
        return "offline"
    if cause == "no_release":
        for setting in ("config_exclude", "config_index"):
            if setting in found:
                return setting
    return cause


def cause_of(code, output, log=None, environ=None):
    """Why a build failed, one of ``CAUSES``: what uv's exit status and words say (``classify``), then what its
    settings explain (``refine``), whose names are written to the log."""
    found = settings(environ)
    if found and log is not None:
        log.write("uv's settings found (names only): " + "; ".join(
            f"{name}: {', '.join(names)}" for name, names in sorted(found.items())))
    return refine(classify(code, output), output, found)


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
        except Exception:  # noqa: BLE001 - the worker never fails of its log
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
                             f"{f' (for {wanted})' if wanted and wanted != told.get('target') else ''}, "
                             f"{told.get('requirement')} built by {told.get('uv')}, "
                             f"{'typed' if told.get('asked') else 'automatic'}"
                             f"{', --major' if told.get('major') else ''}, try {told.get('tries', 1)}\n")
        except Exception:  # noqa: BLE001 - the worker never fails of its log
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
        except Exception:  # noqa: BLE001 - the worker never fails of its log
            pass

    def end(self, found):
        self.write(f"ended {_when(found.get('ended') or time.time())}: {found.get('outcome')}"
                   + (f", the cause: {found['cause']}" if found.get("cause") else "")
                   + (f"; {found['detail']}" if found.get("detail") else ""))


def _when(at):
    return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(at))


def keep(path, record):
    """``record`` written whole in place of ``path`` (``auto_update._keep``). Never raises: the worker never dies of its
    record."""
    from cad_server._internal.auto_update import _keep

    try:
        _keep(Path(path), record)
    except OSError:
        pass


def _record(told):
    """The record at ``told["record"]``, or None where there is none to read."""
    try:
        with open(told["record"], encoding="utf-8") as handle:
            found = json.load(handle)
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _read(told):
    """The record where it is this attempt's (its ``at``), else None."""
    found = _record(told)
    return found if found is not None and found.get("at") == told.get("at") else None


@contextlib.contextmanager
def held(told):
    """The state folder's lock (``file_lock.state``, in the record's folder) held for one read-change-write of the
    record, as every writer of it holds it. Where the lock cannot be taken -- its file cannot be opened, the system's
    lock call fails -- the step is done without it: a rare race is better than an attempt that dies of its lock, and
    the worker never dies of its record (``keep``). Only the taking is forgiven, never an error of the step itself."""
    from cad_server._internal.file_lock import state

    try:
        lock = state(Path(told["record"]).parent)
        lock.__enter__()
    except Exception:  # noqa: BLE001 - see above
        lock = None
    try:
        yield
    finally:
        if lock is not None:
            lock.__exit__(None, None, None)


def ours(told):
    """Whether the record is still this attempt's (its ``at``), or there is none to read: an attempt begun since, by a
    process that took this one for lost, keeps it, and this one was counted ``lost`` as that began."""
    found = _record(told)
    return found is None or found.get("at") == told.get("at")


class Beat:
    """The attempt marked as still underway every ``BEAT_SECONDS`` as the worker runs (its record's ``beat``), from a
    thread of its own, so a command that runs for minutes beats too; only while the record is this attempt's and
    underway. ``mark(phase)`` keeps the phase too, under the same lock, so a beat never writes an older one back.
    ``stop()``: no beat after it, so the outcome is the record's last word. Never raises."""

    def __init__(self, told, every=BEAT_SECONDS):
        self.told, self.every, self.done, self.lock = told, every, threading.Event(), threading.Lock()
        self.thread = threading.Thread(target=self.run, name="cad-update-beat", daemon=True)
        try:
            self.thread.start()
        except RuntimeError:  # no thread to be had: the update runs all the same, lost should it outlast the wait
            pass

    def run(self):
        while not self.done.wait(self.every):
            self.mark()

    def mark(self, phase=None):
        """One beat: the record's ``beat`` now (and its ``phase``), where the record is this attempt's and underway,
        read, changed and written under the state folder's lock, as every writer of the record does: a beat read before
        a person's ask changed the record (``auto_update._claim``) never writes the old one back over it."""
        try:
            with self.lock, held(self.told):
                found = _read(self.told)
                if found is not None and found.get("outcome") == "underway":
                    keep(self.told["record"], {**found, "beat": time.time(), **({"phase": phase} if phase else {})})
        except Exception:  # noqa: BLE001 - a beat missed is one minute nearer lost, nothing more
            pass

    def stop(self):
        self.done.set()
        if self.thread.ident is not None:
            self.thread.join(30)


def crashed(told, error):
    """The record of an attempt whose worker raised: the attempt as the trigger kept it, still ``underway`` (so it holds
    and ends as an attempt whose worker died always has), with ``cause`` ``helper_crash`` and the error as its
    ``detail``; None where the record is not that attempt's."""
    found = _read(told)
    if found is None or found.get("outcome") != "underway":
        return None
    return {**found, "cause": "helper_crash", "detail": f"{type(error).__name__}: {error}"}


def main(told):
    """The update ``told`` asks for, beating as it runs (``Beat``), its record kept where it is still this attempt's
    (``ours``), under the state folder's lock, ``asked`` where the record says a person asked since; where the worker
    itself raises, the attempt kept as it was, marked ``helper_crash`` (``crashed``), and the error written to the log.
    A ``ready`` outcome is written once, as it is decided (``settle``), and never again: not over the sitting that
    resumed it since, whose ``at`` is its own."""
    beat = Beat(told)
    try:
        found = update(told, mark=beat.mark)
    except Exception as error:  # noqa: BLE001 - said in the record, never a silent end
        try:
            import traceback

            Log(told.get("log")).write("the worker stopped with an error:\n" + traceback.format_exc())
            found = crashed(told, error)
        except Exception:  # noqa: BLE001 - nothing more to say: the attempt stays as the trigger kept it
            found = None
    beat.stop()
    if found is None or found.get("outcome") == "ready":
        return
    with held(told):
        kept = _record(told)
        if kept is None or kept.get("at") == told.get("at"):  # ``ours``
            asked = kept is not None and kept.get("asked") is True and found.get("asked") is not True
            keep(told["record"], {**found, **({"asked": True} if asked else {})})


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
