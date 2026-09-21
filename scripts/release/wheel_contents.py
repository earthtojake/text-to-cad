"""Stage a clean wheel build and verify its bundled runtime against source."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil
import sys
import zipfile


def stage_package(source: Path, destination: Path) -> None:
    def ignore(directory, names):
        return [name for name in names if
                name == "__pycache__" or name.endswith((".pyc", ".egg-info")) or
                (Path(directory) == source and name in {"build", "dist"})]

    shutil.copytree(source, destination, ignore=ignore)


def verify_runtime(wheel: Path, package: Path) -> int:
    runtime = package / "src" / "cadgen" / "_runtime"
    expected = {
        "cadgen/_runtime/" + path.relative_to(runtime).as_posix(): path
        for path in runtime.rglob("*") if path.is_file()
    }
    if not expected:
        raise ValueError(f"No bundled runtime files in {runtime}; run scripts/bundle/bundle.sh")
    with zipfile.ZipFile(wheel) as archive:
        entries = [entry for entry in archive.infolist()
                   if entry.filename.startswith("cadgen/_runtime/") and not entry.is_dir()]
        counts = Counter(entry.filename for entry in entries)
        missing = sorted(expected.keys() - counts.keys())
        extra = sorted(counts.keys() - expected.keys())
        duplicates = sorted(name for name, count in counts.items() if count != 1)
        changed = sorted(name for name in expected.keys() & counts.keys()
                         if archive.read(name) != expected[name].read_bytes())
    problems = [("missing", missing), ("extra", extra), ("duplicate", duplicates),
                ("different bytes", changed)]
    details = [f"{label}: {', '.join(names)}" for label, names in problems if names]
    if details:
        raise ValueError("Wheel runtime differs from bundled source:\n" + "\n".join(details))
    return len(expected)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in {"stage", "verify"}:
        raise SystemExit("usage: wheel_contents.py stage SOURCE DEST | verify WHEEL PACKAGE")
    try:
        if sys.argv[1] == "stage":
            stage_package(Path(sys.argv[2]), Path(sys.argv[3]))
        else:
            count = verify_runtime(Path(sys.argv[2]), Path(sys.argv[3]))
            print(f"Wheel runtime exactly matches bundled source ({count} files, identical bytes).")
    except ValueError as error:
        raise SystemExit(str(error)) from error
