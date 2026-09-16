"""``cadgen doctor`` — report the installed cadgen and check a skill's version pin.

The per-verb skill shims used to enforce the requirements pin on every invocation;
the shims are gone (skills are instruction-only over the ``cadgen`` front door), so
this is the ONE documented check a skill teaches instead: run it from the skill
directory (or point it at a requirements.txt) and it says whether the installed
cadgen is the one the skill's docs were written against.

It also proves the CAD kernel loads. ``OCP`` is imported in a fresh interpreter
(never in this one, so the report itself stays stdlib-only and fast to reach),
and a refused load is named for what it is: on Windows 11 that is Smart App
Control blocking the unsigned ``.pyd``, which the bare ``ImportError`` never
says (``cadgen._internal.kernel_load_hint``).

Exit codes: 0 = installed cadgen matches the pin (or nothing claims a pin);
3 = pin mismatch, same code the shims used, since the fix is the same
(``python -m pip install -r requirements.txt``); 4 = the kernel is installed
but cannot be loaded (the report says why when it can tell). A kernel that is
simply not installed is reported, not failed: a no-deps install of the wheel
(what the release workflow smoke-tests) has no OCP and is still a correct
install, and the requirements pin is what puts the kernel there.

stdlib-only on purpose: this must work when the heavy dependency set is broken.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _resolve_requirements(target: str | None) -> Path | None:
    """The requirements.txt to check: an explicit file, a directory containing one,
    or the working directory's — ``None`` when nothing exists to check."""
    base = Path(target).expanduser() if target else Path.cwd()
    if base.is_file():
        return base
    candidate = base / "requirements.txt"
    return candidate if candidate.is_file() else None


KERNEL_OK = "ok"
KERNEL_MISSING = "missing"
KERNEL_FAILED = "failed"


def _probe_kernel() -> tuple[str, str]:
    """Import OCP in a fresh interpreter: ``(state, detail)``.

    ``state`` is ``KERNEL_OK`` (``detail`` is the module's path),
    ``KERNEL_MISSING`` (no OCP installed: ``ModuleNotFoundError``), or
    ``KERNEL_FAILED`` (installed but would not load; ``detail`` is the last
    non-empty stderr line, the exception). A subprocess, so a kernel that
    crashes the interpreter or takes the ~2.5 s import cannot take the report
    down with it, and so this process never carries the kernel itself.
    """
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-c", "import OCP; print(OCP.__file__)"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return KERNEL_FAILED, f"{type(error).__name__}: {error}"
    if result.returncode == 0:
        lines = [text for text in result.stdout.splitlines() if text.strip()]
        return KERNEL_OK, lines[-1].strip() if lines else ""
    lines = [text for text in result.stderr.splitlines() if text.strip()]
    detail = lines[-1].strip() if lines else f"exit status {result.returncode}"
    if detail.startswith("ModuleNotFoundError:"):
        return KERNEL_MISSING, detail
    return KERNEL_FAILED, detail


def main(argv: list[str] | None = None, prog: str = "cadgen doctor") -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print the installed cadgen and verify a skill's cadgen version pin.",
    )
    parser.add_argument(
        "requirements",
        nargs="?",
        help="A requirements.txt, or a directory containing one (default: the working directory).",
    )
    args = parser.parse_args(argv)

    import cadgen
    from cadgen.cli import read_requirements_pin

    installed = getattr(cadgen, "__version__", "unknown")
    location = Path(cadgen.__file__).resolve().parent
    sys.stdout.write(f"cadgen {installed}\n")
    sys.stdout.write(f"  python   {sys.version.split()[0]} ({sys.executable})\n")
    sys.stdout.write(f"  install  {location}\n")

    from cadgen._internal.kernel_load_hint import kernel_load_hint

    kernel_state, detail = _probe_kernel()
    kernel_loaded = kernel_state != KERNEL_FAILED
    if kernel_state == KERNEL_OK:
        sys.stdout.write(f"  kernel   OK — OCP at {detail}\n")
    elif kernel_state == KERNEL_MISSING:
        # Not a failure: the requirements pin installs the kernel, and a wheel
        # installed --no-deps (the release smoke test) legitimately has none.
        sys.stdout.write(
            "  kernel   not installed — OCP is absent from this interpreter "
            "(python -m pip install -r requirements.txt puts it there)\n"
        )
    else:
        sys.stderr.write(f"  kernel   FAILED — {detail}\n")
        for hint in kernel_load_hint(detail) or ():
            sys.stderr.write(f"           {hint}\n")

    requirements = _resolve_requirements(args.requirements)
    if requirements is None:
        sys.stdout.write("  pin      none found (no requirements.txt to check)\n")
        return 0 if kernel_loaded else 4

    pin = read_requirements_pin(requirements)
    if pin is None:
        # A bare `cadgen` line (or none): nothing to enforce.
        sys.stdout.write(f"  pin      unpinned in {requirements}\n")
        return 0 if kernel_loaded else 4
    if pin == installed:
        sys.stdout.write(f"  pin      OK — cadgen=={pin} ({requirements})\n")
        return 0 if kernel_loaded else 4
    sys.stderr.write(
        f"  pin      MISMATCH — {requirements} pins cadgen=={pin}, "
        f"but cadgen {installed} is installed.\n"
        "From the skill directory run:\n"
        "  python -m pip install -r requirements.txt\n"
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
