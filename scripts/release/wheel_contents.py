"""Stage a clean wheel build and verify its bundled runtime against source, and the plugin it carries
against the repository's own files."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PLUGIN = "cad_server/_runtime/plugin/"


def stage_package(source: Path, destination: Path) -> None:
    def ignore(directory, names):
        return [name for name in names if
                name == "__pycache__" or name.endswith((".pyc", ".egg-info")) or
                (Path(directory) == source and name in {"build", "dist"})]

    shutil.copytree(source, destination, ignore=ignore)


def verify_runtime(wheel: Path, package: Path) -> int:
    runtime = package / "src" / "cad_server" / "_runtime"
    expected = {
        "cad_server/_runtime/" + path.relative_to(runtime).as_posix(): path
        for path in runtime.rglob("*") if path.is_file()
    }
    if not expected:
        raise ValueError(f"No bundled runtime files in {runtime}; run scripts/bundle/bundle.sh")
    with zipfile.ZipFile(wheel) as archive:
        entries = [entry for entry in archive.infolist()
                   if entry.filename.startswith("cad_server/_runtime/") and not entry.is_dir()]
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


def skill_files(repo: Path) -> list[str]:
    """The skills' files as the bundle copies them (scripts/bundle/cadgen-runtime.sh's plugin stage): what
    git keeps under skills/ (tracked, or new and not ignored) that is a file; without git, every file but a
    hidden one or bytecode."""
    try:
        listed = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                                 "--", "skills"], check=True, capture_output=True).stdout.decode("utf-8")
        names = sorted({name for name in listed.split("\0") if name and (repo / name).is_file()})
    except (OSError, subprocess.CalledProcessError):
        names = sorted(path.relative_to(repo).as_posix() for path in (repo / "skills").rglob("*")
                       if path.is_file() and not any(part.startswith(".") or part == "__pycache__"
                                                     for part in path.relative_to(repo).parts)
                       and path.suffix != ".pyc")
    return names


def verify_plugin(wheel: Path, repo: Path, files: list[str]) -> int:
    """The plugin the server's wheel carries is the repository's: each of ``files`` (the plugin's files
    beside its skills) and every skill file, byte for byte, and nothing else."""
    expected = {PLUGIN + name: repo / name for name in [*files, *skill_files(repo)]}
    if not any(name.startswith(PLUGIN + "skills/") for name in expected):
        raise ValueError(f"No skills under {repo / 'skills'}")
    with zipfile.ZipFile(wheel) as archive:
        entries = Counter(entry.filename for entry in archive.infolist()
                          if entry.filename.startswith(PLUGIN) and not entry.is_dir())
        missing = sorted(expected.keys() - entries.keys())
        extra = sorted(entries.keys() - expected.keys())
        duplicates = sorted(name for name, count in entries.items() if count != 1)
        changed = sorted(name for name in expected.keys() & entries.keys()
                         if archive.read(name) != expected[name].read_bytes())
    problems = [("missing", missing), ("extra", extra), ("duplicate", duplicates), ("different bytes", changed)]
    details = [f"{label}: {', '.join(names)}" for label, names in problems if names]
    if details:
        raise ValueError("The plugin in the wheel differs from the repository's:\n" + "\n".join(details))
    return len(expected)


if __name__ == "__main__":
    usage = "usage: wheel_contents.py stage SOURCE DEST | verify WHEEL PACKAGE | plugin WHEEL REPO FILE..."
    if len(sys.argv) < 4 or sys.argv[1] not in {"stage", "verify", "plugin"} \
            or (sys.argv[1] != "plugin" and len(sys.argv) != 4):
        raise SystemExit(usage)
    try:
        if sys.argv[1] == "stage":
            stage_package(Path(sys.argv[2]), Path(sys.argv[3]))
        elif sys.argv[1] == "verify":
            count = verify_runtime(Path(sys.argv[2]), Path(sys.argv[3]))
            print(f"Wheel runtime exactly matches bundled source ({count} files, identical bytes).")
        else:
            count = verify_plugin(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:])
            print(f"The wheel's plugin is the repository's: its files and skills/ ({count} files, identical bytes).")
    except ValueError as error:
        raise SystemExit(str(error)) from error
