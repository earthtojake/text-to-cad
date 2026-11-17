"""cad's own update, carried out by a process that is not cad: ``auto_update.trigger`` runs this file's source with
the Python cad's environment was made from (``-I -S -c``: never cad's environment, never a module of it), detached and
with no window, and hands it one JSON argument: ``uv``, ``cad`` (the tool environment's own ``cad`` command), ``target``,
``prefix`` (the tool environment), ``record`` (the last attempt's file), ``from`` and ``at``.

In order: the server stopped (``cad server stop``, which waits until it is gone); unless the environment already holds
``target`` or newer (forward only), ``uv tool install --managed-python --python 3.14 cad==<target>``, tried again on
failure (on Windows a ``cad.exe`` still running makes uv fail halfway, and a retry recovers); where every try failed
and ``cad`` no longer runs (uv removes the whole tool when an install fails after it has begun), the release that ran
before put back (``from``: no way back from a good update, only what a failed one destroyed); the server started with
whatever cad is there; and the outcome written to ``record``. The standard library alone, and nothing else of cad.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Seconds waited before each try of the install: the first at once.
WAITS = (0, 2, 5, 10, 20)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: no console flashes for uv or cad


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


def install(told, version, run, sleep):
    """``cad==<version>`` installed as the uv tool, tried at each of ``WAITS``: ``(installed, uv's last line)``."""
    detail = "not tried"
    for wait in WAITS:
        sleep(wait)
        code, detail = run([told["uv"], "tool", "install", "--managed-python", "--python", "3.14", f"cad=={version}"],
                           900)
        if code == 0 and installed(told["prefix"]) == release(version):
            return True, detail
    return False, detail


def update(told, run=run, sleep=time.sleep):
    """The update ``told`` asks for; its outcome as the record keeps it."""
    target, restored = release(told["target"]), None
    run([told["cad"], "server", "stop"], 120)
    held = installed(told["prefix"])
    if held is not None and target is not None and held >= target:
        outcome, detail = "current", f"cad {'.'.join(map(str, held))} is installed"
    else:
        done, detail = install(told, told["target"], run, sleep)
        outcome = "installed" if done else "failed"
        if not done and run([told["cad"], "--version"], 60)[0] != 0:
            restored = install(told, told["from"], run, sleep)[0]
    code, said = run([told["cad"], "server", "start"], 120)
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
