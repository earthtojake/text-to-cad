"""``cadgen doctor`` — report the installed cadgen and check a skill's version pin.

The per-verb skill shims used to enforce the requirements pin on every invocation;
the shims are gone (skills are instruction-only over the ``cadgen`` front door), so
this is the ONE documented check a skill teaches instead: run it from the skill
directory (or point it at a requirements.txt) and it says whether the installed
cadgen is the one the skill's docs were written against.

Exit codes: 0 = installed cadgen matches the pin (or nothing claims a pin);
3 = mismatch, same code the shims used, since the fix is the same
(``python -m pip install -r requirements.txt``).

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

    requirements = _resolve_requirements(args.requirements)
    if requirements is None:
        sys.stdout.write("  pin      none found (no requirements.txt to check)\n")
        return 0

    pin = read_requirements_pin(requirements)
    if pin is None:
        # A bare `cadgen` line (or none): nothing to enforce.
        sys.stdout.write(f"  pin      unpinned in {requirements}\n")
        return 0
    if pin == installed:
        sys.stdout.write(f"  pin      OK — cadgen=={pin} ({requirements})\n")
        return 0
    sys.stderr.write(
        f"  pin      MISMATCH — {requirements} pins cadgen=={pin}, "
        f"but cadgen {installed} is installed.\n"
        "From the skill directory run:\n"
        "  python -m pip install -r requirements.txt\n"
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
