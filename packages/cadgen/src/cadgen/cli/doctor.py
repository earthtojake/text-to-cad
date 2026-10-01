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

It then runs cadgen's own kernel check in that same fresh interpreter -- the
one the build path runs, which also resolves the distribution OCP came from --
because an OCP that imports is not always one cadgen builds against. A refusal
is reported as ``kernel   unsupported: <the check's words>`` (``--json``: state
``unsupported``) and, like a kernel that is not installed, exits 0.

``--json`` prints the same report as ONE JSON object on stdout, for a program
to read (the desktop app's runtime probe is one): ``version``, ``python``,
``install``, ``viewer`` (``{ok, error}``: whether ``cadgen.viewer`` imports),
``kernel`` (``{ok, state, path, error}``; ``state`` is ``ok``, ``missing``,
``failed``, ``unsupported`` -- OCP loads but cadgen's kernel check refuses
it -- or ``timeout`` -- the kernel interpreter did not answer in time, which
says nothing about whether it loads -- and ``ok`` is true only for ``ok``) and ``pin`` (``{state, file,
pinned}``; ``state`` is ``none``, ``unpinned``, ``ok`` or ``mismatch``). The
exit code is the text report's.
``CADGEN_DOCTOR_KERNEL_TIMEOUT`` (seconds, default 300, at most 3600) bounds
the fresh kernel interpreter, for a caller that runs doctor under a deadline of
its own. A timed-out kernel exits 4, as a failed one always has.

Exit codes: 0 = installed cadgen matches the pin (or nothing claims a pin);
3 = pin mismatch, the same code the shims used; 4 = the kernel is installed
but cannot be loaded (the report says why when it can tell), or its fresh
interpreter did not answer within ``CADGEN_DOCTOR_KERNEL_TIMEOUT``. A kernel
that refuses cadgen's check (``unsupported``) exits 0. A kernel that is
simply not installed is reported, not failed: a no-deps install of the wheel
(what the release workflow smoke-tests) has no OCP and is still a correct
install, and the requirements pin is what puts the kernel there.

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

    ``state``/``detail`` are :func:`_probe_kernel`'s. ``verify`` is None when
    cadgen's check passed (or never ran, the kernel having failed to import),
    else that check's own words: an OCP from a distribution cadgen does not
    build against imports fine and fails here.
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
        return KERNEL_OK, str(answer.get("path") or ""), verify if isinstance(verify, str) and verify else None
    lines = [text for text in result.stderr.splitlines() if text.strip()]
    detail = lines[-1].strip() if lines else f"exit status {result.returncode}"
    if detail.startswith("ModuleNotFoundError:"):
        return KERNEL_MISSING, detail, None
    return KERNEL_FAILED, detail, None


def _probe_kernel() -> tuple[str, str]:
    """Import OCP in a fresh interpreter: ``(state, detail)``.

    ``state`` is ``KERNEL_OK`` (``detail`` is the module's path),
    ``KERNEL_MISSING`` (no OCP installed: ``ModuleNotFoundError``), or
    ``KERNEL_FAILED`` (installed but would not load; ``detail`` is the last
    non-empty stderr line, the exception). A subprocess, so a kernel that
    crashes the interpreter or takes the ~2.5 s import cannot take the report
    down with it, and so this process never carries the kernel itself.
    """
    state, detail, _ = _run_kernel_probe()
    return state, detail


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
    from cadgen.cli import read_requirements_pin

    installed = getattr(cadgen, "__version__", "unknown")
    location = Path(cadgen.__file__).resolve().parent
    sys.stdout.write(f"cadgen {installed}\n")
    sys.stdout.write(f"  python   {sys.version.split()[0]} ({sys.executable})\n")
    sys.stdout.write(f"  install  {location}\n")

    from cadgen._internal.kernel_load_hint import kernel_load_hint

    kernel_state, detail, verify = _run_kernel_probe()
    kernel_loaded = kernel_state not in (KERNEL_FAILED, KERNEL_TIMEOUT)
    if kernel_state == KERNEL_OK and verify is not None:
        # OCP loads, but cadgen's own kernel check refuses it: the same verdict
        # --json reports, and like a missing kernel not an exit-code failure.
        sys.stdout.write(f"  kernel   unsupported: {verify} (OCP at {detail})\n")
    elif kernel_state == KERNEL_OK:
        sys.stdout.write(f"  kernel   OK — OCP at {detail}\n")
    elif kernel_state == KERNEL_MISSING:
        # Not a failure: the requirements pin installs the kernel, and a wheel
        # installed --no-deps (the release smoke test) legitimately has none.
        sys.stdout.write(
            "  kernel   not installed — OCP is absent from this interpreter "
            "(python -m pip install -r requirements.txt puts it there)\n"
        )
    elif kernel_state == KERNEL_TIMEOUT:
        sys.stderr.write(f"  kernel   timed out — {detail}\n")
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
    return 3


def _main_json(target: str | None) -> int:
    """``--json``: the report as one object on stdout, the text report's exit code."""
    import json

    import cadgen
    from cadgen.cli import read_requirements_pin

    installed = getattr(cadgen, "__version__", "unknown")
    kernel = kernel_status()
    requirements = _resolve_requirements(target)
    pinned = read_requirements_pin(requirements) if requirements is not None else None
    if requirements is None:
        pin_state = "none"
    elif pinned is None:
        pin_state = "unpinned"
    else:
        pin_state = "ok" if pinned == installed else "mismatch"
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
    if pin_state == "mismatch":
        return 3
    return 4 if kernel["state"] in (KERNEL_FAILED, KERNEL_TIMEOUT) else 0


if __name__ == "__main__":
    raise SystemExit(main())
