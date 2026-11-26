"""cad's update, repaired from outside cad's environment: the last resort of the worker (``auto_update_helper``), where
its repair in place left no cad that runs. The installer then installs cad again whole (``uv tool install --force``),
which removes the environment and makes it anew: it cannot while any process runs from
it on Windows (measured: ``failed to remove directory ...\\Scripts: Access is denied``, and cad left broken), the
worker's own interpreter included. So the worker copies this file and ``auto_update_sweep`` into cad's state folder,
keeps the attempt underway in its ``repairing`` phase, starts the copy detached, outside any Windows app package
(``places.outside_package``), as ``<base python> -I -B auto_update_repair.py <told>`` by the Python the environment was
made from (``sys._base_executable``, never one inside it), and ends. Run so, it imports the standard library alone and
the sweep beside it.

``told`` is one JSON argument: ``record``, ``log`` and ``at`` (the attempt's), ``from`` (the release that ran before),
``release`` (what the record names), ``prefix`` (the environment), ``cad`` (its own ``cad`` command), ``command`` (the
installer's bin ``cad``, or null), ``install`` (the installer's command that installs cad again, by a range or
unpinned, never one release), ``start`` (whether a server is wanted at the end), ``cause`` and ``detail`` (why the
worker could not repair it), ``worker`` (its pid), ``spare`` (the processes the worker left running: the ``cad update``
that waits on it among them) and ``copy`` (the folder this copy is in). In order (``repair``):

1. The worker's end waited for (``settle``): its last write of the record, which says ``repairing``, and on Windows the
   worker and each spared process of the environment gone (the ``cad update`` that waited says cad is being repaired,
   and ends); ``WAIT_SECONDS`` at most. Then the attempt marked as still underway (``mark``).
2. On Windows the installer's bin ``cad.exe`` moved aside, then every process of the environment stopped
   (``auto_update_sweep``); each ``*.dist-info`` of it without its ``RECORD`` deleted.
3. The installer's command (``install``), then its bin ``cad`` there again where it left none (``command_back``).
4. ``cad --version`` by the environment's own command: the release that runs, if any (``checked``). A server started
   where one was wanted (``cad server start``).
5. The outcome written into the record where it is still this attempt's and underway, whole (``keep``: a rename over
   it): ``installed`` where a release newer than ``from`` runs; else ``failed`` with the worker's cause where ``from``
   runs again (``restored``), or ``broken`` where none runs. Then this copy removed.

Every other writer of the record writes an attempt that ended, or begins one where none is underway: none writes it
while this one is, so the repairer writes it without the state folder's lock, which is cad's. Each command, its exit
status, how long it took and the end of what it printed are added to the worker's log. Never raises: an error of its
own ends the attempt ``broken``, its words the detail.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

if __package__:  # imported as cad's own (the worker, a test)
    from cad_server._internal import auto_update_sweep as sweep
else:  # run as its copy, by its file: the sweep copied beside it
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import auto_update_sweep as sweep

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW
# How long the worker's end is waited for (``settle``), and how often it is looked for.
WAIT_SECONDS, LOOK_SECONDS = 60.0, 0.2
# How long the installer may take (``auto_update.UPGRADE_SECONDS``), and ``cad --version`` and ``cad server start``.
INSTALL_SECONDS, RUN_SECONDS = 900.0, 120.0
LOG_BYTES = 64 * 1024  # how much of each command's output the log keeps: its end


def run(command, timeout):
    """``(exit status, all it printed)``; status None where it could not run or did not end in time, with the error's
    type and words."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{type(error).__name__}: {error}"
    return done.returncode, done.stdout or ""


