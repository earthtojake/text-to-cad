"""cad's own update, carried out by the release it updates to: the worker ``auto_update.trigger`` starts, detached, with
no window and outside any Windows app package (``places.outside_package``), from that release in uv's cache, never from
the environment it replaces: ``uv tool run --isolated --managed-python --python 3.14 --from "cad==<release>" python -P
-m cad_server._internal.auto_update_helper <told>`` (``auto_update.from_cache``, ``auto_update.HELPER``), uv having
built that environment first (``auto_update.build``). So the newest release's code always does the update, and the
worker holds none of the environment's files. That entry and ``told`` are a contract every later release keeps: an
older release starts a newer one's worker by them. ``told`` is one JSON argument: ``record`` (the attempt's file),
``log``, ``from`` (the release that runs), ``at``, ``tries``, ``wanted``, ``asked``, ``start`` (a server wanted at the
end though none runs), ``target`` (the release asked for, or null), ``requirement`` (what is installed:
``cad==<target>``; with no target the bound of ``from``'s major), ``prefix`` (the environment updated), ``cad`` (its
own ``cad`` command), ``installer`` (``uv`` or ``pipx``, who made the global install, kept in the record), ``uv`` (the
person's uv, ``base.find_uv``), ``pipx`` (pipx's command, ``auto_update.find_pipx``, for a pipx install) and ``spare``
(on Windows, the processes the switch leaves running: ``auto_update.spared``). Every record it writes keeps the fields
the release that started it reads, and adds ``worker``, its own release.

The installer that made cad updates it where it is, with the person's own settings: uv by ``uv tool upgrade``, its
receipt untouched; pipx by pip inside its environment (``pipx runpip cad install``; ``uv pip`` under pipx's uv backend),
pipx's pin untouched (``installing``). On Windows a file a process has open or loaded cannot be deleted: uv's upgrade
deletes the old files in the order of the package's ``RECORD`` and stops at the first it cannot delete, with nothing
put back, and one stopped past the ``RECORD`` leaves a ``cad-*.dist-info`` without it that every later uv run fails on
(pip puts back what it removed). Either downloads and prepares the release before it changes the environment, so a
download that fails leaves cad as it was. What follows is what makes the upgrade safe where processes run cad, and
repairs it where it fails anyway. In order (``update``):

1. **Current**: where the environment holds ``target`` or newer already (``auto_update.installed``: another update
   got there first), nothing is upgraded: outcome ``current``, and a server of an older release, or of another
   environment, is replaced by this one's (``replace``). The bridge's hand-over is this step, by the environment's
   own interpreter (``cli.setup.move``).
2. **Switch** (``switch``; the record's ``phase`` is ``switching`` from its claim: while it lasts a server of the
   release being left starts none, ``auto_update.leaving``):

   a. Refused, nothing touched: on Windows inside an app package (``places.packaged``), cause ``packaged``; run from
      the environment it would replace, cause ``helper_start``.
   b. The server that answers stopped at once, as ``cad server stop`` stops it (``stop``).
   c. On Windows, the installer's bin ``cad.exe`` (``tool_command``: uv's, or the copy pipx exposes) moved aside, so a
      new ``cad`` fails at once rather than open the files being replaced; then every other process running from the
      environment stopped, but those spared, and looked for again until none is left (``stop_environment``). In that
      order: a ``cad`` launched between a sweep and the rename would hold the files being replaced.
   d. The installer's upgrade to ``requirement`` (``installing``): the release it leaves is the one installed
      (``auto_update.installed``); ``from`` itself is ``current``. uv's own failure to write the bin ``cad.exe`` (a file
      in use) leaves the environment upgraded and whole: that is checked as an upgrade.
   e. The moment the installer returns, its bin ``cad`` again where it left none (``command_back``: an upgrade uv
      fails after it took the tool's commands out leaves none, ``--reinstall`` makes none, and pip writes none
      there): on Windows the environment's own ``cad.exe`` copied there, as pipx exposes it, else the one moved aside
      put back, and the one moved aside removed where it can be (else the server's next tidying does,
      ``auto_update.tidy``); elsewhere a link to the environment's own, as uv and pipx make it.
   f. A server of another release that came up meanwhile stopped (``clear``), and the release checked (``runs``):
      ``cad server start`` where a server ran or ``start`` asks for one, ending 0 with a server whose greeting names
      it; else ``cad --version`` saying it.
   g. Where d or f failed, the repair in place (``recover``): where nothing changed and the release before runs as it
      is, that; else each ``*.dist-info`` without its ``RECORD`` deleted and the release installed again
      (``installing``: ``uv tool upgrade --reinstall``, ``pipx runpip cad install --force-reinstall``), then the
      release before, each made safe as d is (c, e) and checked. It keeps uv's receipt and pipx's pin.
   h. Where that left no cad that runs, the last resort (``reinstall``): the installer installs cad again whole
      (``uv tool install --force "cad<N>"``, ``pipx install --force cad``), which removes the environment, so nothing
      of it may run: the record's phase ``repairing`` first, on which the processes the switch spared leave it (the
      ``cad update`` that waits says cad is being installed again, and ends), waited for (``WAIT_SECONDS`` at most),
      then every process of it stopped (c), the folders without their ``RECORD`` deleted, the install, e, and the
      release that runs checked (f).

3. **Outcome**, kept in the record: ``installed``, ``current`` or ``failed``, with ``detail``, ``cause`` where it did
   not install what it was for (one of ``CAUSES``: the installer's first error where the upgrade failed, ``why`` and
   ``cause_of``, never a later rollback's; ``cad_running`` where a process of cad's the sweep could not stop held a
   file; ``start_failed`` where the release did not start and the one before runs again; ``broken`` where neither
   runs),
   ``restored`` (whether the release before runs again), ``started`` (``"start": false`` where no server was
   wanted) and ``worker``.
No step is tried twice in a run: the schedule tries a failed release again (``auto_update.next_try``). As it runs the
worker writes the time into the record every ``BEAT_SECONDS`` (``Beat``), by which the server tells it is underway,
never over another attempt's record, and, as every write of the record that another process may make at the same
moment, under the state folder's lock (``held``: done without it where it cannot be taken); where it raises, the
attempt stays underway, marked ``helper_crash`` (``main``). Each command it runs, its exit status, how long it took and
the end of what it printed go to the log (``Log``), which stays on the computer; neither the log nor the cause can stop
the update. It counts nothing and runs no install command: the server that runs after it does both
(``auto_update.report``, ``plugin_catch_up``).
"""

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import traceback
from pathlib import Path

