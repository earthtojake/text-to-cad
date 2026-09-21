from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from cadgen.findings import FindingsReport

GzCheckMode = str


def run_gz_sdf_check(xml_text: str, *, output_path: Path, mode: GzCheckMode = "auto") -> FindingsReport:
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
        )
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
