"""cad's own update, carried out by a process that is not cad: ``auto_update.trigger`` runs this file's source with
the Python cad's environment was made from (``-I -S -c``: never cad's environment, never a module of it), detached and
with no window, and hands it one JSON argument: ``cad`` (the environment's own ``cad`` command), ``target`` (the release
asked for, or null: whatever the upgrade gets), ``prefix`` (the environment), ``record`` (the last attempt's file),
``from``, ``at`` and ``tries``; the installer's commands, ``upgrade`` (cad upgraded to the newest release),
``put_back`` (the release that ran before installed again) and ``launchers`` (prints the folder its launchers are in);
and ``then_install`` and ``install_log``.

In order: the server stopped (``cad server stop``, which waits until it is gone); unless the environment already holds
``target`` or newer (forward only), the upgrade, tried again on failure, until it ends 0 with a release installed, and
that release ``target`` or newer where there is one; where every try failed and ``cad`` no longer runs (uv removes the
whole tool when an install fails after it has begun), the release that ran before put back (``from``: no way back from a
good update, only what a failed one destroyed); the server started with whatever cad is there; and the outcome written
to ``record``. The release the record names is the one installed after the upgrade, where it ended well; the one asked
for where it did not. Then, where ``then_install`` is true and the upgrade installed a release newer than ``from``, the
new cad's ``cad plugin install``, once, after the record said so (``then_install``), its output in ``install_log`` and
its exit status in the record (``install_command``). The
standard library alone, and nothing else of cad.

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
import time
from pathlib import Path

# Seconds waited before each try of the install: the first at once.
WAITS = (0, 2, 5, 10, 20)
WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW: no console flashes for uv or cad
# A cad.exe set aside in the launchers' folder (``set_aside``): ``<stamp>`` names the try, ``<n>`` the file.
ASIDE = ".cad.exe.{stamp}.{n}.old"
# How long an install, and the install command after it, may run.
INSTALL_SECONDS = 900


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


def run(command, timeout):
    """``(exit status, its output's last line)``; status None where it could not run or did not end in time."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{type(error).__name__}: {error}"
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, lines[-1] if lines else ""


def logged(command, log, timeout):
    """``command`` run, its output (both streams) written to the file ``log``: its exit status, None where it could
    not run or did not end in time (said in the file)."""
    try:
        with open(log, "w", encoding="utf-8") as out:
            try:
                return subprocess.run(command, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                      timeout=timeout, creationflags=NO_WINDOW).returncode
            except (OSError, subprocess.SubprocessError) as error:
                out.write(f"\n{type(error).__name__}: {error}\n")
                return None
    except OSError:
        return None


def bin_folder(told, run):
    """The installer's launchers' folder, where the tool's ``cad`` command is (uv: ``uv tool dir --bin``, which reads
    ``UV_TOOL_BIN_DIR`` as uv's install does), or None."""
    code, folder = run(told["launchers"], 60)
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


def install(told, command, wanted, run, sleep, folder=None):
    """``command`` run, tried at each of ``WAITS``, each ``cad.exe`` set aside first where ``folder`` (the launchers'
    folder, on Windows) is given, until it ends 0 with a release of cad installed, ``wanted`` or newer where it is
    given: ``(the release installed, or None, the installer's last line)``."""
    detail = "not tried"
    for wait in WAITS:
        sleep(wait)
        if folder is not None:
            set_aside(told, folder)
        code, detail = run(command, INSTALL_SECONDS)
        held = installed(told["prefix"])
        if code == 0 and held is not None and (wanted is None or held >= wanted):
            return held, detail
        if code == 0:
            detail = f"it installed {named(held) if held else 'no cad'}, not {named(wanted)}"
    return None, detail


def update(told, run=run, sleep=time.sleep, windows=WINDOWS):
    """The update ``told`` asks for; its outcome as the record keeps it."""
    target, before, restored = release(told["target"]), release(told["from"]), None
    folder = bin_folder(told, run) if windows else None
    if folder is not None:
        tidy(folder)
    run([told["cad"], "server", "stop"], 120)
    held = installed(told["prefix"])
    if held is not None and target is not None and held >= target:
        outcome, detail, got = "current", f"cad {named(held)} is installed", held
    else:
        got, detail = install(told, told["upgrade"], target, run, sleep, folder)
        outcome = "failed" if got is None else "installed" if before is None or got > before else "current"
        if got is None and run([told["cad"], "--version"], 60)[0] != 0:
            restored = install(told, told["put_back"], before, run, sleep, folder)[0] is not None
    code, said = run([told["cad"], "server", "start"], 120)
    if folder is not None:
        tidy(folder)
    then = bool(told.get("then_install")) and outcome == "installed"
    return {"release": named(got) if got is not None else told["target"] or "latest", "from": told["from"],
            "at": told["at"], "tries": told.get("tries", 1), "ended": time.time(), "outcome": outcome,
            "detail": detail, **({} if restored is None else {"restored": restored}),
            "started": said if code == 0 else f"not started: {said}", **({"then_install": True} if then else {})}


def chained(told, record, logged=logged):
    """``record`` with the install command's exit status (``install_command``), where it runs after this update
    (``then_install``: asked for, the server's own update with the person's switch on, and a newer cad installed). Run
    once, by the new cad's own command, its output in ``install_log``."""
    if not record.get("then_install"):
        return record
    code = logged([told["cad"], "plugin", "install"], told["install_log"], INSTALL_SECONDS)
    return {**record, "install_command": code}


def keep(path, record):
    """``record`` written to ``path`` (a reader that finds it half written reads no attempt)."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
    except OSError:
        pass


def still(path, record):
    """Whether the attempt kept at ``path`` is still ``record``'s (begun at its ``at``), and not one begun since."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle).get("at") == record["at"]
    except (OSError, ValueError, AttributeError):
        return False


if __name__ == "__main__":
    told = json.loads(sys.argv[1])
    ended = update(told)
    keep(told["record"], ended)  # said at once: the install command after it can take minutes
    after = chained(told, ended)
    if after is not ended and still(told["record"], ended):
        keep(told["record"], after)