from cad.engine import client, places
from cad_server._internal import auto_update, file_lock, tool_install

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW: no console flashes for uv or cad
# How often the worker marks its attempt as still underway (``Beat``): well inside ``auto_update.LOST_SECONDS``.
BEAT_SECONDS = 60
# How long a server stopped at the switch is waited for until it is gone, as ``cad server stop`` waits (``client.sweep``'s
# own bound). It is stopped at once: what is in flight is cut short, and its command says cad updated itself while it
# ran.
STOP_SECONDS = 60.0
# How long ``cad server start`` and ``cad --version`` may take, and a question to the server.
RUN_SECONDS, ASK_SECONDS = 120.0, 30.0
# How long the processes the switch stops on Windows are waited for until they are gone, each round, and how many
# times they are looked for, until none is left.
END_SECONDS, ROUNDS = 15.0, 5
# How long the processes the switch spared are waited for to leave the environment before it is installed again
# (``reinstall``), and how often they are looked for.
WAIT_SECONDS, LOOK_SECONDS = 60.0, 0.2
# The name the installer's bin ``cad.exe`` is given as it is moved aside (``aside``), in its folder: a new ``cad`` fails
# at once meanwhile, rather than open the files being replaced; and the files of that name the server's tidying removes
# (``auto_update.tidy``), one a process still ran then.
ASIDE = ".cad-{pid}.exe.old"


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


def why(text):
    """Why an installer's run failed, in its own words: its first ``error:`` line with the ``Caused by:`` lines under
    it, after each warning before it that names a file it could not remove or replace (``FILE_WORDS``); else its last
    line. uv's rollback of a failed install prints an error of its own last, which says nothing of the first."""
    return first_error(text) or last_line(text)


# A warning that names a file the installer could not act on (``first_error``).
FILE_WORDS = re.compile(r"os error \d+|WinError \d+|failed to (remove|replace|rename|write|copy|open)", re.IGNORECASE)


