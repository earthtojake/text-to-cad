"""``mujoco-studio`` as ``cad run mujoco-studio ARGS`` runs it: MuJoCo Studio's own command line, its web viewer.

The mujoco integration declares the command (``cad.registry.INTEGRATIONS["mujoco"].commands``), so the server's
``cad run`` makes the environment of ``cad[mujoco]`` for it and runs this module with that environment's
Python (``python -P -m cad.mujoco._command mujoco-studio ARGS``). The program is the environment's own
``mujoco-studio``, the console script ``mujoco-studio`` installs beside this Python, never one on PATH. An
environment with no script (one made before the extra carried Studio) has none to run: the run says so and
exits 2.

Its arguments are passed through as given, with two defaults put first where they name neither:
``--gfx=web`` (Studio's web viewer, served from this process: an agent's sandbox has no display, and the
person opens the URL Studio prints) and ``--hot_reload=model`` (an edit of the model file shows at once).
Its stdin, stdout, stderr and exit code are Studio's; relative paths are the caller's folder's.

The web viewer listens on every network interface, with no authentication: MuJoCo 4.0 binds ``::`` in
``WebViewer`` itself, with no host in its ``ViewerConfig``, its command line or its environment (pinning it
to loopback would mean replacing Studio's private socket binding). So a run of the web viewer says so first,
on stderr, in one line (``EXPOSED``), as MuJoCo's own banner and documentation warn: it is for this computer
or a trusted network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__ = ["DEFAULTS", "EXPOSED", "arguments", "main", "program"]

# Our defaults, each put first where the arguments name neither its option nor a value of it.
DEFAULTS = (("--gfx", "web"), ("--hot_reload", "model"))
EXPOSED = ("cad run: MuJoCo Studio's web viewer listens on every network interface with no authentication, as "
           "MuJoCo's documentation warns: use it on this computer or a trusted network")


def program(name: str = "mujoco-studio") -> Path | None:
    """The ``mujoco-studio`` to run: the environment's own, mujoco-studio's console script beside this
    Python; None where this environment has none."""
    folder = Path(sys.executable).parent
    return next((folder / item for item in (name, f"{name}.exe") if (folder / item).is_file()), None)


def _given(args: list[str]) -> dict[str, str | None]:
    """The options the arguments name before any ``--``, each with its value (None for one given last with
    none), as Studio's parser reads ``--option value`` and ``--option=value``."""
    named: dict[str, str | None] = {}
    for index, item in enumerate(args):
        if item == "--":
            break
        option, has, value = item.partition("=")
        if option.startswith("--"):
            named[option] = value if has else (args[index + 1] if index + 1 < len(args) else None)
    return named


def arguments(args: list[str]) -> list[str]:
    """Studio's arguments: ``args`` as given, ``DEFAULTS`` put first for each option they do not name."""
    named = _given(args)
    return [*(f"{option}={value}" for option, value in DEFAULTS if option not in named), *args]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    name, rest = (args[0], args[1:]) if args else ("mujoco-studio", [])
    found = program(name)
    if found is None:
        print(f"cad run: {name} is not in this environment: it comes with cad's mujoco integration, cad[mujoco] "
              "(mujoco-studio)", file=sys.stderr)
        return 2
    command = [str(found), *arguments(rest)]
    if _given(command[1:]).get("--gfx") == "web" and not {"-h", "--help"} & set(rest):
        print(EXPOSED, file=sys.stderr, flush=True)
    sys.stdout.flush()
    try:
        child = subprocess.Popen(command)
    except OSError as error:
        print(f"cad run: cannot run {found}: {error.strerror or error}", file=sys.stderr)
        return 1
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:  # Studio was interrupted too: its exit code is the run's
            continue


if __name__ == "__main__":
    raise SystemExit(main())
