"""``cadgen doctor`` — report the installed cadgen and check a skill's version pin.

The per-verb skill shims used to enforce the requirements pin on every invocation;
the shims are gone (skills are instruction-only over the ``cadgen`` front door), so
this is the ONE documented check a skill teaches instead: run it from the skill
directory (or point it at a requirements.txt) and it says whether the installed
cadgen is the one the skill's docs were written against.

It also proves the CAD kernel loads, in a fresh interpreter (so this report
stays stdlib-only and fast): ``import OCP``, then cadgen's own kernel check --
the one the build path runs -- because an OCP that imports is not always one
cadgen builds against. A refused load is named for what it is when it can be
told (``cadgen._internal.kernel_load_hint``: on Windows 11, Smart App Control
blocking the unsigned ``.pyd``).

``--json`` prints the same report as ONE JSON object on stdout, for a program
to read (the desktop app's runtime probe is one). Its ``kernel.state`` is
``ok``, ``missing``, ``failed``, ``unsupported`` (OCP loads but cadgen's check
refuses it) or ``timeout`` (the kernel interpreter did not answer within
``CADGEN_DOCTOR_KERNEL_TIMEOUT``, which says nothing about whether it loads).

Exit codes, the same for both reports: 0 = the installed cadgen matches the pin
(or nothing claims a pin); 3 = pin mismatch, the code the old shims used; 4 =
the kernel failed to load or timed out. A kernel that is ``unsupported`` or
simply not installed exits 0: a no-deps install of the wheel (what the release
workflow smoke-tests) has no OCP and is still a correct install, and the
requirements pin is what puts the kernel there.

A mismatch has TWO fixes and they are not interchangeable, so the report picks
one by asking the install what KIND it is (:func:`_editable_source`). An
ordinary install is simply behind the pin, and
``python -m pip install -r requirements.txt`` fetches the pinned release. An
EDITABLE install records its version once, when it is installed, and never
re-reads the project's metadata — so its code can be current while the version
it reports is not, and that same command would swap the working tree being
developed for a published release. The fix there is to re-install it in place,
which re-records the version.

stdlib-only on purpose: this must work when the heavy dependency set is broken.
"""

from __future__ import annotations

import argparse
import os
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


def _editable_source() -> str | None:
    """The directory this cadgen was EDITABLE-installed from, or ``None``.

    ``pip install -e <dir>`` writes the project's version into the distribution's
    metadata at install time and records the source directory beside it
    (``direct_url.json``, PEP 610). The import path then points at that live
    directory, but the recorded version is a SNAPSHOT: nothing re-reads the
    project's metadata afterwards, so a source tree whose version has since been
    bumped keeps reporting the version it was installed at. That is not a wrong
    reading of the version -- it is what this interpreter really has installed --
    and it is why the mismatch above it may need a different command.

    Anything unreadable, unparseable or non-editable answers ``None``: a report
    that cannot tell says the ordinary thing rather than guessing.
    """
    import json
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        recorded = distribution("cadgen").read_text("direct_url.json")
    except (PackageNotFoundError, OSError):
        return None
    try:
        direct = json.loads(recorded or "")
    except ValueError:
        return None
    if not isinstance(direct, dict):
        return None
    directory = direct.get("dir_info")
    if not isinstance(directory, dict) or not directory.get("editable"):
        return None
    url = str(direct.get("url") or "")
    if not url.startswith("file://"):
        return None
    # url2pathname, not a prefix strip: a Windows record is file:///C:/... and
    # the path component of that is "/C:/...".
    from urllib.parse import unquote, urlparse
    from urllib.request import url2pathname

    return url2pathname(unquote(urlparse(url).path))


KERNEL_OK = "ok"
KERNEL_MISSING = "missing"
KERNEL_FAILED = "failed"
KERNEL_UNSUPPORTED = "unsupported"
KERNEL_TIMEOUT = "timeout"

# Run in the fresh interpreter. ``import OCP`` stays bare so a load that fails
# or crashes reads exactly as it did; cadgen's own kernel check follows, with
# this cadgen put first on the path so the child checks the same install.
_KERNEL_PROBE = """\
import sys
sys.path.insert(0, {root!r})
import json, OCP
verify = None
try:
    from cadgen._internal.op_memo import _runtime_versions
    _runtime_versions()
except Exception as error:
    verify = f"{{type(error).__name__}}: {{error}}"
    if error.__cause__ is not None:
        verify += f" ({{type(error.__cause__).__name__}}: {{error.__cause__}})"
print(json.dumps({{"path": OCP.__file__, "verify": verify}}))
"""


_KERNEL_TIMEOUT_ENV = "CADGEN_DOCTOR_KERNEL_TIMEOUT"
_KERNEL_TIMEOUT_DEFAULT = 300.0
_KERNEL_TIMEOUT_MAX = 3600.0