def first_error(text):
    """The installer's first error as ``why`` says it, at most 1000 characters; "" where it printed no ``error:``
    line."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    first = next((n for n, line in enumerate(lines) if line.lower().startswith("error:")), None)
    if first is None:
        return ""
    said = [line for line in lines[:first] if line.lower().startswith("warn") and FILE_WORDS.search(line)]
    said.append(lines[first])
    for line in lines[first + 1:]:
        if not line.lower().startswith("caused by:"):
            break
        said.append(line)
    return " ".join(said)[:1000]


def update(told, run=run, mark=lambda phase: None):
    """The update ``told`` asks for (see the module); its outcome as the record keeps it. ``mark``: the record's phase
    kept (``Beat.mark``)."""
    log = Log(told.get("log"))
    log.begin(told)
    run = log.running(run)
    before, target = release(told["from"]), release(told.get("target"))
    held = release(auto_update.installed(told["prefix"]))
    if held is not None and before is not None and (held >= target if target is not None else held > before):
        found = {"release": named(held), "outcome": "current", "detail": f"cad {named(held)} is installed",
                 **replace(told, run, named(held), log, mark)}
    else:
        found = switch(told, run, log, mark=mark)
    found = {**found, "from": told["from"], "at": told["at"], "tries": told.get("tries", 1), "ended": time.time(),
             "worker": auto_update._version(),  # noqa: SLF001
             **{name: told[name] for name in ("installer", "wanted", "asked") if name in told}}
    log.end(found)
    return found


def installer(told):
    """The installer's command as the worker runs it: uv, or pipx (``find_pipx``'s)."""
    return " ".join(map(str, told.get("pipx") or ())) if told.get("installer") == "pipx" else told.get("uv")


def by(told):
    """Who installs cad, as the log and the detail name it: ``uv`` or ``pipx``."""
    return "pipx" if told.get("installer") == "pipx" else "uv"


def answering():
    """The server that answers now: ``(its release, the environment it runs from)``, either None where it does not
    say; or None where none answers."""
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


def stop(server, log):
    """The server that answers stopped at once (``{"op": "stop"}``, as ``cad server stop`` stops it: ``client.sweep``,
    which notes the port it serves pages on first, for the next server), and waited for until it is gone,
    ``STOP_SECONDS`` at most; that written to the log. One still there is replaced by the next start."""
    began = time.monotonic()
    try:
        client.sweep(stop=True, seconds=STOP_SECONDS)
        gone = True
    except ConnectionError as error:
        gone = False
        log.write(f"the server could not be stopped: {error}")
    log.write(f"the cad server {server[0] or ''} stopped: "
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


def same(one, other):
    """Whether the paths ``one`` and ``other`` name the same folder."""
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def switch(told, run, log, system=None, mark=lambda phase: None):
    """Step 2 (see the module): the environment upgraded in place to ``target`` (with none named, the newest the
    requirement allows), checked, and repaired where that fails. ``system``: Windows' process calls (``Windows``; a
    test's stand-in); ``mark``: the record's phase kept (``Beat.mark``)."""
    target = told.get("target")
    named_ = {"release": target or "latest"}
    if places.packaged():
        return {**named_, "outcome": "failed", "cause": "packaged", "start": False,
                "detail": "refused: this worker runs inside a Windows app package, and nothing was changed"}
    prefix = Path(told["prefix"])
    if same(sys.prefix, prefix):
        return {**named_, "outcome": "failed", "cause": "helper_start", "start": False,
                "detail": "refused: this worker runs from the environment it would replace, and nothing was changed"}
    command = tool_command(told, run)
    server = answering()
    if server is not None:
        stop(server, log)
    wanted = server is not None or told.get("start") is True
    code, said, left = upgrade(told, run, installing(told, told["requirement"]), command, log, system)
    got = auto_update.installed(prefix)
    if code != 0 and got is not None and got == target and not unrecorded(prefix):
        # The environment is upgraded and whole: what failed after it is the bin command, which is back (``upgrade``).
        log.write(f"{by(told)} exited {code} with cad {got} installed whole: checked as an upgrade")
        code = 0
    got = (got if code == 0 else None) or target
    named_ = {"release": got or "latest"}
    if code == 0 and got is not None:
        clear(got, log)
        ok, said = runs(told, run, got, wanted)
        if ok and got == told["from"]:
            return {**named_, "outcome": "current", "detail": f"cad {got} is the newest release it may take",
                    **started(wanted, True, said)}
        if ok:
            return {**named_, "outcome": "installed", "detail": f"cad {got} runs, upgraded in place by {by(told)}",
                    **started(wanted, True, said)}
        cause = "start_failed"
        detail = f"cad {got} did not {'start' if wanted else 'run'}: {last_line(said) or 'no word'}"
    else:
        cause, detail = cause_of(code, said, log), why(said) or f"{by(told)} said nothing"
        if cause in ("in_use", "denied") and left:  # a process of cad's the sweep could not stop held the file
            cause = "cad_running"
    back, again = recover(told, run, got, wanted, log, upgraded=code == 0, command=command, system=system)
    if back is not None and back == got and got != told["from"]:
        return {**named_, "outcome": "installed", "detail": f"cad {got} runs, installed again after: {detail}",
                **started(wanted, True, again)}
    if back is None:
        detail = f"{detail}; and the repair in place left no cad that runs: {last_line(again) or 'no word'}"
        back, again = reinstall(told, run, log, command=command, wanted=wanted, mark=mark, system=system)
        how = f"installed again by `{' '.join(map(str, reinstalling(told)))}`"
        if back is not None and back != told["from"]:
            return {"release": back, "outcome": "installed", "detail": f"cad {back} runs, {how} after: {detail}",
                    **started(wanted, True, again)}
        if back is None:
            cause, detail = "broken", f"{detail}; and {how} left no cad that runs: {last_line(again) or 'no word'}"
        else:
            detail = f"{detail}; cad {back} runs again, {how}"
    return {**named_, "outcome": "failed", "cause": cause, "restored": back is not None, "detail": detail,
            **started(wanted, back is not None, again)}


def upgrade(told, run, argv, command, log, system=None, spare=None):
    """One run of the installer's ``argv`` (``installing``), made safe on Windows: its bin ``cad.exe`` (``command``)
    moved aside first, so a new ``cad`` fails at once, then every process running from the environment stopped but
    ``spare`` (the switch's, ``told["spare"]``, by default), looked for again until none is left
    (``stop_environment``), and the moment the installer returns a bin ``cad`` there again (``command_back``, on every
    system), before anything is checked. The installer's exit status and words, and the processes of the environment
    the sweep left running."""
    prefix, moved, left = Path(told["prefix"]), None, []
    if WINDOWS:
        moved = aside(command, log) if command is not None else None
        left = stop_environment(prefix, command, (told.get("spare") or ()) if spare is None else spare, log, system)
    try:
        return (*run(argv, auto_update.UPGRADE_SECONDS), left)
    finally:
        if command is not None:
            command_back(command, moved, prefix, log, windows=WINDOWS)


def recover(told, run, target, wanted, log, *, upgraded, command=None, system=None):
    """Step g (see the module), where the upgrade to ``target`` failed (``upgraded`` false) or its check did: the
    release that runs after it, or None, and what its check said. Where nothing changed (no ``*.dist-info`` without its
    ``RECORD``) the release before is checked as it is first; else, or where it does not run, ``target`` installed
    again in place (``installing``: ``uv tool upgrade --reinstall``, ``pipx runpip cad install --force-reinstall``),
    then the release before, each after a server of another release is stopped (``clear``) and the records left half
    removed are deleted (``unrecorded``), made safe as the upgrade is (``upgrade``); each checked (``runs``)."""
    prefix, before, said = Path(told["prefix"]), told["from"], ""
    if target is None:  # the installer named none it got: the release before alone
        target = before
    if not upgraded and not unrecorded(prefix):
        clear(before, log)
        ok, said = runs(told, run, before, wanted)
        if ok:
            return before, said
    for release_ in dict.fromkeys(name for name in (target, before) if release(name) is not None):
        clear(release_, log)
        removed(prefix, told, log)
        code, said, _left = upgrade(told, run, installing(told, f"cad=={release_}", again=True), command, log, system)
        if code == 0:
            ok, said = runs(told, run, release_, wanted)
            if ok:
                return release_, said
    return None, said


def reinstall(told, run, log, *, command, wanted, mark, system=None, seconds=WAIT_SECONDS, sleep=time.sleep):
    """Step h (see the module), the last resort: the record's phase ``repairing`` (``mark``), the processes the switch
    spared waited for until none runs from the environment (``running``; ``seconds`` at most: the sweep stops what is
    left), the folders without their ``RECORD`` deleted (``removed``), and the installer's ``reinstalling`` run as an
    upgrade is (``upgrade``), sparing none; then the release that runs checked (``runs``). That release, or None, and
    what was said."""
    mark("repairing")
    prefix, spare = Path(told["prefix"]), told.get("spare") or []
    deadline = time.monotonic() + seconds
    while running(spare, prefix, command, system):
        if time.monotonic() >= deadline:
            log.write(f"a process the switch spared still ran from cad's environment after {seconds:g} s")
            break
        sleep(LOOK_SECONDS)
    clear(None, log)
    removed(prefix, told, log)
    code, said, _left = upgrade(told, run, reinstalling(told), command, log, system, spare=[])
    held = auto_update.installed(prefix) if code == 0 else None
    if held is None:
        return None, said
    ok, said = runs(told, run, held, wanted)
    return (held if ok else None), said


def removed(prefix, told, log):
    """Each ``*.dist-info`` of the environment at ``prefix`` left without its ``RECORD`` (``unrecorded``) deleted."""
    for path in unrecorded(prefix):
        shutil.rmtree(path, ignore_errors=True)
        log.write(f"removed {path}, which {by(told)} left without its RECORD")


def unrecorded(prefix):
    """Each ``*.dist-info`` of the environment at ``prefix`` that has no ``RECORD``: what an upgrade stopped midway
    leaves, which every later uv run fails on."""
    return [path for folder in auto_update.site_packages(prefix) for path in sorted(folder.glob("*.dist-info"))
            if path.is_dir() and not (path / "RECORD").is_file()]


def clear(release_, log):
    """Before a release is checked again: a server of another release than ``release_`` that answers now -- one come up
    after its start was given up on -- stopped at once. Left there, every command of ``release_`` would be refused as
    one of another release, and a start of it would join it and replace nothing. Never raises."""
    try:
        found = answering()
        if found is None or found[0] == release_:
            return
        client.sweep(stop=True, seconds=RUN_SECONDS)
        log.write(f"the cad server {found[0] or ''}, of another release, was stopped")
    except Exception as error:  # noqa: BLE001 - the check goes on: the start says what is there
        log.write(f"a server of another release could not be stopped: {type(error).__name__}: {error}")


def replace(told, run, held, log, mark=lambda phase: None):
    """Where the environment holds release ``held`` already: a server of an older release, or one of ``held`` from
    another environment (a copy the bridge hands over from), stopped and replaced by this environment's (the record's
    phase ``switching`` kept first, ``mark``, so a command that finds no server meanwhile waits for the next); else,
    where none answers and ``start`` asks for one, one started. The record's word for the server."""
    server = answering()
    elsewhere = server is not None and isinstance(server[1], str) and not same(server[1], told["prefix"])
    if server is not None and not (server[0] is None or client.newer(held, server[0]) or server[0] == held and elsewhere):
        return {}
    if server is None and told.get("start") is not True:
        return {"start": False}
    mark("switching")
    if server is not None:
        stop(server, log)
    ok, said = runs(told, run, held, True)
    return started(True, ok, said)


