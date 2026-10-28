"""Agent operations independent of a viewer, using the public Python verbs.

A session owns bounded, in-memory status. Repeating a request ID joins its work;
status/cancel go through the same tool. Destinations belong to the engine host.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from pathlib import Path

from cadgen.jobs import TERMINAL, Jobs, JobError


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


STRING = {"type": "string", "minLength": 1}
BOOL = {"type": "boolean"}
JSON_VALUE = {"type": ["object", "array", "string"]}
COMMON = {
    "action": {"type": "string", "enum": ["start", "status", "cancel"], "default": "start"},
    "requestId": {**STRING, "description": "Unique 16–100 character request ID. Reuse only for an identical start in this session."},
    "operationId": STRING,
    "epoch": {**STRING, "description": "Session epoch returned by start; required for status/cancel."},
    "afterSequence": {"type": "integer", "minimum": 0},
    "waitMs": {"type": "integer", "minimum": 0, "maximum": 25000,
               "description": "Milliseconds to wait before answering: for the operation to finish, or with afterSequence for its next change."},
}
# What follows an operation: status or cancel, by the id and epoch its start returned.
FOLLOW = ("action", "operationId", "epoch", "afterSequence", "waitMs")
FOLLOW_REQUIRED = ("action", "operationId", "epoch")
SNAPSHOT = {"source": STRING,
            "output": {**STRING, "description": "The PNG's absolute path; required with source unless a packet names the outputs."},
            "packet": {**JSON_VALUE, "description": "A Quick Edit packet (its absolute path or object), which declares its outputs: "
                                                    "give it in place of output; a source with it replaces its input."},
            "display": JSON_VALUE, "camera": JSON_VALUE, "grid": BOOL,
            "pose": {"type": ["object", "string"]}, "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1}, "size_profile": STRING,
            "annotation": JSON_VALUE, "measurements": JSON_VALUE}
START = {
    "cad_export": obj({"source": STRING, "destinations": {"type": "array", "minItems": 1, "maxItems": 32, "items": STRING}},
                      ("source", "destinations")),
    "cad_snapshot": obj(SNAPSHOT),
    "cad_inspect": obj({"source": STRING, "ref": STRING,
                        "query": {"type": "string", "enum": ["summary", "structure", "closure", "geometry", "build"]}},
                       ("source",)),
}
# The arguments each start requires, beside requestId: one set, or (a snapshot) one of several.
STARTS = {"cad_export": (("source", "destinations"),), "cad_snapshot": (("source", "output"), ("packet",)),
          "cad_inspect": (("source",),)}
DESCRIPTIONS = {
    "cad_export": "Export a document to explicit absolute destinations on the engine host (.xbf/.step/.glb/.stl/.3mf/.dxf). The source is an absolute CAD file path or a document id (a model's, which running its script prints); a document id is exported as the engine holds it. A mesh source (.glb/.stl/.3mf) exports to the other two mesh kinds only, each holding what its format carries. Reuses the Python export operation. Viewer downloads instead choose a destination in the user's browser and use temporary artifacts.",
    "cad_snapshot": "Render an explicit source/output PNG or a Quick Edit packet, using the Python snapshot operation. The source is an absolute CAD file path or a document id; paths must be absolute on the engine host. A failed snapshot or packet leaves existing pictures unchanged.",
    "cad_inspect": "Inspect an existing CAD file (.xbf, .step, a mesh) or a document id. Without a ref it answers what `cadgen inspect SOURCE` prints: the summary (parts, bounds, volume, materials and mass, joints, states, sequences, animations) as data and as its text, with the build closure where there is one. With a ref (or SOURCE#REF), that element's or part's geometry. query picks one answer instead: summary, structure (the summary's lists without bounds, volume or mass, so nothing is measured), closure, geometry (requires ref) or build (file metadata or live build metadata). Never builds a model, meshes a part or writes its declared outputs; a document the engine no longer holds is refused with the command that builds it again.",
}


def catalog():
    return [{"name": name, "title": name.removeprefix("cad_").capitalize() + " CAD",
             "description": description + " " + takes(name) + " A start returns an asynchronous operation (waitMs waits for its result): call this same tool with action=status, operationId and epoch (optionally afterSequence and waitMs) for progress/result, or action=cancel while queued. Disconnect does not cancel. Status of this MCP session's 64 most recent finished operations lasts up to 24 hours; restart loses it. Running file writes cannot be cancelled.",
             "inputSchema": {**obj({**COMMON, **START[name]["properties"]}), "anyOf": [
                 obj({"action": {"type": "string", "enum": ["start"]}, **_start(name)}, ("requestId", *START[name]["required"])),
                 obj({**{k: COMMON[k] for k in FOLLOW}, "action": {"type": "string", "enum": ["status", "cancel"]}},
                     FOLLOW_REQUIRED)]},
             "outputSchema": {"type": "object", "required": ["state"], "properties": {
                 "state": {"type": "string", "enum": ["queued", "running", "succeeded", "failed", "cancelled", "rejected"]},
                 "id": STRING, "epoch": STRING, "requestId": STRING, "operation": STRING,
                 "sequence": {"type": "integer"}, "stage": STRING, "cancellable": BOOL,
                 "progress": {"type": "object", "description": "The engine's latest progress event for the operation: {kind, stage, job, outputs, detail, done, total, elapsedMs}; absent until it says one."},
                 "result": {"type": "object"}, "error": {"type": "string"}}},
             "annotations": {"readOnlyHint": name == "cad_inspect", "destructiveHint": name != "cad_inspect",
                             "idempotentHint": True, "openWorldHint": name != "cad_inspect"}}
            for name, description in DESCRIPTIONS.items()]


def _start(name):
    """What a start takes: its request ID, the tool's own arguments, and how long to wait for its result."""
    return {"requestId": COMMON["requestId"], **START[name]["properties"], "waitMs": COMMON["waitMs"]}


