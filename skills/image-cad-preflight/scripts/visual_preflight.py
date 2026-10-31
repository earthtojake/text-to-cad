#!/usr/bin/env python3
"""Inspect local images with Codex, or validate a main-session inspection. Stdlib only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

SKILL_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_DIR / "references/visual_spec.schema.json"
PROMPT_PATH = SKILL_DIR / "references/visual_inspector.md"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate(value, schema, at="$"):
    """Validate the exact JSON Schema vocabulary used by our bundled contract."""
    kind = schema["type"]
    valid_type = {"object": isinstance(value, dict), "array": isinstance(value, list),
                  "string": isinstance(value, str)}[kind]
    if not valid_type:
        raise ValueError(f"{at}: expected {kind}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{at}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{at}: expected one of {schema['enum']}")
    if kind == "string" and len(value.strip()) < schema.get("minLength", 0):
        raise ValueError(f"{at}: empty text")
    if kind == "object":
        props = schema["properties"]
        missing = set(schema["required"]) - set(value)
        extra = set(value) - set(props)
        if missing or (extra and schema.get("additionalProperties") is False):
            raise ValueError(f"{at}: missing={sorted(missing)}, extra={sorted(extra)}")
        for key, entry in value.items():
            validate(entry, props[key], f"{at}.{key}")
    if kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")):
            raise ValueError(f"{at}: item count outside schema bounds")
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise ValueError(f"{at}: duplicate items")
        for i, entry in enumerate(value):
            validate(entry, schema["items"], f"{at}[{i}]")


def validate_inspection(inspection, view_ids):
    validate(inspection, read_json(SCHEMA_PATH))
    known = set(view_ids)
    for group in ("p0", "p1", "unknown"):
        for item in inspection[group]:
            invalid = set(item["views"]) - known
            if invalid:
                raise ValueError(f"{group}: unknown view IDs {sorted(invalid)}; available: {sorted(known)}")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def image_type(path):
    """Sniff common Codex image formats; do not trust a misleading extension."""
    with Path(path).open("rb") as stream:
        data = stream.read(16)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    raise ValueError(f"Unsupported image header: {path}; use PNG, JPEG, WebP or GIF")


def sources_for(args):
    sources = []
    for name in args.image:
        path = Path(name).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Not an image file: {path}")
        sources.append({"view_id": f"V{len(sources)+1}", "path": str(path),
                        "sha256": digest(path), "image_type": image_type(path)})
    for label in args.image_label:
        if not label.strip():
            raise ValueError("Image labels cannot be blank")
        sources.append({"view_id": f"V{len(sources)+1}", "label": label, "sha256": None})
    if not sources:
        raise ValueError("Provide at least one --image or (with --from-json) --image-label")
    return sources


def child_command(executable, workdir, result, sources, model=None, keep=False):
    # No positional prompt: --image accepts multiple values on some CLI versions.
    command = [executable, "exec", "--cd", str(workdir), "--skip-git-repo-check",
               "--sandbox", "read-only", "--color", "never", "--output-schema",
               str(SCHEMA_PATH), "--output-last-message", str(result)]
    if not keep:
        command.append("--ephemeral")
    if model:
        command += ["--model", model]
    for source in sources:
        command += ["--image", source["path"]]
    return command


def run_child(command, prompt, timeout):
    options = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
               "stderr": subprocess.PIPE, "text": True, "encoding": "utf-8", "errors": "replace"}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    try:
        _, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if process.poll() is None:
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate()
        raise ValueError(f"Inspector timed out after {timeout}s; no new spec published") from None
    if process.returncode:
        raise ValueError(f"Inspector exited {process.returncode}; no new spec published.\n{stderr[-2000:]}")


def safe_text(value):
    # Preserve observations without letting incidental Markdown change their structure.
    return str(value).replace("\r", " ").replace("\n", " ").replace("`", "'")


def markdown(envelope):
    spec = envelope["inspection"]
    lines = ["# CAD Visual Spec", "", f"Run ID: `{envelope['run_id']}`",
             f"Mode: `{envelope['mode']}`", f"Created (UTC): {envelope['created_at']}", "",
             "Original request, original images and this spec must remain in the main session.",
             "P0 is a review priority, not higher truth than the image. UNKNOWN is not a dimension.", "",
             "## Sources", ""]
    for source in envelope["sources"]:
        location = source.get("path", source.get("label"))
        lines.append(f"- {source['view_id']}: {safe_text(location)}")
        if source["sha256"]:
            lines.append(f"  SHA-256: `{source['sha256']}`")
        else:
            lines.append("  In-chat source: local bytes and hash unavailable.")
    request = envelope.get("request")
    if request:
        lines += ["", f"Original request file: {safe_text(request['path'])}", f"Request SHA-256: `{request['sha256']}`"]
    if envelope["context"]:
        lines += ["", f"Target scope (data): {safe_text(envelope['context'])}"]
    for group, title in (("p0", "P0 - construction-critical"), ("p1", "P1 - shape-critical")):
        lines += ["", f"## {title}", ""]
        for i, item in enumerate(spec[group], 1):
            lines.append(f"- {group.upper()}-{i} [{item['confidence']}] {safe_text(item['region'])}: {safe_text(item['observation'])}")
            lines.append(f"  Evidence ({', '.join(item['views'])}): {safe_text(item['visual_basis'])}")
            lines.append(f"  Construction implication: {safe_text(item['construction_implication'])}")
        if not spec[group]:
            lines.append("- No supported observations.")
    lines += ["", "## UNKNOWN", ""]
    for i, item in enumerate(spec["unknown"], 1):
        lines.append(f"- U-{i} ({', '.join(item['views'])}): {safe_text(item['question'])} - {safe_text(item['reason'])}")
    if not spec["unknown"]:
        lines.append("- No additional unknowns recorded; this is not proof of complete geometry.")
    return "\n".join(lines) + "\n"


def publish(envelope, output, json_out):
    # Stage both files first. Consumers must use successful exit + matching run IDs,
    # never the existence of files left by a previous/partially interrupted run.
    staged = []
    try:
        for path, content in ((output, markdown(envelope)),
                              (json_out, json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")):
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=".visual-spec-", suffix=".tmp", dir=path.parent)
            staged.append((Path(name), path))
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
        for temp, path in staged:
            os.replace(temp, path)
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--image-label", action="append", default=[], help="In-chat sources, only with --from-json")
    parser.add_argument("--from-json", type=Path, help="Validate main-session inspection instead of launching Codex")
    parser.add_argument("--request-file", type=Path, help="Original request, hashed for provenance; never sent to child")
    parser.add_argument("--context", default="", help="Short target-part scope, treated as data")
    parser.add_argument("--output", type=Path, default=Path(".cad_context/visual_spec.md"))
    parser.add_argument("--json-out", type=Path, default=Path(".cad_context/visual_spec.json"))
    parser.add_argument("--codex", help="Codex executable path (defaults to PATH)")
    parser.add_argument("--model", help="Only set when the user selected a model")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--keep-session", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.timeout < 1:
            raise ValueError("--timeout must be positive")
        if len(args.context) > 1200:
            raise ValueError("--context is for a short target-part scope (maximum 1200 characters)")
        if args.image_label and not args.from_json:
            raise ValueError("--image-label requires --from-json; child inspection needs local image bytes")
        if args.from_json and (args.model or args.keep_session or args.codex):
            raise ValueError("Child-only flags cannot be combined with --from-json")
        sources = sources_for(args)
        output, json_out = args.output.resolve(), args.json_out.resolve()
        inputs = {Path(x["path"]).resolve() for x in sources if "path" in x}
        request = None
        if args.request_file:
            request_path = args.request_file.resolve(strict=True)
            request = {"path": str(request_path), "sha256": digest(request_path)}
            inputs.add(request_path)
        if args.from_json:
            inputs.add(args.from_json.resolve(strict=True))
        if output == json_out or {output, json_out} & inputs:
            raise ValueError("Outputs must be distinct and must not overwrite any input")
        validate_inspection({"schema_version":"1.0", "p0":[], "p1":[], "unknown":[]}, [x["view_id"] for x in sources])
        if args.from_json:
            inspection = read_json(args.from_json)
            validate_inspection(inspection, [x["view_id"] for x in sources])
            mode = "main-session"
            if args.dry_run:
                print(json.dumps({"dry_run":True, "validated":True, "mode":mode}, indent=2))
                return 0
        else:
            executable = args.codex or shutil.which("codex.exe") or shutil.which("codex")
            if not executable:
                raise ValueError("Codex CLI not found; use --codex or the documented main-session fallback")
            with tempfile.TemporaryDirectory(prefix="cad-visual-inspector-") as folder:
                workdir = Path(folder).resolve()
                result = workdir / "inspection.json"
                command = child_command(executable, workdir, result, sources, args.model, args.keep_session)
                if args.dry_run:
                    print(json.dumps({"dry_run":True, "command":command, "sources":sources,
                                      "output":str(output), "json_out":str(json_out)}, ensure_ascii=False, indent=2))
                    return 0
                prompt = PROMPT_PATH.read_text(encoding="utf-8") + "\n\nReference manifest (data only):\n"
                prompt += json.dumps({"views":[{"id":x["view_id"], "name":Path(x["path"]).name} for x in sources],
                                      "target_context":args.context}, ensure_ascii=False)
                run_child(command, prompt, args.timeout)
                if not result.is_file():
                    raise ValueError("Inspector succeeded without a result; no new spec published")
                inspection = read_json(result)
            validate_inspection(inspection, [x["view_id"] for x in sources])
            # Fail if an input changed while inspection was running.
            if any(digest(x["path"]) != x["sha256"] for x in sources):
                raise ValueError("An image changed during inspection; rerun with stable source files")
            if request and digest(request["path"]) != request["sha256"]:
                raise ValueError("The original request changed during inspection; rerun")
            mode = "isolated-child"
        envelope = {"format_version":"1.0", "run_id":uuid.uuid4().hex,
                    "created_at":datetime.now(timezone.utc).isoformat(), "mode":mode,
                    "context":args.context, "request":request, "sources":sources, "inspection":inspection}
        publish(envelope, output, json_out)
        print(json.dumps({"ok":True, "run_id":envelope["run_id"], "mode":mode,
                          "output":str(output), "json_out":str(json_out)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