# --- the installer's commands ------------------------------------------------------------------------------------


def installing(told, requirement, again=False):
    """The installer's command that installs ``requirement`` in cad's environment where it is: uv's ``uv tool upgrade
    [--reinstall] <requirement>``, which keeps its receipt; pipx's ``pipx runpip cad install --upgrade
    [--force-reinstall] <requirement>``, pip (or ``uv pip``, under pipx's uv backend) inside pipx's environment,
    which keeps pipx's pin (pipx 1.19 notes ``requirement`` in its metadata, which ``pipx upgrade`` moves on from)."""
    if told.get("installer") == "pipx":
        return [*told["pipx"], "runpip", "cad", "install", "--upgrade", *(["--force-reinstall"] if again else []),
                requirement]
    return [told["uv"], "tool", "upgrade", *(["--reinstall"] if again else []), requirement]


def reinstalling(told):
    """The installer's command that installs cad again whole, the last resort (``reinstall``): uv's ``uv tool install
    --force`` of the newest of ``from``'s major (``tool_install.command``: ``cad<N>``, as cad's installers write it,
    never one release, which would pin it); pipx's ``pipx install --force cad``, unpinned."""
    if told.get("installer") == "pipx":
        return [*told["pipx"], "install", "--force", "cad"]
    command = tool_install.command(told["uv"], told["from"])
    return [*command[:3], "--force", *command[3:]]


