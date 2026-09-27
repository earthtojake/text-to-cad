"""Repository-only benchmark metadata; no CAD imports or runtime changes."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def command(*args: str) -> str:
    try:
        return subprocess.check_output(args, cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    roots = [REPO / "packages/cadgen/src/cadgen", REPO / "packages/core/src"]
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "_runtime" in path.parts or path.suffix not in {".py", ".js", ".mjs"}:
                continue
            digest.update(str(path.relative_to(REPO)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def peak_rss_bytes() -> int:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss if sys.platform == "darwin" else rss * 1024)


def metadata() -> dict:
    versions = {}
    for package in ("cadgen", "build123d", "cadquery-ocp", "numpy"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    return {
        "timeUtc": datetime.now(timezone.utc).isoformat(),
        "gitHead": command("git", "rev-parse", "HEAD"),
        "sourceFingerprint": source_fingerprint(),
        "python": sys.version, "pythonExecutable": sys.executable,
        "platform": platform.platform(), "machine": platform.machine(),
        "cpuCount": os.cpu_count(),
        "cpu": command("sysctl", "-n", "machdep.cpu.brand_string") if sys.platform == "darwin" else platform.processor(),
        "physicalMemoryBytes": command("sysctl", "-n", "hw.memsize") if sys.platform == "darwin" else None,
        "node": command("node", "--version"), "versions": versions,
        "environment": {key: value for key, value in os.environ.items() if key.startswith("CADGEN_") and
                        not any(word in key for word in ("KEY", "TOKEN", "AUTH", "SOCKET"))},
    }


def model_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(REPO / "models"):
        raise ValueError(f"CAD inputs and generated artifacts must be under {REPO / 'models'}: {path}")
    return path


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
