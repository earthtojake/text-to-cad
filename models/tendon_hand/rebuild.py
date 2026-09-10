#!/usr/bin/env python3
"""Import, verify, list, and execute the Tendon Hand asset rebuild."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
MANIFEST_PATH = ROOT / "rebuild_manifest.json"
RECEIPT_PATH = ROOT / "validation/checkpoint_import_receipt.json"
LEGACY_PART = "anthropomorphic_hand"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def source_path(assemblies: Path, relative: str) -> Path:
    section, tail = relative.split("/", 1)
    return assemblies / section / LEGACY_PART / tail


def relocate_string(value: str) -> str:
    normalized = value.replace("\\", "/")
    mappings = (
        ("models/assemblies/STEP/anthropomorphic_hand/", ROOT / "STEP"),
        ("models/assemblies/validation/anthropomorphic_hand/", ROOT / "validation"),
        ("models/assemblies/src/anthropomorphic_hand/", ROOT / "src"),
        ("models/tendon_hand/STEP/", ROOT / "STEP"),
        ("models/tendon_hand/validation/", ROOT / "validation"),
        ("models/tendon_hand/src/", ROOT / "src"),
    )
    for marker, destination in mappings:
        if marker in normalized:
            return str(destination / normalized.split(marker, 1)[1])
    return value


def relocate_json(value):
    if isinstance(value, dict):
        return {relocate_string(str(key)): relocate_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [relocate_json(item) for item in value]
    if isinstance(value, str):
        return relocate_string(value)
    return value


def import_checkpoint(assemblies: Path) -> None:
    assemblies = assemblies.expanduser().resolve()
    rows = manifest()["checkpoint"]["files"]
    receipt = {"manifest_sha256": sha256(MANIFEST_PATH), "source": str(assemblies), "files": {}}
    for row in rows:
        relative = row["path"]
        source = source_path(assemblies, relative)
        if not source.is_file():
            raise FileNotFoundError(f"missing checkpoint input: {source}")
        actual = sha256(source)
        if source.stat().st_size != row["bytes"] or actual != row["sha256"]:
            raise ValueError(f"checkpoint digest mismatch: {source}")
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".json":
            data = relocate_json(json.loads(source.read_text()))
            destination.write_text(json.dumps(data, indent=2) + "\n")
        else:
            shutil.copyfile(source, destination)
        receipt["files"][relative] = {
            "source_sha256": actual,
            "installed_sha256": sha256(destination),
        }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Imported and verified {len(rows)} checkpoint files ({sum(r['bytes'] for r in rows)} bytes).")


def check_checkpoint() -> None:
    rows = manifest()["checkpoint"]["files"]
    if not RECEIPT_PATH.is_file():
        raise FileNotFoundError(
            f"missing {RECEIPT_PATH}; run import-checkpoint before an exact R13 rebuild"
        )
    receipt = json.loads(RECEIPT_PATH.read_text())
    if receipt["manifest_sha256"] != sha256(MANIFEST_PATH):
        raise ValueError("checkpoint receipt belongs to a different rebuild manifest")
    for row in rows:
        relative = row["path"]
        path = ROOT / relative
        recorded = receipt["files"].get(relative, {})
        if not path.is_file():
            raise FileNotFoundError(f"missing installed checkpoint file: {path}")
        if recorded.get("source_sha256") != row["sha256"]:
            raise ValueError(f"wrong checkpoint source digest in receipt: {relative}")
        if sha256(path) != recorded.get("installed_sha256"):
            raise ValueError(f"installed checkpoint file changed: {relative}")
        if path.suffix == ".json":
            json.loads(path.read_text())
    certificate = json.loads((ROOT / "validation/integration_native_base_certificate.json").read_text())
    if certificate["step_sha256"] != sha256(ROOT / "STEP/imported/integration_native_base.step"):
        raise ValueError("native-base STEP does not match its certificate")
    if certificate["metadata_sha256"] != sha256(ROOT / "validation/integration_native_base_frames.json"):
        raise ValueError("native-base frames do not match their certificate")
    print(f"Checkpoint preflight passed for {len(rows)} files.")


def cadgen() -> str:
    executable = Path(sys.executable).with_name("cadgen")
    return str(executable if executable.exists() else "cadgen")


def commands(include_video: bool = False) -> list[tuple[str, list[str]]]:
    python = sys.executable
    step_file = ROOT / "STEP/hand_mechanical_candidate_r13.step"
    result = [
        ("Build R13 once to write the body-frame manifest", [python, str(ROOT / "src/hand_mechanical_candidate_r13.py")]),
        ("Regenerate the indexed capstan overlay from those frames", [python, str(ROOT / "src/capstan_index_overlay.py")]),
        ("Rebuild final R13 with the regenerated overlay", [python, str(ROOT / "src/hand_mechanical_candidate_r13.py")]),
        ("Validate every final STEP placement", [cadgen(), "step", "inspect", "validate", str(step_file), "--every-placement"]),
        ("Generate the ignored animation render module", [python, str(ROOT / "validation/write_showcase_presentation.py")]),
    ]
    animation = lambda clip: json.dumps(
        {"clip": clip, "fps": 30, "deform": "morph", "deformTolerance": 1.0, "drop": ["visible"]},
        separators=(",", ":"),
    )
    for clip in ("fist", "wave", "pinch", "signs", "drive"):
        result.append((f"Export website clip {clip}", [cadgen(), "glb", "build", str(step_file), str(ROOT / f"website/hand_{clip}.glb"), "--animation", animation(clip)]))
    if include_video:
        result.append(("Render the optional showcase video (requires ffmpeg)", [cadgen(), "step", "snapshot", str(step_file), str(ROOT / "tmp/showcase.mp4"), "--animation", "showcase", "--video", '{"fps":30,"quality":"review"}']))
    result.append(("Test the authored HTML presentation", ["node", "--test", str(ROOT / "website/preview.behavior.test.mjs")]))
    return result


def print_plan(include_video: bool) -> None:
    print("0. Import and verify the archival checkpoint (see README).")
    for index, (description, command) in enumerate(commands(include_video), 1):
        print(f"{index}. {description}\n   {shlex.join(command)}")


def run(include_video: bool) -> None:
    check_checkpoint()
    for description, command in commands(include_video):
        print(f"\n==> {description}", flush=True)
        subprocess.run(command, cwd=REPO, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("plan", help="print the dependency-ordered commands without executing them").add_argument("--video", action="store_true")
    importer = subparsers.add_parser("import-checkpoint", help="copy and verify the ignored legacy checkpoint")
    importer.add_argument("--from", dest="assemblies", required=True, type=Path, help="legacy models/assemblies directory")
    subparsers.add_parser("check", help="verify imported checkpoint files without loading CAD")
    runner = subparsers.add_parser("run", help="execute the full final-asset rebuild")
    runner.add_argument("--video", action="store_true", help="also render tmp/showcase.mp4; requires ffmpeg")
    args = parser.parse_args()
    if args.action == "plan":
        print_plan(args.video)
    elif args.action == "import-checkpoint":
        import_checkpoint(args.assemblies)
    elif args.action == "check":
        check_checkpoint()
    elif args.action == "run":
        run(args.video)


if __name__ == "__main__":
    main()