def tool_command(told, run):
    """The installer's bin ``cad`` (``cad.exe`` on Windows), as the installer names its folder (``uv tool dir --bin``;
    ``pipx environment --value PIPX_BIN_DIR``), or None where it cannot say."""
    asked = [*told["pipx"], "environment", "--value", "PIPX_BIN_DIR"] if told.get("installer") == "pipx" \
        else [told["uv"], "tool", "dir", "--bin"]
    code, said = run(asked, ASK_SECONDS)
    folder = last_line(said) if code == 0 else ""
    return Path(folder) / ("cad.exe" if WINDOWS else "cad") if folder else None


# --- on Windows: the bin command moved aside and back, and the environment's processes stopped ---------------------


def own_command(prefix, windows=WINDOWS):
    """The environment's own ``cad`` command at ``prefix`` (``Scripts/cad.exe``, ``bin/cad``)."""
    return Path(prefix) / ("Scripts/cad.exe" if windows else "bin/cad")


def aside(command, log):
    """``command`` (the installer's bin ``cad.exe``) renamed beside itself (``ASIDE``): Windows lets a running program
    be renamed, never deleted. Where it was moved, or None (none there, or the rename refused: the installer then
    meets it, and goes on)."""
    moved = command.with_name(ASIDE.format(pid=os.getpid()))
    try:
        os.replace(command, moved)
    except FileNotFoundError:
        return None
    except OSError as error:
        log.write(f"{command} could not be moved aside: {type(error).__name__}: {error}")
        return None
    log.write(f"{command} moved aside to {moved.name}")
    return moved