def _kernel_timeout() -> float:
    """Seconds the fresh kernel interpreter may take: ``CADGEN_DOCTOR_KERNEL_TIMEOUT``
    when it is a positive number, else 300. A program that runs doctor under
    its own deadline sets it shorter, so the child is ended here, by
    ``subprocess.run``, rather than orphaned when that program kills doctor.
    Not finite (``inf``, ``nan``) or not positive is the default, and nothing
    is longer than an hour: ``subprocess.run`` overflows on an infinite one."""
    import math

    try:
        value = float(os.environ.get(_KERNEL_TIMEOUT_ENV, ""))
    except ValueError:
        return _KERNEL_TIMEOUT_DEFAULT
    if not math.isfinite(value) or value <= 0:
        return _KERNEL_TIMEOUT_DEFAULT
    return min(value, _KERNEL_TIMEOUT_MAX)


def _run_kernel_probe() -> tuple[str, str, str | None]:
    """Import OCP, then run cadgen's kernel check, in a fresh interpreter:
    ``(state, detail, verify)``.

    ``state`` is ``KERNEL_OK`` (``detail`` is the module's path),
    ``KERNEL_MISSING`` (no OCP installed: ``ModuleNotFoundError``),
    ``KERNEL_FAILED`` (installed but would not load; ``detail`` is the last
    non-empty stderr line, the exception) or ``KERNEL_TIMEOUT``. A subprocess,
    so a kernel that crashes the interpreter cannot take the report down with
    it, and so this process never carries the kernel itself. ``verify`` is None
    when cadgen's check passed (or never ran, the kernel having failed to
    import), else that check's own words: an OCP from a distribution cadgen
    does not build against imports fine and fails here.
    """
    import json
    import subprocess

    root = str(Path(__file__).resolve().parent.parent.parent)
    timeout = _kernel_timeout()
    try:
        result = subprocess.run(
            [sys.executable, "-c", _KERNEL_PROBE.format(root=root)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # Not a verdict on the kernel: a cold disk can take longer than the
        # caller allowed. Its own state, so a caller can ask again. The
        # exception's text is the whole probe script; the time is the news.
        return KERNEL_TIMEOUT, f"timed out after {timeout:g} s", None
    except OSError as error:
        return KERNEL_FAILED, f"{type(error).__name__}: {error}", None
    if result.returncode == 0:
        lines = [text for text in result.stdout.splitlines() if text.strip()]
        last = lines[-1].strip() if lines else ""
        try:
            answer = json.loads(last)
        except ValueError:
            return KERNEL_OK, last, None
        if not isinstance(answer, dict):
            return KERNEL_OK, last, None
        verify = answer.get("verify")
        verify = verify if isinstance(verify, str) and verify else None
        return KERNEL_OK, str(answer.get("path") or ""), verify
    lines = [text for text in result.stderr.splitlines() if text.strip()]
    detail = lines[-1].strip() if lines else f"exit status {result.returncode}"
    if detail.startswith("ModuleNotFoundError:"):
        return KERNEL_MISSING, detail, None
    return KERNEL_FAILED, detail, None


def kernel_status() -> dict:
    """The kernel as ``--json`` reports it: ``{ok, state, path, error}``.

    ``ok`` only when OCP loads AND cadgen's kernel check accepts it; ``error``
    is the words of whichever step refused, verbatim.
    """
    state, detail, verify = _run_kernel_probe()
    if state == KERNEL_OK and verify is not None:
        return {"ok": False, "state": KERNEL_UNSUPPORTED, "path": detail or None, "error": verify}
    if state == KERNEL_OK:
        return {"ok": True, "state": KERNEL_OK, "path": detail or None, "error": None}
    return {"ok": False, "state": state, "path": None, "error": detail}


def _pin_status(target: str | None, installed: str) -> tuple[Path | None, str | None, str]:
    """``(requirements, pinned, state)``; ``state`` is ``none``, ``unpinned``,
    ``ok`` or ``mismatch``."""
    from cadgen.cli import read_requirements_pin

    requirements = _resolve_requirements(target)
    if requirements is None:
        return None, None, "none"
    pinned = read_requirements_pin(requirements)
    if pinned is None:
        return requirements, None, "unpinned"
    return requirements, pinned, "ok" if pinned == installed else "mismatch"


def _exit_code(kernel: dict, pin_state: str) -> int:
    """Both reports' exit code: a pin mismatch outranks the kernel."""
    if pin_state == "mismatch":
        return 3
    return 4 if kernel["state"] in (KERNEL_FAILED, KERNEL_TIMEOUT) else 0


def _viewer_status() -> dict:
    """Whether ``cadgen.viewer`` imports: ``{ok, error}``."""
    try:
        import cadgen.viewer  # noqa: F401
    except Exception as error:  # the report must survive a broken viewer
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    return {"ok": True, "error": None}


def main(argv: list[str] | None = None, prog: str = "cadgen doctor") -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print the installed cadgen and verify a skill's cadgen version pin.",
        epilog=(
            "Exit codes: 0 ok, 3 pin mismatch, 4 CAD kernel failed to load or timed out. "
            f"{_KERNEL_TIMEOUT_ENV} (seconds, default {_KERNEL_TIMEOUT_DEFAULT:g}, "
            f"at most {_KERNEL_TIMEOUT_MAX:g}) bounds the fresh interpreter the kernel "
            "is loaded in."
        ),
    )
    parser.add_argument(
        "requirements",
        nargs="?",
        help="A requirements.txt, or a directory containing one (default: the working directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as one JSON object (version, python, install, viewer, kernel, pin).",
    )
    args = parser.parse_args(argv)
    if args.json:
        return _main_json(args.requirements)

    import cadgen

    installed = getattr(cadgen, "__version__", "unknown")
    location = Path(cadgen.__file__).resolve().parent
    sys.stdout.write(f"cadgen {installed}\n")
    sys.stdout.write(f"  python   {sys.version.split()[0]} ({sys.executable})\n")
    sys.stdout.write(f"  install  {location}\n")

    from cadgen._internal.kernel_load_hint import kernel_load_hint

    kernel = kernel_status()
    state = kernel["state"]
    if state == KERNEL_UNSUPPORTED:
        # OCP loads, but cadgen's own kernel check refuses it: like a missing
        # kernel, not an exit-code failure.
        path = kernel["path"] or ""
        sys.stdout.write(f"  kernel   unsupported: {kernel['error']} (OCP at {path})\n")
    elif state == KERNEL_OK:
        sys.stdout.write(f"  kernel   OK — OCP at {kernel['path'] or ''}\n")
    elif state == KERNEL_MISSING:
        # Not a failure: the requirements pin installs the kernel, and a wheel
        # installed --no-deps (the release smoke test) legitimately has none.
        sys.stdout.write(
            "  kernel   not installed — OCP is absent from this interpreter "
            "(python -m pip install -r requirements.txt puts it there)\n"
        )
    elif state == KERNEL_TIMEOUT:
        sys.stderr.write(f"  kernel   timed out — {kernel['error']}\n")
    else:
        sys.stderr.write(f"  kernel   FAILED — {kernel['error']}\n")
        for hint in kernel_load_hint(kernel["error"]) or ():
            sys.stderr.write(f"           {hint}\n")

    requirements, pin, pin_state = _pin_status(args.requirements, installed)
    if pin_state == "none":
        sys.stdout.write("  pin      none found (no requirements.txt to check)\n")
    elif pin_state == "unpinned":
        # A bare `cadgen` line (or none): nothing to enforce.
        sys.stdout.write(f"  pin      unpinned in {requirements}\n")
    elif pin_state == "ok":
        sys.stdout.write(f"  pin      OK — cadgen=={pin} ({requirements})\n")
    else:
        sys.stderr.write(
            f"  pin      MISMATCH — {requirements} pins cadgen=={pin}, "
            f"but cadgen {installed} is installed.\n"
        )
        editable = _editable_source()
        if editable is None:
            sys.stderr.write(
                "From the skill directory run:\n"
                "  python -m pip install -r requirements.txt\n"
            )
        else:
            # The install is a live source tree, so the code may already BE the
            # pinned version: what is stale is the version this install recorded
            # when it was made. Naming the other command here would exchange that
            # source tree for a published release, which is not the fix.
            sys.stderr.write(
                f"This cadgen is an EDITABLE install of {editable}. Its version was recorded when\n"
                "it was installed and is never re-read, so the code can be current while the\n"
                "version it reports is not. Re-install it in place to re-record it:\n"
                f"  python -m pip install -e {editable}\n"
                "(python -m pip install -r requirements.txt would replace that source tree with a\n"
                "published release instead.)\n"
            )
    return _exit_code(kernel, pin_state)


def _main_json(target: str | None) -> int:
    """``--json``: the report as one object on stdout, the text report's exit code."""
    import json

    import cadgen

    installed = getattr(cadgen, "__version__", "unknown")
    kernel = kernel_status()
    requirements, pinned, pin_state = _pin_status(target, installed)
    report = {
        "version": installed,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "install": str(Path(cadgen.__file__).resolve().parent),
        "viewer": _viewer_status(),
        "kernel": kernel,
        "pin": {
            "state": pin_state,
            "file": str(requirements) if requirements is not None else None,
            "pinned": pinned,
        },
    }
    sys.stdout.write(json.dumps(report) + "\n")
    return _exit_code(kernel, pin_state)


if __name__ == "__main__":
    raise SystemExit(main())