def _shape(groups, optional):
    said = " or ".join("{" + ", ".join(group) + "}" for group in groups)
    return said + (f", optionally with {', '.join(optional)}" if optional else "")


def takes(name):
    """The arguments a tool takes, in one line: what starts it, and what follows one it started."""
    groups = [("requestId", *group) for group in STARTS[name]]
    named = {key for group in groups for key in group}
    start = _shape(groups, [key for key in _start(name) if key not in named])
    follow = _shape([("action: status or cancel", "operationId", "epoch")],
                    [key for key in FOLLOW if key not in FOLLOW_REQUIRED])
    return f"To start: {start}. To follow one: {follow}."


def refusal(tool, missing=(), unknown=(), takes_line=""):
    """A call's arguments refused in words: what is missing, what the tool does not take, and what it takes."""
    said = ([f"missing {', '.join(missing)}"] if missing else []) + ([f"unknown {', '.join(unknown)}"] if unknown else [])
    return f"{tool}: {'; '.join(said)}. {takes_line}".strip()


def check_arguments(name, values):
    """A call's arguments checked against what its action takes, before anything is queued: the action.
    Refused (``JobError``) with every argument missing and every one unknown, and the tool's shape."""
    action = values.get("action", "start")
    checked(action, COMMON["action"], "action")
    if action == "start":
        allowed = _start(name)
        # The set the call reaches for (the one it gives the most of, missing the fewest), else the first.
        given = [group for group in STARTS[name] if any(key in values for key in group)]
        group = min(given, key=lambda group: (sum(key not in values for key in group), -sum(key in values for key in group))) \
            if given else STARTS[name][0]
        required = ("requestId", *group)
        if name == "cad_snapshot" and "packet" in values and "output" in values:
            raise JobError(f"cad_snapshot: a packet declares its outputs; omit output. {takes(name)}")
    else:
        allowed = {key: COMMON[key] for key in FOLLOW}
        required = FOLLOW_REQUIRED
    missing = [key for key in required if key not in values]
    unknown = sorted(key for key in values if key not in allowed and key != "action")
    if missing or unknown:
        raise JobError(refusal(name, missing, unknown, takes(name)))
    for key, item in values.items():
        if key != "action":
            checked(item, allowed[key], key)
    if action != "start":
        return action
    if not re.fullmatch(r"[\w-]{16,100}", values["requestId"]):
        raise JobError("requestId must be 16–100 letters, digits, underscores or hyphens")
    # Paths are checked here too, so nothing is queued that could only fail.
    if "source" in values:
        source(values["source"])
    if "output" in values:
        absolute(values["output"])
    if name == "cad_export":
        destinations = [absolute(path) for path in values["destinations"]]
        from cadgen.engine.ids import is_id

        if len(set(destinations)) != len(destinations) or (not is_id(values["source"]) and absolute(values["source"]) in destinations):
            raise JobError("Export destinations must be distinct from each other and the source")
    return action