def command_back(command, moved, prefix, log, windows=WINDOWS):
    """The installer's bin ``cad`` at ``command`` again where the installer left none -- on Windows the environment's
    own (``Scripts/cad.exe``) copied there, as pipx exposes it and uv's is the same program, elsewhere a link to its
    ``bin/cad`` as uv and pipx make one; else the one moved aside (``moved``) put back --; then the one moved aside
    removed where it can be (a process may run it still: the server's next tidying removes it). What is left of it
    there, or None."""
    if not os.path.lexists(command):
        try:
            own = own_command(prefix, windows)
            if windows:
                shutil.copy2(own, command)
                log.write(f"{command} copied from the environment's own")
            else:
                if not own.is_file():
                    raise FileNotFoundError(own)
                os.symlink(own, command)
                log.write(f"{command} linked to the environment's own")
        except OSError:
            if moved is not None:
                with contextlib.suppress(OSError):
                    os.replace(moved, command)
                    log.write(f"{command} put back as it was")
                    return None
    if moved is not None:
        try:
            os.unlink(moved)
        except OSError:
            return moved if os.path.lexists(moved) else None
    return None


def lineage(pid, table):
    """``pid`` and each process that started it, as far as ``table`` (``Windows.processes``) knows them: the processes
    ending which ends ``pid`` (a ``cad.exe``, the environment's ``python.exe``, each ends the Python under it)."""
    found = set()
    while pid and pid in table and pid not in found:
        found.add(pid)
        pid = table[pid][0]
    if pid:
        found.add(pid)
    return found


def running_from(image, prefix, command):
    """Whether a process whose program is ``image`` runs from the environment at ``prefix``: its program inside it, or
    the installer's bin ``cad.exe`` (``command``), or one moved aside beside it (``ASIDE``)."""
    if not image:
        return False
    path = os.path.normcase(os.path.abspath(image))
    inside = os.path.normcase(os.path.abspath(prefix)).rstrip("\\/") + os.sep
    if path.startswith(inside):
        return True
    if command is None:
        return False
    if path == os.path.normcase(os.path.abspath(command)):
        return True
    folder, name = os.path.split(path)
    return folder == os.path.normcase(os.path.abspath(Path(command).parent)) \
        and re.fullmatch(r"\.cad-\d+\.exe\.old", name) is not None


