"""Equivalence oracle for the production-architecture migration.

Every workstream in design/production-architecture.md is judged by this
module: it builds an entry under a controlled environment (fresh process,
explicit cache/session configuration) and reduces the result to a
FINGERPRINT — the content that must be identical across cache states and
across the batch/session paths. Fingerprints are an ALLOWLIST, never a
blocklist: they contain only fields whose equality we assert (component
cids and bytes, occurrence identity/placement, mates, bounds), so
provenance fields can change freely without touching the oracle.

The oracle never compares a nondeterministic subtree against a fresh
uncached rebuild of itself (OCCT parallel booleans are not byte-stable);
it compares SYSTEM OUTPUTS to each other across cache states, which is the
determinism contract the design docs establish.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# The interpreter running the suite, NOT a hardcoded checkout path: the oracle
# spawns children that must import the same cadgen/OCP the parent did, and a
# literal ``.venv/bin/python`` exists on exactly one machine (it named an
# absolute macOS path and raised FileNotFoundError on every CI runner).
VENV_PYTHON = sys.executable
REPO_ROOT = Path(__file__).resolve().parents[3]
CADGEN_SRC = REPO_ROOT / "packages" / "cadgen" / "src"


def build_entry(
    entry_path: Path,
    *,
    env: dict[str, str] | None = None,
    force: bool = False,
    timeout: float = 900.0,
) -> subprocess.CompletedProcess:
    """Build one entry in a FRESH process from its own directory.

    ``env`` overrides are applied on top of a hermetic base: warm daemon off,
    serial component workers (deterministic measurement), caches ON unless
    the caller says otherwise. Callers isolate CADGEN_CACHE_DIR themselves —
    the oracle never touches the user-level store.
    """
    entry_path = Path(entry_path).resolve()
    merged = dict(os.environ)
    merged.update({
        "CADGEN_DAEMON": "0",
        "CADGEN_COMPONENT_WORKERS": "1",
        "PYTHONPATH": str(CADGEN_SRC),
    })
    merged.update(env or {})
    # Library-first: a model script IS the entrypoint; running it builds it.
    return subprocess.run(
        [VENV_PYTHON, entry_path.name, *(["--force"] if force else [])],
        cwd=str(entry_path.parent),
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def artifact_path(entry_path: Path) -> Path:
    """The .step a model entry writes — its declared ``out=``, else the sibling.

    A cad-project routes its artifacts into a format folder
    (``@step(out="../STEP/x.step")``), so assuming the sibling default silently
    resolves a package that was never built. Read the declaration statically:
    importing the module would drag in the CAD kernel.
    """
    entry_path = Path(entry_path).resolve()
    if not entry_path.name.endswith(".py"):
        return entry_path
    declared = None
    for node in ast.parse(entry_path.read_text()).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if getattr(decorator.func, "id", None) != "step":
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "out" and isinstance(keyword.value, ast.Constant):
                    declared = str(keyword.value.value)
    if declared:
        return (entry_path.parent / declared).resolve()
    return entry_path.with_name(entry_path.name[: -len(".py")] + ".step")


def package_dir(entry_path: Path) -> Path:
    # The package resolves from the STORE by the ARTIFACT's content hash
    # (cadgen.catalog.render_package_dir), wherever out= routed it.
    from cadgen.catalog import render_package_dir

    return render_package_dir(artifact_path(entry_path))


def fingerprint(entry_path: Path) -> dict:
    """The allowlisted identity of a built package."""
    pkg = package_dir(entry_path)
    descriptor = json.loads((pkg / "assembly.json").read_text())

    occurrences = {}
    for occ in descriptor.get("occurrences") or []:
        name = str(occ.get("name") or occ.get("id") or "")
        occurrences[name] = {
            "component": occ.get("component") or occ.get("cid"),
            "transform": [round(float(v), 6) for v in (occ.get("transform") or [])],
        }

    components = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for pattern in ("*.surf", "*.brep")
        for path in sorted((pkg / "components").glob(pattern))
    }

    # Kinematics are source-derived, so they ride the MODEL-SIDE sidecar
    # (<name>.step gets <name>.step.json beside it); an imported model has no
    # sidecar and therefore no kinematics.
    artifact = artifact_path(entry_path)
    sidecar_path = artifact.with_name(f"{artifact.name}.json")
    kinematics = None
    if sidecar_path.is_file():
        sidecar = json.loads(sidecar_path.read_text())
        kinematics = sidecar.get("kinematics")

    return {
        "cids": sorted((descriptor.get("components") or {}).keys()),
        "occurrences": occurrences,
        "componentBytes": components,
        "kinematics": kinematics,
        "bbox": descriptor.get("bbox"),
    }


def diff_fingerprints(a: dict, b: dict) -> list[str]:
    """Human-readable differences; empty list means equivalent."""
    problems: list[str] = []
    if a["cids"] != b["cids"]:
        only_a = sorted(set(a["cids"]) - set(b["cids"]))
        only_b = sorted(set(b["cids"]) - set(a["cids"]))
        problems.append(f"cids differ: only-a={only_a[:4]} only-b={only_b[:4]}")
    if set(a["occurrences"]) != set(b["occurrences"]):
        problems.append(
            "occurrence names differ: "
            f"{sorted(set(a['occurrences']) ^ set(b['occurrences']))[:6]}"
        )
    else:
        for name, occ in a["occurrences"].items():
            if b["occurrences"][name] != occ:
                problems.append(f"occurrence {name!r} differs")
    changed = [
        name for name in set(a["componentBytes"]) & set(b["componentBytes"])
        if a["componentBytes"][name] != b["componentBytes"][name]
    ]
    if changed:
        problems.append(f"component bytes differ: {changed[:6]}")
    missing = set(a["componentBytes"]) ^ set(b["componentBytes"])
    if missing:
        problems.append(f"component files differ: {sorted(missing)[:6]}")
    if a["kinematics"] != b["kinematics"]:
        problems.append("kinematics differ")
    if a["bbox"] != b["bbox"]:
        problems.append("bbox differs")
    return problems


def inspect_fingerprint(entry_path: Path, refs: list[str],
                        env: dict[str, str] | None = None) -> dict:
    """CLI-surface identity: resolved selections for the given refs, with
    volatile fields stripped."""
    entry_path = Path(entry_path).resolve()
    merged = dict(os.environ)
    merged.update({"CADGEN_DAEMON": "0", "PYTHONPATH": str(CADGEN_SRC)})
    merged.update(env or {})
    code = (
        "from cadgen.cli.step_inspect.cli import main\n"
        f"main(['refs', {entry_path.name!r}] + {refs!r} + ['--facts'])\n"
    )
    proc = subprocess.run(
        [VENV_PYTHON, "-c", code],
        cwd=str(entry_path.parent), env=merged,
        capture_output=True, text=True, timeout=600,
    )
    line = next((l for l in proc.stdout.splitlines() if l.strip().startswith("{")), "{}")
    payload = json.loads(line)
    tokens = []
    for token in payload.get("tokens") or []:
        tokens.append({
            "token": token.get("token"),
            "summary": token.get("summary"),
            "selections": token.get("selections"),
            "entryFacts": token.get("entryFacts"),
        })
    return {"ok": payload.get("ok"), "tokens": tokens,
            "errors": payload.get("errors")}