def last_line(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def release(text):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


class Log:
    """The worker's log (``auto_update_helper.Log``), added to: each line, and each command with its exit status, how
    long it took and the last ``LOG_BYTES`` of what it printed. A log that cannot be written writes nothing more."""

    def __init__(self, path):
        self.path = path

    def write(self, text):
        if not self.path:
            return
        try:
            with open(self.path, "a", encoding="utf-8", errors="replace") as handle:
                handle.write(text.rstrip("\n") + "\n")
        except Exception:  # noqa: BLE001 - the repair never fails of its log
            self.path = None

    def running(self, run):
        def each(command, timeout):
            began = time.monotonic()
            code, said = run(command, timeout)
            data = (said or "").encode("utf-8", errors="replace")
            text = data[max(len(data) - LOG_BYTES, 0):].decode("utf-8", errors="ignore")
            self.write("\n".join([f"$ {' '.join(map(str, command))}",
                                  f"  {'exit ' + str(code) if code is not None else 'did not run to its end'} after "
                                  f"{time.monotonic() - began:.1f} s",
                                  *(f"  | {line}" for line in text.rstrip().splitlines())]))
            return code, said
        return each


def _read(told):
    """The record where it is this attempt's (its ``at``) and underway, else None."""
    try:
        with open(told["record"], encoding="utf-8") as handle:
            found = json.load(handle)
    except (OSError, ValueError):
        return None
    ok = isinstance(found, dict) and found.get("at") == told.get("at") and found.get("outcome") == "underway"
    return found if ok else None


def keep(path, record, tries=10):
    """``record`` written whole in place of ``path``: a file beside it renamed over it, tried again a moment later
    where Windows refuses the rename (a reader holds the record open). Never raises."""
    staged = f"{path}.{os.getpid()}.repair.tmp"
    try:
        with open(staged, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
        for attempt in range(tries):
            try:
                os.replace(staged, path)
                return
            except OSError:
                if attempt == tries - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
    except OSError:
        try:
            os.unlink(staged)
        except OSError:
            pass


def mark(told):
    """The attempt marked as still underway (its ``beat`` now), where the record is still this attempt's and underway:
    the repair takes minutes, and an attempt silent for twenty is taken for lost."""
    found = _read(told)
    if found is not None:
        keep(told["record"], {**found, "beat": time.time(), "phase": "repairing"})


def settle(told, prefix, command, system=None, seconds=WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic):
    """Step 1: until the record says ``repairing`` (the worker's last write) and, on Windows, neither the worker nor any
    spared process of the environment runs (``auto_update_sweep.running``), ``seconds`` at most. Whether it all
    ended."""
    deadline = clock() + seconds
    pids = [pid for pid in (told.get("worker"), *(told.get("spare") or ())) if pid]
    while True:
        written = (_read(told) or {}).get("phase") == "repairing"
        if written and not sweep.running(pids, prefix, command, system):
            return True
        if clock() >= deadline:
            return False
        sleep(LOOK_SECONDS)


def unrecorded(prefix):
    """Each ``*.dist-info`` of the environment at ``prefix`` that has no ``RECORD``: what an install stopped midway
    leaves, which every later install fails on."""
    folders = [path for pattern in ("Lib/site-packages", "lib/python*/site-packages") for path in prefix.glob(pattern)]
    return [path for folder in folders for path in sorted(folder.glob("*.dist-info"))
            if path.is_dir() and not (path / "RECORD").is_file()]


def checked(told, run):
    """Step 4: the release ``cad --version`` says now, or None where none runs; and what was said."""
    code, said = run([told["cad"], "--version"], RUN_SECONDS)
    found = re.fullmatch(r"cad (\S+)", last_line(said)) if code == 0 else None
    return (found[1] if found else None), said


def outcome(told, held, said):
    """Step 5's outcome, from the release that runs now (``held``, or None) and what was said."""
    before, how = told["from"], f"installed again by `{' '.join(map(str, told['install']))}`"
    if held is not None and release(held) is not None and release(before) is not None \
            and release(held) > release(before):
        return {"release": held, "outcome": "installed", "detail": f"cad {held} runs, {how} after: {told['detail']}"}
    if held == before:
        return {"release": told["release"], "outcome": "failed", "cause": told.get("cause") or "unknown",
                "restored": True, "detail": f"{told['detail']}; cad {before} runs again, {how}"}
    return {"release": told["release"], "outcome": "failed", "cause": "broken", "restored": False,
            "detail": f"{told['detail']}; and {how} left no cad that runs: {last_line(said) or 'no word'}"}


def repair(told, run=run, system=None, seconds=WAIT_SECONDS, sleep=time.sleep):
    """Steps 1 to 4 (see the module): what step 5 writes into the record. ``system``: Windows' process calls
    (``auto_update_sweep.Windows``; a test's stand-in)."""
    log = Log(told.get("log"))
    run = log.running(run)
    prefix = Path(told["prefix"])
    command = Path(told["command"]) if told.get("command") else None
    log.write(f"the repair outside cad's environment, begun {time.strftime('%Y-%m-%d %H:%M:%S %z')} by "
              f"{sys.executable}")
    if not settle(told, prefix, command, system, seconds, sleep):
        log.write(f"the update's worker, or a process it left running, had not ended after {seconds:g} s")
    mark(told)
    moved = None
    if WINDOWS:
        moved = sweep.aside(command, log) if command is not None else None
        sweep.stop_environment(prefix, command, [], log, system)
    for path in unrecorded(prefix):
        shutil.rmtree(path, ignore_errors=True)
        log.write(f"removed {path}, which an install left without its RECORD")
    try:
        code, said = run(told["install"], INSTALL_SECONDS)
    finally:
        if command is not None:
            sweep.command_back(command, moved, prefix, log, windows=WINDOWS)
    mark(told)
    held, checked_said = checked(told, run)
    found = outcome(told, held, checked_said if code == 0 else said)  # where the install failed, its words
    if told.get("start") is True:
        code, said = run([told["cad"], "server", "start"], RUN_SECONDS) if held is not None else (None, "")
        found["started"] = last_line(said) if code == 0 else f"not started: {last_line(said) or 'no cad that runs'}"
    else:
        found["start"] = False
    return found


def main(told, run=run, system=None, seconds=WAIT_SECONDS):
    """The repair ``told`` asks for, its outcome written into the record where it is still this attempt's and underway,
    the worker's own fields kept; then this copy removed. Never raises."""
    log = Log(told.get("log"))
    try:
        found = repair(told, run=run, system=system, seconds=seconds)
    except Exception as error:  # noqa: BLE001 - said in the record, never a silent end
        log.write("the repair stopped with an error:\n" + traceback.format_exc())
        found = {"release": told.get("release"), "outcome": "failed", "cause": "broken", "restored": False,
                 "detail": f"{told.get('detail')}; and the repair stopped with an error: {type(error).__name__}: "
                           f"{error}"}
    kept = _read(told)
    if kept is not None:
        record = {name: value for name, value in kept.items() if name not in ("phase", "beat")}
        keep(told["record"], {**record, **found, "ended": time.time()})
    log.write(f"ended {time.strftime('%Y-%m-%d %H:%M:%S %z')}: {found.get('outcome')}"
              + (f", the cause: {found['cause']}" if found.get("cause") else "") + f"; {found.get('detail')}")
    if told.get("copy"):
        shutil.rmtree(told["copy"], ignore_errors=True)


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
