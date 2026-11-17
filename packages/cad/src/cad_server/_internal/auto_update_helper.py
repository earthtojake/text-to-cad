"""cad's own update, carried out by a process that is not cad: ``auto_update.trigger`` runs this file's source with
the Python cad's environment was made from (``-I -S -c``: never cad's environment, never a module of it), detached and
with no window, and hands it one JSON argument: ``uv``, ``cad`` (the tool environment's own ``cad`` command), ``target``,
``prefix`` (the tool environment), ``record`` (the last attempt's file), ``from`` and ``at``.

In order: the server stopped (``cad server stop``, which waits until it is gone); unless the environment already holds
``target`` or newer (forward only), ``uv tool install --managed-python --python 3.14 cad==<target>``, tried again on
failure; where every try failed and ``cad`` no longer runs (uv removes the whole tool when an install fails after it
has begun), the release that ran before put back (``from``: no way back from a good update, only what a failed one
destroyed); the server started with whatever cad is there; and the outcome written to ``record``. The standard library
alone, and nothing else of cad.

On Windows uv cannot remove a ``cad.exe`` that runs (a ``cad update`` waiting, a ``cad server start``), and an install
that meets one fails halfway. A running ``cad.exe`` can be renamed, though, once cad holds it only as a running program
(``cad_server/__init__.py`` takes it off ``sys.path``). So before each try, each ``cad.exe`` of the tool, uv's bin
folder's (``uv tool dir --bin``) and the environment's own, is renamed to a name of its own in the bin folder, never
inside the environment, which uv deletes when an install fails, and a copy is put back where it was (``set_aside``).
The process keeps running from the renamed file. The renamed files are deleted where they can be, at the start and the
end of each run; one whose process still runs is left for the next (``tidy``).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Seconds waited before each try of the install: the first at once.
WAITS = (0, 2, 5, 10, 20)
WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW: no console flashes for uv or cad
# A cad.exe set aside in uv's bin folder (``set_aside``): ``<stamp>`` names the try, ``<n>`` the file.
ASIDE = ".cad.exe.{stamp}.{n}.old"


def release(text):
    """``X.Y.Z`` as three numbers, or None."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def installed(prefix):
    """The release of cad the tool environment at ``prefix`` holds now (the newest, after an install that failed
    midway), or None."""
    found = [release(path.name[len("cad-"):-len(".dist-info")]) for pattern in
             ("lib/python*/site-packages/cad-*.dist-info", "Lib/site-packages/cad-*.dist-info")
             for path in Path(prefix).glob(pattern)]
    return max((held for held in found if held is not None), default=None)


def run(command, timeout):
    """``(exit status, its output's last line)``; status None where it could not run or did not end in time."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{type(error).__name__}: {error}"
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, lines[-1] if lines else ""


def bin_folder(told, run):
    """uv's bin folder, where the tool's ``cad`` command is (``uv tool dir --bin``, which reads ``UV_TOOL_BIN_DIR`` as
    uv's install does), or None."""
    code, folder = run([told["uv"], "tool", "dir", "--bin"], 60)
    return Path(folder) if code == 0 and folder and Path(folder).is_dir() else None


def set_aside(told, folder):
    """Windows, before a try of the install: the bin folder's ``cad.exe`` and the environment's own (``told["cad"]``)
    each renamed to a name of its own in ``folder``, the bin folder, and a copy put back where it was. A rename that
    fails (no such file, another volume) is skipped. What was set aside."""
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


def install(told, version, run, sleep, folder=None):
    """``cad==<version>`` installed as the uv tool, tried at each of ``WAITS``, each ``cad.exe`` set aside first where
    ``folder`` (the bin folder, on Windows) is given: ``(installed, uv's last line)``."""
    detail = "not tried"
    for wait in WAITS:
        sleep(wait)
        if folder is not None:
            set_aside(told, folder)
        code, detail = run([told["uv"], "tool", "install", "--managed-python", "--python", "3.14", f"cad=={version}"],
                           900)
        if code == 0 and installed(told["prefix"]) == release(version):
            return True, detail
    return False, detail


def update(told, run=run, sleep=time.sleep, windows=WINDOWS):
    """The update ``told`` asks for; its outcome as the record keeps it."""
    target, restored = release(told["target"]), None
    folder = bin_folder(told, run) if windows else None
    if folder is not None:
        tidy(folder)
    run([told["cad"], "server", "stop"], 120)
    held = installed(told["prefix"])
    if held is not None and target is not None and held >= target:
        outcome, detail = "current", f"cad {'.'.join(map(str, held))} is installed"
    else:
        done, detail = install(told, told["target"], run, sleep, folder)
        outcome = "installed" if done else "failed"
        if not done and run([told["cad"], "--version"], 60)[0] != 0:
            restored = install(told, told["from"], run, sleep, folder)[0]
    code, said = run([told["cad"], "server", "start"], 120)
    if folder is not None:
        tidy(folder)
    return {"release": told["target"], "from": told["from"], "at": told["at"], "tries": told.get("tries", 1),
            "ended": time.time(), "outcome": outcome, "detail": detail,
            **({} if restored is None else {"restored": restored}),
            "started": said if code == 0 else f"not started: {said}"}


def keep(path, record):
    """``record`` written to ``path`` (a reader that finds it half written reads no attempt)."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
    except OSError:
        pass


if __name__ == "__main__":
    told = json.loads(sys.argv[1])
    keep(told["record"], update(told))