def checked(value, schema, label="arguments"):
    """Validate the small JSON schema vocabulary our operation contracts use."""
    kinds = schema.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if kinds and not any(type(value) is types[k] for k in kinds):
        raise JobError(f"{label} must be {' or '.join(kinds)}")
    if "enum" in schema and value not in schema["enum"]:
        raise JobError(f"Invalid {label}: choose from {schema['enum']}")
    if isinstance(value, str) and not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 1000000):
        raise JobError(f"Invalid length for {label}")
    if type(value) is int and not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
        raise JobError(f"Invalid range for {label}")
    if isinstance(value, dict) and "properties" in schema:
        missing = set(schema.get("required", [])) - value.keys()
        unknown = value.keys() - schema["properties"].keys()
        if missing or unknown:
            raise JobError(f"{label}: missing {sorted(missing)}; unknown {sorted(unknown)}")
        for key, item in value.items():
            checked(item, schema["properties"][key], f"{label}.{key}")
    if isinstance(value, list) and "items" in schema:
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10000):
            raise JobError(f"Invalid length for {label}")
        for item in value:
            checked(item, schema["items"], label + "[]")


# The snapshot's words name its command's flags (``--pose '{"hinge": 90}'``); a cad_snapshot's caller
# gave arguments: the same words with each flag named as the argument it is.
_FLAG_VALUE = re.compile(r"--(pose|display|camera) '([^']*)'")
_FLAG = re.compile(r"--(pose|display|camera|annotation|measurements|width|height|grid|size-profile)\b")


def arguments_named(text):
    """A snapshot's refusal in the words of cad_snapshot's arguments, not the command's flags."""
    text = _FLAG_VALUE.sub(lambda found: f"{found[1]} {found[2]}", text)
    return _FLAG.sub(lambda found: found[1].replace("-", "_"), text)


