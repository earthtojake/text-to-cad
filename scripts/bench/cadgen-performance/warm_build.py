#!/usr/bin/env python3
"""Unprofiled in-process edit timings, with normal stage logs and preview events.

Run with the checkout's cadgen on PYTHONPATH and exact source substitutions
for a disposable model copy.
The source is restored in finally, including when a build fails.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from unittest import mock

from common import metadata, model_path, peak_rss_bytes, sha256, source_fingerprint, write_json


def summary(values):
    return {"count": len(values), "minMs": min(values), "medianMs": statistics.median(values), "maxMs": max(values)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--store", required=True, help="Dedicated benchmark store under models/; never deleted")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--geometry-model", help="Source containing the geometry substitution; defaults to --model")
    parser.add_argument("--placement-model", help="Source containing the placement substitution; defaults to --model")
    parser.add_argument("--child-daemon-socket", help="Use a caller-owned dedicated warm daemon for child builds; default uses transient workers")
    parser.add_argument("--skip-imports", action="store_true", help="Measure builds only, omitting the separate import study")
    parser.add_argument("--assert-child-pins", action="store_true", help="Require geometry to change only its child pin and placement to preserve all pins")
    parser.add_argument("--geometry-from", required=True)
    parser.add_argument("--geometry-to", required=True)
    parser.add_argument("--placement-from", required=True)
    parser.add_argument("--placement-to", required=True)
    parser.add_argument("--novel-geometry-to", action="append", default=[],
                        help="Additional replacement measured once, without priming; repeat for distinct edits")
    parser.add_argument("--novel-placement-to", action="append", default=[],
                        help="Additional placement replacement measured once, without priming")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    model, store = model_path(args.model), model_path(args.store)
    geometry_model = model_path(args.geometry_model or model)
    placement_model = model_path(args.placement_model or model)
    if args.assert_child_pins and geometry_model == model:
        parser.error("--assert-child-pins requires --geometry-model naming a child source")
    originals = {path: (path.read_bytes(), path.stat()) for path in (model, geometry_model, placement_model)}
    original = originals[model][0]
    variants = {name: {path: saved[0] for path, saved in originals.items()}
                for name in ("baseline", "geometry", "placement")}
    variant_kinds = {name: name for name in variants}
    novel_variants = []
    for variant, path, old, new in (("geometry", geometry_model, args.geometry_from, args.geometry_to),
                                    ("placement", placement_model, args.placement_from, args.placement_to)):
        baseline = originals[path][0].decode("utf-8")
        if baseline.count(old) != 1 or old == new:
            parser.error(f"Substitution must match exactly once and change the source: {old!r}")
        variants[variant][path] = baseline.replace(old, new).encode("utf-8")
    for kind, path, old, primed, replacements in (
        ("geometry", geometry_model, args.geometry_from, args.geometry_to, args.novel_geometry_to),
        ("placement", placement_model, args.placement_from, args.placement_to, args.novel_placement_to),
    ):
        seen = {old, primed}
        for index, replacement in enumerate(replacements, start=1):
            if replacement in seen:
                parser.error(f"Novel {kind} replacements must be distinct from baseline and primed edits")
            seen.add(replacement)
            name = f"novel-{kind}-{index}"
            variants[name] = {source: saved[0] for source, saved in originals.items()}
            variants[name][path] = originals[path][0].decode("utf-8").replace(old, replacement).encode("utf-8")
            variant_kinds[name] = kind
            novel_variants.append(name)
    store.mkdir(parents=True, exist_ok=True)
    os.environ.update(CADGEN_CACHE_DIR=str(store), CADGEN_DAEMON="0", CADGEN_EVENTS="1", PYTHONDONTWRITEBYTECODE="1")
    if args.child_daemon_socket:
        os.environ.update(CADGEN_DAEMON="1", CADGEN_DAEMON_SOCKET=str(Path(args.child_daemon_socket).expanduser().resolve()))
    from cadgen.cli._run_model import run_model_argv
    from cadgen.daemon import executors
    from cadgen._internal import op_memo
    from cadgen.store.records import read_record
    from cadgen.store.trees import flatten
    from cadgen.step_scene import read_step
    import build123d  # noqa: F401 - exclude kernel startup from timed runs

    report = {"metadata": metadata(), "model": str(model), "sourceSha256": sha256(original),
              "sourceFiles": {str(path): sha256(saved[0]) for path, saved in originals.items()},
              "geometryModel": str(geometry_model), "placementModel": str(placement_model),
              "childWorkers": "dedicated warm daemon" if args.child_daemon_socket else "transient",
              "store": str(store), "timingBoundary": "same interpreter, kernel imported; excludes startup, source writes and daemon IPC; no profiler",
              "substitutions": {"geometry": [args.geometry_from, args.geometry_to],
                                "placement": [args.placement_from, args.placement_to],
                                "novelGeometry": args.novel_geometry_to,
                                "novelPlacement": args.novel_placement_to}, "runs": []}
    logs = args.report.resolve().with_suffix("").with_name(args.report.stem + "-logs")
    logs.mkdir(parents=True, exist_ok=True)
    if args.child_daemon_socket:
        report["timingBoundary"] = "same root interpreter, kernel imported; child daemon IPC and declared output completion included; workers primed before measured calls; no profiler"
    initial_child_pins = None
    seen_document_hashes = set()

    def run(label: str, variant: str, *, measured: bool):
        nonlocal initial_child_pins
        variant_kind = variant_kinds[variant]
        for path, payload in variants[variant].items():
            path.write_bytes(payload)
        events = []
        before_ops = op_memo.stats()
        started = time.perf_counter()

        def event_sink(event):
            events.append({"elapsedMs": (time.perf_counter() - started) * 1000, **event})

        executors.set_event_sink(event_sink)
        log_path = logs / f"{len(report['runs']):02d}-{label}.log"
        with log_path.open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            code = run_model_argv([str(model), "--verbose"])
        elapsed = (time.perf_counter() - started) * 1000
        after_ops = op_memo.stats()
        record = read_record(model) or {}
        tree = flatten(record["tree"]) if record.get("tree") else {}
        stage_pattern = r"^\[cadgen\] (.+?) completed in ([0-9.]+)(ms|s)$"
        stages = [{"label": match[0], "milliseconds": float(match[1]) * (1000 if match[2] == "s" else 1)}
                  for match in re.findall(stage_pattern, log_path.read_text(), flags=re.MULTILINE)]
        root_events = [event for event in events if str(event.get("model", "")).split("::")[0] == str(model)]
        previews = [event for event in root_events if event.get("preview")]
        saves = [event for event in root_events if event.get("saved")]
        source_results = [event for event in root_events if event.get("sourceResult")]
        children = []
        for pin in record.get("children") or []:
            child = read_record(pin["model"]) or {}
            children.append({"model": pin["model"], "pinnedTree": pin.get("tree"), "currentTree": child.get("tree"),
                             "documentTree": child.get("documentTree"), "documentHash": child.get("stepHash"),
                             "outputs": child.get("outputs"), "closure": child.get("closure"),
                             "actualOutputSha256": {path: sha256(Path(path).read_bytes())
                                                    for path in child.get("outputs") or {}}})
        if "inputClosureFiles" not in report:
            closure_files = {str(path) for path in originals}
            for item in [record, *children]:
                owner = Path(str(item.get("model") or model).split("::")[0]).parent
                closure_files.update(str((owner / path).resolve())
                                     for path in (item.get("closure") or {}).get("files") or [])
            report["inputClosureFiles"] = {path: sha256(Path(path).read_bytes()) for path in sorted(closure_files)
                                           if Path(path).is_file()}
        milestones = {}
        for event in events:
            target = str(event.get("model", ""))
            timing = milestones.setdefault(target, {})
            for flag, field in (("sourceResult", "sourceReadyMs"), ("preview", "previewMs"), ("saved", "savedMs")):
                if event.get(flag):
                    timing.setdefault(field, event["elapsedMs"])
            if event.get("state") in {"done", "current", "failed"}:
                timing["terminalMs"] = event["elapsedMs"]
                timing["terminalState"] = event["state"]
        current_pins = {child["model"]: child["pinnedTree"] for child in children}
        if initial_child_pins is None:
            initial_child_pins = current_pins
        changed_pins = sorted(key for key in current_pins.keys() | initial_child_pins.keys()
                              if current_pins.get(key) != initial_child_pins.get(key))
        expected_changes = sorted(key for key in initial_child_pins
                                  if variant_kind == "geometry" and key.split("::")[0] == str(geometry_model))
        pin_check = (bool(initial_child_pins) and changed_pins == expected_changes
                     and all(child["currentTree"] == child["pinnedTree"] for child in children))
        actual_outputs = {path: sha256(Path(path).read_bytes()) for path in record.get("outputs") or {}}
        actual_steps = [digest for path, digest in actual_outputs.items() if Path(path).suffix.lower() in {".step", ".stp"}]
        document_hash = actual_steps[0] if len(actual_steps) == 1 else None
        if not code and (document_hash is None or document_hash != record.get("stepHash")):
            raise AssertionError(f"{label} must write one STEP whose actual bytes match its recorded digest")
        first_output_digest = bool(document_hash) and document_hash not in seen_document_hashes
        seen_document_hashes.add(document_hash)
        row = {"run": label, "variant": variant, "variantKind": variant_kind,
               "novelEdit": variant in novel_variants, "firstOutputDigestInStudy": first_output_digest,
               "measured": measured, "milliseconds": elapsed, "exit": code,
               "ops": {key: value - before_ops.get(key, 0) for key, value in after_ops.items()},
               "events": events, "stages": stages, "tree": record.get("tree"), "documentHash": record.get("stepHash"),
               "actualOutputSha256": actual_outputs,
               "documentTree": record.get("documentTree"), "children": children,
               "modelMilestones": milestones, "changedChildPins": changed_pins,
               "childPinCheckPassed": pin_check if args.assert_child_pins else None,
               "components": sorted((tree.get("components") or {}).keys()), "occurrences": len(tree.get("occurrences") or []),
               "firstPreviewMs": previews[0]["elapsedMs"] if previews else None,
               "sourceResultMs": source_results[0]["elapsedMs"] if source_results else None,
               "savedMs": saves[-1]["elapsedMs"] if saves else None,
               "processPeakRssBytes": peak_rss_bytes()}
        report["runs"].append(row)
        write_json(args.report, report)
        print(json.dumps({key: row[key] for key in ("run", "milliseconds", "exit", "firstPreviewMs", "savedMs")}), flush=True)
        if code:
            raise RuntimeError(f"{label} failed; see {log_path}")
        if args.assert_child_pins and (not pin_check or (variant_kind == "geometry" and len(expected_changes) != 1)):
            raise AssertionError(f"{label} changed unexpected child pins: {changed_pins}, expected {expected_changes}")
        if variant in novel_variants and not first_output_digest:
            raise AssertionError(f"{label} did not produce a previously unseen STEP digest in this study")
        return record

    try:
        for variant in ("baseline", "geometry", "baseline", "placement", "baseline"):
            run(f"prime-{variant}", variant, measured=False)
        for iteration in range(args.iterations):
            for name, variant in (("unchanged", "baseline"), ("geometry", "geometry"),
                                  ("restore-geometry", "baseline"), ("placement", "placement"), ("restore-placement", "baseline")):
                record = run(f"{name}-{iteration + 1}", variant, measured=not name.startswith("restore"))
        report["summary"] = {
            label: summary([row["milliseconds"] for row in report["runs"] if row["measured"] and row["run"].startswith(label + "-")])
            for label in ("unchanged", "geometry", "placement")}
        for variant in novel_variants:
            run(variant, variant, measured=True)
            record = run(f"restore-{variant}", "baseline", measured=False)
        report["novelSummary"] = {
            kind: summary([row["milliseconds"] for row in report["runs"]
                           if row["novelEdit"] and row["variantKind"] == kind])
            for kind in ("geometry", "placement")
            if any(row["novelEdit"] and row["variantKind"] == kind for row in report["runs"])
        }
        if args.skip_imports:
            report["imports"] = {"skipped": True}
            return 0
        steps = [Path(path) for path in record.get("outputs", {}) if Path(path).suffix.lower() in {".step", ".stp"}]
        if len(steps) != 1:
            raise RuntimeError("Benchmark expects exactly one STEP output")
        step = steps[0]
        imports = []
        # A separate empty import cache proves publication of a first read.
        # Its compile subprocess startup is included and labelled explicitly.
        with tempfile.TemporaryDirectory(prefix="import-benchmark-", dir=store.parent) as scratch:
            scratch_path = Path(scratch)
            imported = scratch_path / "input.step"
            shutil.copyfile(step, imported)
            os.environ["CADGEN_CACHE_DIR"] = str(scratch_path / "store")
            for index in range(args.iterations + 1):
                started = time.perf_counter()
                guard = mock.patch.object(executors, "submit_compile", side_effect=AssertionError("cached import requested a compile")) if index else contextlib.nullcontext()
                with guard:
                    shape = read_step(imported)
                imports.append({"cache": "cold" if index == 0 else "warm", "milliseconds": (time.perf_counter() - started) * 1000,
                                "volume": shape.volume, "compileForbidden": bool(index)})
                del shape
            report["imports"] = {"inputSha256": sha256(imported.read_bytes()), "inputBytes": imported.stat().st_size,
                                 "coldIncludesCompileProcessStartup": True, "runs": imports}
        report["imports"]["warmSummary"] = summary([row["milliseconds"] for row in imports if row["cache"] == "warm"])
        return 0
    finally:
        for path, (payload, original_stat) in originals.items():
            path.write_bytes(payload)
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        os.environ["CADGEN_CACHE_DIR"] = str(store)
        executors.set_event_sink(None)
        report["sourceRestored"] = all(path.read_bytes() == saved[0] for path, saved in originals.items())
        report["inputClosureUnchangedAfterRestoration"] = all(
            Path(path).is_file() and sha256(Path(path).read_bytes()) == digest
            for path, digest in report.get("inputClosureFiles", {}).items())
        report["runtimeUnchangedDuringStudy"] = source_fingerprint() == report["metadata"]["sourceFingerprint"]
        write_json(args.report, report)


if __name__ == "__main__":
    raise SystemExit(main())
