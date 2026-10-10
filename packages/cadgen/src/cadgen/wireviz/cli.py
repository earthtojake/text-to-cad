"""Running ``wireviz`` on a harness document, in a folder of its own.

Every run stages the document's exact bytes in a temporary folder and tells
WireViz to write there, so nothing is ever written beside a person's file and
what WireViz read is exactly what the caller hashed. WireViz reports a bad
document as a Python traceback; the last line is the reason, and that is what
:class:`WirevizRunError` carries.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from cadgen.wireviz.install import WirevizInstall

__all__ = ["WirevizRunError", "run_wireviz"]

_TIMEOUT_SECONDS = 300
_INPUT_NAME = "harness.yml"


class WirevizRunError(RuntimeError):
    """``wireviz`` failed; the message carries its reason."""


def _reason(completed: subprocess.CompletedProcess) -> str:
    lines = [line.strip() for line in ((completed.stderr or "") + "\n" + (completed.stdout or "")).splitlines() if line.strip()]
    errors = [line for line in lines if re.match(r"^[A-Za-z_.]*(Error|Exception|NotFound)\b", line)]
    last = (errors or lines or [f"exit status {completed.returncode}"])[-1]
    return re.sub(r"^[A-Za-z_.]*(Error|Exception|NotFound):\s*", "", last)


def run_wireviz(install: WirevizInstall, document: bytes, *, formats: str, name: str) -> dict[str, bytes]:
    """Run ``wireviz -f formats`` over ``document``; return what it wrote, by file name.

    ``formats`` is WireViz's letters (``s`` an SVG, ``t`` the BOM as TSV); the
    files are named ``name.svg``, ``name.bom.tsv``.
    """
    with tempfile.TemporaryDirectory(prefix="cadgen-wireviz-") as folder:
        stage = Path(folder)
        (stage / _INPUT_NAME).write_bytes(document)
        out = stage / "out"
        out.mkdir()
        try:
            completed = subprocess.run(
                [str(install.cli), "--format", formats, "--output-dir", str(out), "--output-name", name, _INPUT_NAME],
                cwd=str(stage),
                env=install.env(),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise WirevizRunError(f"wireviz did not finish in {_TIMEOUT_SECONDS} s") from None
        except OSError as error:
            raise WirevizRunError(f"wireviz could not be run ({install.cli}): {error}") from None
        if completed.returncode != 0:
            raise WirevizRunError(_reason(completed))
        return {path.name: path.read_bytes() for path in sorted(out.iterdir()) if path.is_file()}