def stop_environment(prefix, command, spare, log, system=None, seconds=END_SECONDS, rounds=ROUNDS):
    """On Windows, every process running from the environment at ``prefix`` (``running_from``) stopped -- but each
    process in ``spare``, with those that started them (``lineage``) -- and waited for until it is gone, with the
    processes each started directly (the Python a launcher started, which ends with it: killing a ``cad.exe`` takes its
    Python down in milliseconds), ``seconds`` at most; then looked for again, until none is left, ``rounds`` looks at
    most. As Scoop finds what to stop before it updates an app. This worker runs from uv's cache, never from there, so
    it spares nothing of its own. Each written to the log. The processes still running from it after the last look
    (none where none could be seen), by which a file in use is ``cad_running``. Never raises. ``system``: Windows'
    process calls (``Windows``; a test's stand-in)."""
    try:
        system = system or Windows()
        for round_ in range(rounds + 1):
            table = system.processes()
            kept = set()
            for pid in spare:
                kept |= lineage(pid, table)
            ending = sorted(pid for pid, (_parent, image) in table.items()
                            if pid not in kept and running_from(image, prefix, command))
            if not ending:
                return []
            if round_ == rounds:
                log.write(f"still running from cad's environment after {rounds} rounds: {', '.join(map(str, ending))}")
                return ending
            watched = sorted(pid for pid, (parent, _image) in table.items()
                             if parent in ending and pid not in kept and pid not in ending)
            left = system.end(ending, watched, seconds)
            log.write("stopped the processes running from cad's environment: "
                      + ", ".join(f"{pid} ({table[pid][1]})" for pid in ending)
                      + (f"; still there after {seconds:g} s: {', '.join(map(str, left))}" if left else ""))
    except Exception as error:  # noqa: BLE001 - the install goes on, and says what it met
        log.write(f"the processes running from cad's environment could not be stopped: {type(error).__name__}: {error}")
    return []


def running(pids, prefix, command, system=None):
    """On Windows, which of ``pids`` run from the environment at ``prefix`` now (``running_from``); elsewhere, and where
    Windows cannot be asked, none."""
    if not WINDOWS and system is None:
        return []
    try:
        table = (system or Windows()).processes()
    except Exception:  # noqa: BLE001 - what cannot be seen is not waited for: the sweep stops it
        return []
    return sorted(pid for pid in pids if pid in table and running_from(table[pid][1], prefix, command))


# PowerShell's list of the processes (``listed``): each one's id, its parent's and its program's path, as JSON.
PROCESSES = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-CimInstance Win32_Process | "
             "Select-Object ProcessId, ParentProcessId, ExecutablePath | ConvertTo-Json -Compress"]


def listed(run=run):
    """Every process as ``Windows.processes`` gives them, read from PowerShell's ``Get-CimInstance Win32_Process``
    where the Win32 API could not be read; None where PowerShell could not say."""
    code, said = run(PROCESSES, 60)
    try:
        found = json.loads(said) if code == 0 else None
    except ValueError:
        return None
    found = [found] if isinstance(found, dict) else found
    if not isinstance(found, list):
        return None
    return {int(each.get("ProcessId") or 0): (int(each.get("ParentProcessId") or 0), each.get("ExecutablePath") or None)
            for each in found if isinstance(each, dict)}


class Windows:
    """Windows' own calls for ``stop_environment``, by ctypes: the processes (a Toolhelp snapshot, each program's path
    by ``QueryFullProcessImageNameW``; else PowerShell's list, ``listed``) and their end (``TerminateProcess``, ``WaitForSingleObject``)."""


    SNAPPROCESS, QUERY, TERMINATE, SYNCHRONIZE = 0x2, 0x1000, 0x0001, 0x00100000

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        kernel = self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class Entry(ctypes.Structure):  # PROCESSENTRY32W
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]

        self.Entry = Entry
        for name, arguments, result in (
                ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
                ("Process32FirstW", [wintypes.HANDLE, ctypes.POINTER(Entry)], wintypes.BOOL),
                ("Process32NextW", [wintypes.HANDLE, ctypes.POINTER(Entry)], wintypes.BOOL),
                ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
                ("QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
                ("TerminateProcess", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
                ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
                ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL)):
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result

    def processes(self):
        """``{pid: (parent pid, its program's path or None)}`` of every process now: by a Toolhelp snapshot, else, where
        that fails, by PowerShell (``listed``)."""
        try:
            return self.snapshot()
        except Exception:  # noqa: BLE001 - the other way, then the error
            found = listed()
            if found is None:
                raise
            return found

    def snapshot(self):
        kernel, ctypes = self.kernel, self.ctypes
        snapshot = kernel.CreateToolhelp32Snapshot(self.SNAPPROCESS, 0)
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        table = {}
        try:
            entry = self.Entry()
            entry.dwSize = ctypes.sizeof(self.Entry)
            more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID, None)
                more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        return {pid: (parent, self.image(pid)) for pid, (parent, _none) in table.items()}

    def image(self, pid):
        kernel, ctypes = self.kernel, self.ctypes
        handle = kernel.OpenProcess(self.QUERY, False, pid)
        if not handle:
            return None
        try:
            size = self.wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            return buffer.value if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
        finally:
            kernel.CloseHandle(handle)

    def end(self, ending, watched, seconds):
        """Each of ``ending`` terminated, then it and each of ``watched`` waited for, ``seconds`` in all: the pids still
        there."""
        kernel, handles = self.kernel, {}
        for pid in ending:
            handle = kernel.OpenProcess(self.TERMINATE | self.SYNCHRONIZE, False, pid)
            if handle:
                kernel.TerminateProcess(handle, 1)
                handles[pid] = handle
        for pid in watched:
            handle = kernel.OpenProcess(self.SYNCHRONIZE, False, pid)
            if handle:
                handles[pid] = handle
        deadline, left = time.monotonic() + seconds, []
        for pid, handle in handles.items():
            wait = max(0, int((deadline - time.monotonic()) * 1000))
            if kernel.WaitForSingleObject(handle, wait) != 0:
                left.append(pid)
            kernel.CloseHandle(handle)
        return left


