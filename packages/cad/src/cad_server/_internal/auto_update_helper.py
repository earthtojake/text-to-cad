"""cad's own update, carried out by a process that is not cad: ``auto_update.trigger`` runs this file's source with
the Python cad's environment was made from (``-I -S -c``: never cad's environment, never a module of it), detached and
with no window, and hands it one JSON argument: ``cad`` (the environment's own ``cad`` command), ``target`` (the release
asked for, or null: whatever the upgrade gets), ``prefix`` (the environment), ``record`` (the last attempt's file),
``from``, ``at`` and ``tries``; the installer's commands, ``upgrade`` (cad upgraded to the newest release of the major
of ``from``, never below it; with ``major``, to the newest release of all), ``put_back`` (the release that ran before
installed again) and ``launchers`` (prints the folder its launchers are in); ``installer`` (its name), ``wanted`` (the
release the attempt is for), ``asked`` (a typed update) and ``major`` (``cad update --major``), which it keeps in the
record for the server to count and judge; and ``start``, whether it starts the server at the end (false where ``cad
update`` found none running: it leaves none running).

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
not. It runs no install command and counts nothing: the server that starts after it does both
(``auto_update.report``, ``plugin_catch_up``). The standard library alone, and nothing else of cad.

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


def accepted(held, before, major):
    """Whether the upgrade may end on release ``held``: never older than ``before``, the release that ran, and, but for
    ``major`` (``cad update --major``), of ``before``'s major. Any release where ``before`` is not known."""
    if held is None:
        return False
    return before is None or (held >= before and (major or held[0] == before[0]))


def install(told, command, wanted, run, sleep, folder=None, accept=lambda held: held is not None, settle=False,
            enough=lambda held: False):
    """``command`` run, tried at each of ``WAITS``, each ``cad.exe`` set aside first where ``folder`` (the launchers'
    folder, on Windows) is given, until it ends 0 with a release of cad installed that ``accept`` takes, ``wanted`` or
    newer where it is given, or one ``enough`` takes (``major``: a higher major than ``from``'s): ``(the release
    installed, or None, the installer's last line)``. With ``settle``, where the last try ended 0 on a release
    ``accept`` takes, below ``wanted``, that release: nothing newer is to be had."""
    detail, settled = "not tried", None
    for wait in WAITS:
        sleep(wait)
        if folder is not None:
            set_aside(told, folder)
        code, detail = run(command, INSTALL_SECONDS)
        held = installed(told["prefix"])
        if code == 0 and accept(held) and (wanted is None or held >= wanted or enough(held)):
            return held, detail
        settled = held if settle and code == 0 and accept(held) else None
        if code == 0:
            detail = (f"it installed {named(held)}, not {named(wanted)}" if accept(held) else
                      f"it installed {named(held) if held else 'no cad'}, which it may not end on")
    return settled, detail


def update(told, run=run, sleep=time.sleep, windows=WINDOWS):
    """The update ``told`` asks for; its outcome as the record keeps it."""
    target, before, restored = release(told["target"]), release(told["from"]), None
    major = told.get("major") is True
    folder = bin_folder(told, run) if windows else None
    if folder is not None:
        tidy(folder)
    run([told["cad"], "server", "stop"], 120)
    held = installed(told["prefix"])
    above = held is not None and before is not None and not major and held[0] > before[0]
    if held is not None and ((target is not None and held >= target) or above):
        outcome, detail, got = "current", f"cad {named(held)} is installed", held
    else:
        # ``major``: crossing to a higher major is what was asked, whatever release of it the upgrade got; where no
        # higher major was the target (none is out, or PyPI could not say), it ends as a bounded update does.
        crossed = lambda found: major and found is not None and before is not None and found[0] > before[0]  # noqa: E731
        got, detail = install(told, told["upgrade"], target, run, sleep, folder,
                              accept=lambda found: accepted(found, before, major), enough=crossed,
                              settle=not (major and crossed(target)))
        outcome = "failed" if got is None else "installed" if before is None or got > before else "current"
        if got is None and run([told["cad"], "--version"], 60)[0] != 0:
            restored = install(told, told["put_back"], before, run, sleep, folder)[0] is not None
    start = told.get("start", True) is not False
    code, said = run([told["cad"], "server", "start"], 120) if start else (None, "")
    if folder is not None:
        tidy(folder)
    return {"release": named(got) if got is not None else told["target"] or "latest", "from": told["from"],
            "at": told["at"], "tries": told.get("tries", 1), "ended": time.time(), "outcome": outcome,
            "detail": detail, **({} if restored is None else {"restored": restored}),
            **({"started": said if code == 0 else f"not started: {said}"} if start else {"start": False}),
            **{name: told[name] for name in ("installer", "wanted", "asked", "major") if name in told}}


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


if __name__ == "__main__":
    told = json.loads(sys.argv[1])
    keep(told["record"], update(told))
