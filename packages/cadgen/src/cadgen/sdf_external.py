from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from cadgen.findings import FindingsReport

GzCheckMode = str

# An external `gz sdf --check` resolves the document's own <include>/<uri> references.
# Bound it: a reference to a host that accepts but never answers must not hang the verb forever.
GZ_CHECK_TIMEOUT = 60.0
# The <uri> schemes gz may resolve over the network (an <include>'s model, a mesh by URL, a Fuel
# asset). The document names them, not the person validating it, and nothing waits on the
# network unasked: gz does not run on a document that names one unless the caller allows it.
REMOTE_SCHEMES = frozenset({"http", "https", "fuel"})


def remote_references(xml_text: str) -> list[str] | None:
    """The document's ``<uri>`` references that name a remote scheme, in document order; None
    when the text does not parse as XML (so its references cannot be read before gz reads them)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    found = []
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == "uri":
            text = (element.text or "").strip()
            if urlsplit(text).scheme.lower() in REMOTE_SCHEMES:
                found.append(text)
    return found


def run_gz_sdf_check(xml_text: str, *, output_path: Path, mode: GzCheckMode = "auto",
                     remote: bool = False) -> FindingsReport:
    result = FindingsReport()
    normalized_mode = str(mode or "auto").strip().lower()
    if normalized_mode not in {"auto", "required", "never"}:
        raise ValueError("gz_check must be one of: auto, required, never")
    if normalized_mode == "never":
        result.add("info", "gz_check_skipped", "gz sdf --check skipped by request")
        return result

    gz_path = shutil.which("gz")
    if gz_path is None:
        # Under `auto` an absent tool is a note, never a finding against the FILE.
        # `auto` means "run gz if it is here", so a machine without Gazebo would
        # otherwise fail every clean document -- and, because `--strict` promotes
        # warnings, fail it blockingly. Asking for the check with `required` is the
        # way to say its absence is an error.
        if normalized_mode == "required":
            result.add(
                "error",
                "gz_check_unavailable",
                "gz sdf --check could not run: 'gz' is not on PATH",
            )
            return result
        result.add(
            "info",
            "gz_check_unavailable",
            "gz sdf --check skipped because 'gz' is not on PATH",
        )
        return result

    if not remote:
        references = remote_references(xml_text)
        if references is None or references:
            why = ("the document does not parse as XML, so its references cannot be read before gz resolves them"
                   if references is None else
                   f"the document names {len(references)} remote reference{'s' if len(references) != 1 else ''} "
                   f"gz would fetch ({', '.join(references[:3])}{', ...' if len(references) > 3 else ''})")
            level = "error" if normalized_mode == "required" else "info"
            result.add(level, "gz_check_remote",
                       f"gz sdf --check not run: {why}; pass gz_remote (--gz-remote) to let gz reach them")
            return result

    # The scratch copy lives BESIDE the output, not in a temp dir: `gz sdf --check`
    # resolves relative `<uri>`s (meshes, includes) against the file's own
    # directory, so a copy elsewhere would report every relative reference missing.
    output_parent = output_path.resolve().parent
    output_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sdf", dir=output_parent, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(xml_text if xml_text.endswith("\n") else xml_text + "\n")
    try:
        completed = subprocess.run(
            [gz_path, "sdf", "--check", str(temp_path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            timeout=GZ_CHECK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        result.add("error", "gz_check_failed",
                   f"gz sdf --check did not finish within {GZ_CHECK_TIMEOUT:g}s")
        return result
    except OSError as exc:
        result.add("error", "gz_check_failed", f"gz sdf --check could not start: {exc}")
        return result
    finally:
        temp_path.unlink(missing_ok=True)

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        message = "gz sdf --check failed"
        if details:
            message = f"{message}: {details}"
        result.add("error", "gz_check_failed", message)
    else:
        result.add("info", "gz_check_passed", "gz sdf --check passed")
    return result