# --- why an attempt did not install what it was for: one word ------------------------------------------------------

# Every word a record's ``cause`` holds, a closed list. The worker tells most of them: from uv's words where the
# upgrade failed (``cause_of``; ``cad_running`` where a file was in use or refused and a process of the environment the
# switch could not stop still ran, ``stop_environment``), ``start_failed`` where the release did not start and the one
# before runs again, ``broken`` where neither runs, ``packaged`` where it ran inside a Windows app package, ``helper_start`` where it ran
# from the environment it would replace; ``helper_start`` is the trigger's too (its worker could not start), and so are
# uv's words where it could not build the worker's environment (``auto_update.build``); ``lost`` a reader's (an
# attempt still underway and silent), ``no_installer`` and ``pinned`` the reasons none begins (``auto_update.blocked``),
# and ``no_switch`` one an earlier release kept. Each word is said in plain words by ``auto_update.SAID``.
CAUSES = ("timeout", "no_program", "in_use", "denied", "disk_full", "network", "offline", "no_release", "python",
          "platform", "config_exclude", "config_index", "config_tls", "cad_running", "broken", "start_failed", "helper_start",
          "helper_crash", "lost", "no_installer", "no_switch", "packaged", "pinned", "unknown")

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
    """Why uv failed, one of ``CAUSES``: what uv's exit status and words say (``classify``) -- its first error
    (``first_error``), never a later rollback's, and all it printed where that tells nothing known --, then what its
    settings explain (``refine``), whose names are written to the log."""
    found = settings(environ)
    if found and log is not None:
        log.write("uv's settings found (names only): " + "; ".join(
            f"{name}: {', '.join(names)}" for name, names in sorted(found.items())))
    first = first_error(output)
    cause = classify(code, first) if first else "unknown"
    if cause == "unknown":
        first, cause = output, classify(code, output)
    return refine(cause, first, found)


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
                             f"{told.get('requirement')} by {installer(told)}, "
                             f"{'typed' if told.get('asked') else 'automatic'}, try {told.get('tries', 1)}\n")
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
    try:
        auto_update._keep(Path(path), record)  # noqa: SLF001
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
    try:
        lock = file_lock.state(Path(told["record"]).parent)
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
    Every command it runs is told it is the worker's of this attempt (``auto_update.WORKER_ENV``), so its check of the
    release being left starts that release's server, which a start meanwhile would not (``auto_update.leaving``)."""
    os.environ[auto_update.WORKER_ENV] = json.dumps(told.get("at"))
    beat = Beat(told)
    try:
        found = update(told, mark=beat.mark)
    except Exception as error:  # noqa: BLE001 - said in the record, never a silent end
        try:
            Log(told.get("log")).write("the worker stopped with an error:\n" + traceback.format_exc())
            found = crashed(told, error)
        except Exception:  # noqa: BLE001 - nothing more to say: the attempt stays as the trigger kept it
            found = None
    beat.stop()
    if found is None:
        return
    with held(told):
        kept = _record(told)
        if kept is None or kept.get("at") == told.get("at"):  # ``ours``
            asked = kept is not None and kept.get("asked") is True and found.get("asked") is not True
            keep(told["record"], {**found, **({"asked": True} if asked else {})})


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