def absolute(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise JobError("Paths must be absolute on the engine host")
    return str(Path(value).resolve())


def source(value):
    """A source: a document id, or an absolute path on the engine host (``FILE#REF`` alike)."""
    from cadgen.engine.ids import is_id

    named = value.partition("#")[0]
    if not is_id(named):
        absolute(named)


def packet_paths(value, override=None):
    """Check paths before the snapshot parser resolves them against process cwd."""
    if isinstance(value, str):
        value = json.loads(value if value.lstrip().startswith(("{", "[")) else
                           Path(absolute(value)).read_text(encoding="utf-8"))
    if isinstance(value, list):
        for item in value:
            packet_paths(item, override)
    elif isinstance(value, dict):
        if "input" in value and override is None:
            source(value["input"])
        if ("annotation" in value and isinstance(value["annotation"], str)
                and not value["annotation"].lstrip().startswith(("{", "["))):
            absolute(value["annotation"])
        for output in value.get("outputs", []):
            absolute(output if isinstance(output, str) else output["path"])
        if isinstance(value.get("measurements"), str) and not value["measurements"].lstrip().startswith(("{", "[")):
            absolute(value["measurements"])
        if "jobs" in value:
            packet_paths(value["jobs"], override)
    return value


def serial(value):
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        # A build may register a viewer URL containing the installation capability.
        return {k: serial(v) for k, v in value.items() if k not in ("url", "token")}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


# What a session keeps of finished operations: the most recent, at most this many and this many
# bytes of reports, so a session never refuses new work for history it holds (each report is
# already cut to REPORT_BYTES), and the request IDs that named them, for ``request_conflict``.
HISTORY_JOBS = 64
HISTORY_BYTES = 32 * 1024 * 1024
HISTORY_REQUESTS = 2048
REPORT_BYTES = 2 * 1024 * 1024


class Operations(Jobs):
    def _prune(self):
        super()._prune()
        finished = [job for job in self.jobs.values() if job["state"] in TERMINAL]
        kept = sum(job.get("kept", 0) for job in finished)
        for job in sorted(finished, key=lambda job: job["finishedAt"]):
            if len(finished) < HISTORY_JOBS and kept <= HISTORY_BYTES:
                break
            self.jobs.pop(job["id"], None)
            finished.remove(job)
            kept -= job.get("kept", 0)
        # A request ID whose operation is gone still answers "expired" until it is the oldest.
        for request_id in [r for r, ident in self.requests.items() if ident not in self.jobs]:
            if len(self.requests) < HISTORY_REQUESTS:
                break
            del self.requests[request_id]

    def call(self, name, arguments):
        try:
            action = check_arguments(name, arguments)
            wait = min(25, arguments.get("waitMs", 0) / 1000)
            if action != "start":
                if arguments["epoch"] != self.epoch:
                    raise JobError("Operation session restarted", 409)
                ident = arguments["operationId"]
                with self.changed:
                    current = self.get(ident)
                    if current["operation"] != name:
                        raise JobError("Use the tool that started this operation", 409)
                    if action == "cancel":
                        return self.cancel(ident)
                    if arguments.get("afterSequence") is None:
                        return self._settled(ident, wait)
                    return self.get(ident, arguments.get("afterSequence"), wait)
            request_id = arguments["requestId"]
            args = {k: v for k, v in arguments.items() if k not in ("action", "requestId", "waitMs")}
            normalized = hashlib.sha256(json.dumps([name, args], sort_keys=True, allow_nan=False).encode()).hexdigest()
            with self.changed:
                # Join retries before re-reading a packet or source that may have changed.
                if request_id in self.requests:
                    started = self._submit(request_id, normalized)
                else:
                    started = self._submit(request_id, normalized, operation=name, arguments=args)
                return self._settled(started["id"], wait) if wait else started
        except (ValueError, TypeError, OSError, KeyError) as error:
            return {"state": "rejected", "error": str(error), "status": getattr(error, "status", 400)}

    def _settled(self, ident, wait):
        """Under changed's lock: the operation once it finished, or as it is after ``wait`` seconds."""
        job = self.jobs.get(ident)
        if job is not None and wait:
            self.changed.wait_for(lambda: job["state"] in TERMINAL, timeout=wait)
        return self.get(ident)

    def public(self, job):
        result = super().public(job)
        if job.get("operation") == "cad_snapshot" and isinstance(result.get("error"), str):
            result["error"] = arguments_named(result["error"])
        if len(json.dumps(result).encode()) <= REPORT_BYTES:
            return result
        # MCP transports have bounded messages. Never silently omit a long report.
        summary = result.get("result") or {}
        return {**{k: v for k, v in result.items() if k not in ("result", "progress", "error")},
                "error": str(result.get("error", ""))[:4096],
                "result": {"truncated": True, "message": "Report exceeds 2 MiB; use the Python API or CLI for the full report.",
                           "id": summary.get("id")}}

    def _failure(self, job, error):
        """Whether a failed operation may have written: only once its export or snapshot was asked
        for (``_perform``), and not where it was refused before any output was opened. A snapshot's
        refusal is that wherever it was raised, here or in the engine (``api._failed`` raises the
        engine's as its own type): ``SnapshotRefused`` is a request the snapshot will not draw,
        refused before it renders, and a picture is written whole or not at all
        (``snapshot.write_png``, ``draw_pictures``). An export's refusal is that only where this
        process raised it, before the engine was asked; one the engine raised may come after a
        destination was written (a DXF's checks, after a STEP beside it)."""
        from cadgen.engine.export import ExportRefused
        from cadgen.engine.snapshot import SnapshotRefused

        refused_before = isinstance(error, SnapshotRefused) or (
            isinstance(error, ExportRefused) and not getattr(error, "_engine_refusal", False))
        return {"result": {"outputsMayHaveBeenWritten": bool(job.get("writing")) and not refused_before}}

    def _finished(self, job):
        job.pop("arguments", None)
        # Keep only what status can send: a long report is held as its summary, never in full.
        public = self.public(job)
        job.update({k: public[k] for k in ("result", "error") if k in public})
        if "progress" not in public:
            job.pop("progress", None)
        job["kept"] = len(json.dumps(public).encode())

    def _perform(self, job, progress):
        """The operation run through the engine's verb; where it is comes from the engine alone, as
        progress events (``cadgen.engine.progress``) handed to ``progress``, never a word of this
        module's own."""
        from cadgen.engine import api
        name, args = job["operation"], dict(job["arguments"])
        if name == "cad_export":
            destinations = [absolute(path) for path in args.pop("destinations")]
            # Keep the one Python operation: all destinations are validated and share a document read.
            src = args.pop("source")
            job["writing"] = True
            result = {"files": serial(api.export(src, *destinations, **args, progress=progress))}
        elif name == "cad_snapshot":
            packet = args.pop("packet", None)
            output = args.pop("output", None)
            for field in ("annotation", "measurements"):
                if isinstance(args.get(field), str) and not args[field].lstrip().startswith(("{", "[")):
                    absolute(args[field])
            if packet is not None:
                packet = packet_paths(packet, args.get("source"))
                job["writing"] = True
                result = {"pictures": serial(api.snapshot(job=packet, **args, progress=progress))}
            else:
                job["writing"] = True
                result = {"pictures": [serial(api.snapshot(**args, out=absolute(output), progress=progress))]}
        elif name == "cad_inspect":
            if "ref" not in args and "query" not in args and "#" not in args["source"]:
                args["query"] = "summary"  # what `cadgen inspect SOURCE` prints (``engine.cli``)
            found = serial(api.inspect(**args, progress=progress))
            if isinstance(found, dict) and isinstance(found.get("summary"), dict):
                from cadgen.engine.cli import summary_text

                found = {**found, "text": summary_text(found["summary"])}
            result = {"inspection": found}
        return {"state": "succeeded", "stage": "Complete", "result": result}
