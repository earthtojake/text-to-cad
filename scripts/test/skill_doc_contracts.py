"""Run prose contracts, including real documented examples, without runtime suites.

New skill documentation tests use test_documented*.py, test_skill_structure.py
or test_report_template.py. They also remain in the ordinary full skill suite.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
GLOBAL_CONTRACTS = (
    "test_documented_commands.py",
    "test_skill_requirements.py",
    "test_skill_self_containment.py",
    "test_package_boundaries.py",
    "test_plugin_manifests.py",
    "test_ci_workspace_selection.py",
    "test_source_text_bytes.py",
)
PATTERNS = ("test_documented*.py", "test_skill_structure.py", "test_report_template.py")
# This existing mixed module also holds prose contracts. Keep its full coverage
# until it is split; it needs no browser or generated runtime.
EXTRA_CONTRACTS = {
    "bambu-labs": ("test_bambu_lan_print.py",),
}


def contract_files(root: Path, names: list[str]) -> list[Path]:
    files = [root / "tests/python/global" / name for name in GLOBAL_CONTRACTS]
    for directory in sorted((root / "tests/python/skills").iterdir()):
        if not directory.is_dir() or names and directory.name not in names:
            continue
        for pattern in (*PATTERNS, *EXTRA_CONTRACTS.get(directory.name, ())):
            files.extend(directory.glob(pattern))
    return sorted(set(files))


def main() -> int:
    names = json.loads(os.environ.get("SKILL_DOC_NAMES", "[]"))
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("SKILL_DOC_NAMES must be a JSON array of skill names")
    files = contract_files(ROOT, names)
    # The common runner rejects empty modules; do not silently ignore missing policy files.
    if not files or any(not path.is_file() for path in files):
        raise RuntimeError("missing documentation contract tests")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "packages/cadgen/src"), env.get("PYTHONPATH", "")])
    return subprocess.call([
        sys.executable, str(ROOT / "scripts/test/unittest_files.py"), "--top", str(ROOT),
        "--jobs", os.environ.get("CADGEN_TEST_JOBS", "4"), "--print-weights",
        *map(str, files),
    ], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
