"""The CAD Viewer's local-filesystem backend.

Owns root resolution, catalog absolutization (raw scanner URLs ->
``/__cad/asset?file=...`` form the client consumes verbatim), the guarded
asset-path resolver, and the render-artifact build/export routes that shell
out to cadgen.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit, parse_qs, unquote

from . import artifact as artifact_mod
from . import cadgen_bridge
from . import paths
from . import scanner
from .content_types import content_type_for_path
from .save_dialog import pick_save_destination
from .urls import local_asset_url_for_path

_STEP_EXPORT_FORMAT_SUFFIX = {"step": "step", "stl": "stl", "3mf": "3mf", "glb": "glb"}

# How long an artifact build may wait for a peer's generation lock before reporting the
# peer's run instead. Long enough that an UNCONTENDED acquire never trips it (it is a
# couple of syscalls), short enough that a POST cannot park the shared warm worker.
_ARTIFACT_LOCK_TIMEOUT_SECONDS = 0.5

# The formats an `.implicit.js` model exports to. Rejected here only so a bad request fails
# before a Node process is spawned; `cadgen.implicit_export` holds the authoritative list
# beside the exporter it drives, and validates again.
_IMPLICIT_EXPORT_FORMATS = ("stl", "glb", "3mf")


def _to_posix(value: str) -> str:
    return str(value or "").replace(os.sep, "/")


def absolute_file_ref(file_path: str) -> str:
    return _to_posix(os.path.abspath(file_path))


def relative_file_ref(root_path: str, file_path: str) -> str:
    return _to_posix(os.path.relpath(os.path.abspath(file_path), os.path.abspath(root_path)))


def normalized_file_ref(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if "\0" in raw:
        raise ValueError("File path contains an invalid null byte")
    # A ref can reach us in URL-path form (`/D:/models/part.step`) the same way ?dir= does.
    raw = paths.filesystem_path_from_url_path(raw)
    return absolute_file_ref(raw) if os.path.isabs(raw) else raw.lstrip("/")


def require_directory(root_path: str) -> None:
    if not os.path.isdir(root_path):
        raise ValueError(f"CAD Viewer directory not found: {root_path}")


class ForbiddenAssetError(Exception):
    status_code = 403


def _query_value(raw_url: str, name: str) -> str:
    try:
        params = parse_qs(urlsplit(str(raw_url or "")).query)
        return (params.get(name) or [""])[0]
    except ValueError:
        return ""


def _asset_path_from_catalog_url(scan_repo_root: str, raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
        explicit_file = (parse_qs(parts.query).get("file") or [""])[0]
        if explicit_file:
            return os.path.abspath(explicit_file)
        return os.path.abspath(os.path.join(scan_repo_root, unquote(parts.path).lstrip("/")))
    except ValueError:
        cleaned = text.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        return os.path.abspath(os.path.join(scan_repo_root, cleaned))


def _absolute_path_from_catalog_value(scan_repo_root: str, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if os.path.isabs(text):
        return os.path.abspath(text)
    return os.path.abspath(os.path.join(scan_repo_root, text))


def _absolutize_keyed(obj, scan_repo_root: str, keys):
    if not isinstance(obj, dict):
        return obj
    nxt = dict(obj)
    for key in keys:
        if nxt.get(key):
            nxt[key] = absolute_file_ref(_absolute_path_from_catalog_value(scan_repo_root, nxt[key]))
    return nxt


def _absolutize_source(source, scan_repo_root):
    return _absolutize_keyed(source, scan_repo_root, ("file", "path", "sourcePath"))


def _absolutize_source_status(status, scan_repo_root):
    return _absolutize_keyed(status, scan_repo_root, ("sourcePath", "stepPath", "packagePath"))


def _absolutize_artifact(artifact, scan_repo_root):
    return _absolutize_keyed(artifact, scan_repo_root, ("stepPath", "packagePath", "sourcePath", "cadPath"))


def _absolutize_entry(entry: dict, *, root_path: str, scan_repo_root: str, root_dir: str) -> dict:
    output_path = os.path.abspath(os.path.join(root_path, str(entry.get("file") or "")))
    nxt = dict(entry)
    nxt["file"] = absolute_file_ref(output_path)
    nxt["rootRelativeFile"] = relative_file_ref(root_path, output_path)
    if entry.get("url"):
        asset_path = _asset_path_from_catalog_url(scan_repo_root, entry["url"])
        nxt["url"] = local_asset_url_for_path(asset_path, version=_query_value(entry["url"], "v"), root_dir=root_dir)
        nxt["assetFile"] = absolute_file_ref(asset_path)
    if entry.get("moduleUrl"):
        module_path = _asset_path_from_catalog_url(scan_repo_root, entry["moduleUrl"])
        nxt["moduleUrl"] = local_asset_url_for_path(module_path, version=_query_value(entry["moduleUrl"], "v"), root_dir=root_dir)
        nxt["moduleFile"] = absolute_file_ref(module_path)
    if entry.get("source"):
        nxt["source"] = _absolutize_source(entry["source"], scan_repo_root)
    if entry.get("sourceStatus"):
        nxt["sourceStatus"] = _absolutize_source_status(entry["sourceStatus"], scan_repo_root)
    if entry.get("artifact"):
        nxt["artifact"] = _absolutize_artifact(entry["artifact"], scan_repo_root)
    relations = entry.get("relations")
    if isinstance(relations, dict):
        nxt_relations = {}
        for key, relation in relations.items():
            if not isinstance(relation, dict):
                nxt_relations[key] = relation
                continue
            relation_path = os.path.abspath(os.path.join(root_path, str(relation.get("file") or "")))
            nxt_relation = dict(relation)
            nxt_relation["file"] = absolute_file_ref(relation_path)
            nxt_relation["rootRelativeFile"] = relative_file_ref(root_path, relation_path)
            if relation.get("url"):
                rel_asset = _asset_path_from_catalog_url(scan_repo_root, relation["url"])
                nxt_relation["url"] = local_asset_url_for_path(rel_asset, version=_query_value(relation["url"], "v"), root_dir=root_dir)
                nxt_relation["assetFile"] = absolute_file_ref(rel_asset)
            nxt_relations[key] = nxt_relation
        nxt["relations"] = nxt_relations
    return nxt


class LocalAssetBackend:
    """Serves whatever directory a request names. There is no configured root.

    A request's directory is an absolute filesystem path (the page URL's path;
    see server.py). It is its own scan root, so there is no base-vs-request root
    to reconcile, no relative-vs-absolute resolution, and no re-basing of scanned
    entries. An empty directory means the process cwd.
    """

    kind = "local-fs"

    def resolve_root(self, root_dir: str = "") -> dict:
        # ?dir= is a URL path, so a Windows root arrives as `/D:/models`; abspath would
        # read the leading slash as the current drive's root and answer `C:\D:\models`.
        requested = paths.filesystem_path_from_url_path(str(root_dir or "").strip())
        root_path = os.path.abspath(requested or os.getcwd())
        if "\0" in root_path:
            raise ValueError("CAD Viewer directory contains an invalid null byte")
        require_directory(root_path)
        return {"dir": absolute_file_ref(root_path), "rootPath": root_path, "rootName": os.path.basename(root_path)}

    def read_catalog(self, root_dir: str = "", file_ref: str = "") -> dict:
        resolved_root = self.resolve_root(root_dir)
        root_path = resolved_root["rootPath"]
        raw = scanner.scan_cad_directory(root_path, include_artifact_status=False)
        entries = [
            _absolutize_entry(entry, root_path=root_path, scan_repo_root=root_path, root_dir=resolved_root["dir"])
            for entry in raw["entries"]
        ]
        return {"schemaVersion": scanner.CAD_CATALOG_SCHEMA_VERSION, "entries": entries}

    def asset_path_for_file_ref(self, file_ref: str, resolved_root: dict | None = None, root_dir: str = "") -> str | None:
        normalized = normalized_file_ref(file_ref)
        if not normalized or not os.path.isabs(normalized):
            return None
        candidate = os.path.abspath(normalized)
        if not scanner.is_served_cad_asset(candidate):
            return None
        active = resolved_root or (self.resolve_root(root_dir) if root_dir else None)
        if active:
            if not (candidate == active["rootPath"] or scanner.path_is_inside(candidate, active["rootPath"])):
                raise ForbiddenAssetError("Forbidden")
            # Hidden (dot-prefixed) directories below the served root are never served;
            # only root-relative components are checked so a root that itself lives under
            # a hidden absolute path still works.
            relative = os.path.relpath(candidate, active["rootPath"])
            if any(part.startswith(".") for part in relative.split(os.sep) if part and part != ".."):
                return None
        return candidate

    def content_type_for_path(self, file_path: str) -> str:
        return content_type_for_path(file_path)

    def catalog_entry_for_file_ref(self, catalog, file_ref):
        norm = normalized_file_ref(file_ref)
        if not norm or not isinstance(catalog, dict):
            return None
        for entry in catalog.get("entries", []):
            if normalized_file_ref(entry.get("file")) == norm or normalized_file_ref(entry.get("rootRelativeFile")) == norm:
                return entry
        return None

    def _source_candidates_for_file_ref(self, file_ref, resolved_root):
        normalized = normalized_file_ref(file_ref)
        if not normalized:
            return "", []
        if os.path.isabs(normalized):
            candidates = [os.path.abspath(normalized), os.path.abspath(os.path.join(resolved_root["rootPath"], normalized.lstrip("/")))]
        else:
            candidates = [os.path.abspath(os.path.join(resolved_root["rootPath"], normalized))]
        seen = []
        existing = []
        for c in candidates:
            if c in seen:
                continue
            seen.append(c)
            inside = c == resolved_root["rootPath"] or scanner.path_is_inside(c, resolved_root["rootPath"])
            if inside and os.path.exists(c):
                existing.append(c)
        return normalized, existing

    def resolve_step_source(self, file_ref, resolved_root):
        normalized, candidates = self._source_candidates_for_file_ref(file_ref, resolved_root)
        if not normalized:
            raise ValueError("Missing STEP file")
        for c in candidates:
            ext = os.path.splitext(c)[1].lower()
            if ext == ".py":
                stem = os.path.basename(c)[: -len(".py")]
                step_base = stem if re.search(r"\.(step|stp)$", stem, re.IGNORECASE) else stem + ".step"
                return {"stepPath": os.path.join(os.path.dirname(c), step_base), "sourcePath": c, "skipStepWrite": True}
            if ext not in (".step", ".stp"):
                raise ValueError("Only STEP/STP sources or same-stem Python generators can generate STEP topology artifacts")
            # A same-stem `<name>.step.py` generator OWNS the entry even when an
            # exported `<name>.step` sits beside it. The export is the generator's
            # output, and only the generator can declare the model's `params`
            # sidecar -- the documented way to attach one to an imported STEP.
            # Resolving it here keeps the
            # build, the freshness check and STEP export all keyed on the same
            # source. cadgen's generator mode writes only the render package, so
            # the exported `.step` beside it is never rewritten.
            generator = self._same_stem_python_generator_path(c)
            if generator:
                return {"stepPath": c, "sourcePath": generator, "skipStepWrite": True}
            return {"stepPath": c, "sourcePath": "", "skipStepWrite": False}
        raise ValueError(f"STEP file not found: {normalized}")

    def resolve_dxf_source(self, file_ref, resolved_root):
        # Both DXF inputs resolve here, exactly as both STEP inputs do above: a `.dxf.py`
        # generator (run it) and an imported `.dxf` (copy it in and bake its preview). An
        # imported drawing is artifact-managed because the package's preview.glb is the only
        # 3D DXF renderer there is.
        normalized, candidates = self._source_candidates_for_file_ref(file_ref, resolved_root)
        if not normalized:
            raise ValueError("Missing DXF file")
        for c in candidates:
            if not scanner.is_dxf_generator_path(c) and os.path.splitext(c)[1].lower() != ".dxf":
                raise ValueError(
                    "Only .dxf drawings and .dxf.py drawing generators can generate DXF drawing artifacts"
                )
            return {"sourcePath": c}
        raise ValueError(f"DXF source not found: {normalized}")

    def resolve_implicit_source(self, file_ref, resolved_root):
        # One input, one resolution: the `.implicit.js` model itself. There is no generator
        # indirection (the model IS the generator) and no exported sibling to prefer.
        normalized, candidates = self._source_candidates_for_file_ref(file_ref, resolved_root)
        if not normalized:
            raise ValueError("Missing implicit CAD file")
        for c in candidates:
            if not scanner.path_is_implicit_cad_source(c):
                raise ValueError(
                    "Only .implicit.js models can generate implicit CAD render artifacts"
                )
            return {"sourcePath": c}
        raise ValueError(f"Implicit CAD source not found: {normalized}")

    # One record per render-package format, matched in order. Everything that used to be an
    # `if owns_dxf_entry(entry): ... else: ...` at three call sites lives here, so adding a
    # format is a row rather than another branch in each method.
    #
    # The table is TOTAL by construction: it RAISES when no predicate matches instead of
    # falling through to STEP. A half-wired format that silently answered as STEP would
    # validate an assembly.json that does not exist, report `ready` for the missing-source
    # code, and never build -- the failure mode this shape exists to make impossible.
    def _artifact_format(self, entry):
        formats = (
            (artifact_mod.owns_dxf_entry, {
                "validate": artifact_mod.validate_dxf_freshness,
                "resolve_source": lambda file_ref, root: self.resolve_dxf_source(file_ref, root)["sourcePath"],
                "build": self.generate_dxf_artifact,
            }),
            (artifact_mod.owns_implicit_entry, {
                "validate": artifact_mod.validate_implicit_freshness,
                "resolve_source": lambda file_ref, root: self.resolve_implicit_source(file_ref, root)["sourcePath"],
                "build": self.generate_implicit_artifact,
            }),
            (artifact_mod.owns_step_entry, {
                "validate": artifact_mod.validate_step_freshness,
                "resolve_source": self._resolve_step_artifact_source,
                "build": self.generate_step_artifact,
            }),
        )
        for owns, record in formats:
            if owns(entry):
                return record
        raise ValueError(
            f"No render-artifact format owns this entry: {str((entry or {}).get('file') or '(unknown)')}"
        )

    def _resolve_step_artifact_source(self, file_ref, resolved_root):
        resolved = self.resolve_step_source(file_ref, resolved_root)
        return resolved.get("sourcePath") or resolved["stepPath"]

    def artifact_status(self, file_ref, resolved_root, catalog):
        entry = self.catalog_entry_for_file_ref(catalog, file_ref)
        ref = str((entry or {}).get("url") or "")
        if not artifact_mod.owns_entry(entry):
            return {"state": artifact_mod.ARTIFACT_STATE_READY, "ref": ref}
        fmt = self._artifact_format(entry)
        try:
            artifact_source = fmt["resolve_source"](file_ref, resolved_root)
        except ValueError as exc:
            return {"state": artifact_mod.ARTIFACT_STATE_ERROR, "error": str(exc)}
        package_dir = scanner.render_package_dir(artifact_source)
        snap = artifact_mod.generation_snapshot(package_dir)
        if snap.writing:
            # The LOCK decides the state; the record only says how far along it is, and is
            # omitted when the build has not reported yet, or when the record on disk
            # belongs to some other (dead) run. runId lets the client tell one run from the
            # next, so its bar resets on a handoff instead of jumping backwards.
            status = {"state": artifact_mod.ARTIFACT_STATE_GENERATING, "ref": ref}
            if snap.run_id:
                status["runId"] = snap.run_id
            if snap.progress is not None:
                status["progress"] = snap.progress
            return status
        ok, code = fmt["validate"](resolved_root["rootPath"], artifact_source)
        if ok:
            # A busy GENERATOR (an export running this model's gen_step) does not hide a
            # renderable model -- nothing is rewriting the package, so what is on disk is
            # still valid. Annotated so the client can say why a build is unavailable.
            status = {"state": artifact_mod.ARTIFACT_STATE_READY, "ref": ref}
            if snap.busy:
                status["busy"] = True
                # An occupied generator (an export, an on-demand topology extraction) runs
                # the same multi-minute gen_step a build does. It does NOT hide the model —
                # nothing is being rewritten — so this rides alongside a ready artifact and
                # the client shows it without blocking the render.
                if snap.run_id:
                    status["runId"] = snap.run_id
                if snap.progress is not None:
                    status["progress"] = snap.progress
            return status
        if code in artifact_mod.BUILDABLE_ARTIFACT_CODES:
            status = {"state": artifact_mod.ARTIFACT_STATE_NEEDS_BUILD, "reason": code, "ref": ref}
            if snap.busy:
                # Stale AND the generator is occupied (an export is running this model's
                # gen_step). A build would NOT block on it -- the two take different
                # sentinels precisely so they do not exclude each other -- it would run the
                # same generator a second time, concurrently, for nothing. Telling the
                # client to wait is an efficiency call, not a deadlock avoidance one.
                status["blocked"] = True
            return status
        return {"state": artifact_mod.ARTIFACT_STATE_ERROR, "reason": code, "error": code, "ref": ref}

    def _same_stem_python_generator_path(self, step_path):
        ext = os.path.splitext(step_path)[1].lower()
        if ext not in (".step", ".stp"):
            return ""
        candidate = os.path.join(os.path.dirname(step_path), os.path.basename(step_path) + ".py")
        return candidate if scanner._file_has_python_generator(candidate, "gen_step") else ""

    # POST /__cad/artifact build — subprocess cadgen.step_artifact_cli (OCP stays out of
    # the server process).
    def generate_step_artifact(self, file_ref, force, resolved_root, catalog):
        resolved = self.resolve_step_source(file_ref, resolved_root)
        step_path = resolved["stepPath"]
        ext = os.path.splitext(step_path)[1].lower()
        has_step = ext in (".step", ".stp") and os.path.isfile(step_path)
        # resolve_step_source already prefers a same-stem generator over a sibling
        # export, so both the freshness check and this build key on one source.
        generator = resolved.get("sourcePath") or ""
        has_generator = bool(generator) and os.path.isfile(generator)
        if not has_step and not has_generator:
            raise ValueError("CAD Viewer regenerates GLB artifacts only for existing STEP/STP files or their same-stem Python generators.")
        args = ["--step", step_path]
        if has_generator:
            # Generated models keep no .step on disk — --source-path selects generator
            # mode: cadgen runs the generator in-process and writes only the render
            # package (the logical --step path never exists).
            args += ["--source-path", generator]
        result = self._run_artifact_build(
            "cadgen.step_artifact_cli", args, resolved_root["rootPath"],
            force=force, error_label="STEP render artifact build failed",
        )
        return {**result, "stepPath": step_path}

    # POST /__cad/artifact build for a generated `.dxf.py` drawing — subprocess
    # cadgen.dxf_artifact (parity with the STEP build; the generator runs out of the
    # server process).
    def generate_dxf_artifact(self, file_ref, force, resolved_root, catalog):
        resolved = self.resolve_dxf_source(file_ref, resolved_root)
        source_path = resolved["sourcePath"]
        result = self._run_artifact_build(
            "cadgen.dxf_artifact", ["--source-path", source_path], resolved_root["rootPath"],
            force=force, error_label="DXF render artifact build failed",
        )
        return {**result, "sourcePath": source_path}

    # POST /__cad/artifact build for an `.implicit.js` model — subprocess
    # cadgen.implicit_artifact. Same shape as the DXF build: the cadgen module holds the
    # generation lock and owns the Node mesher's lifetime, so nothing about "the geometry is
    # produced in JS" leaks into this process.
    def generate_implicit_artifact(self, file_ref, force, resolved_root, catalog):
        resolved = self.resolve_implicit_source(file_ref, resolved_root)
        source_path = resolved["sourcePath"]
        result = self._run_artifact_build(
            "cadgen.implicit_artifact", ["--source-path", source_path], resolved_root["rootPath"],
            force=force, error_label="Implicit CAD render artifact build failed",
        )
        return {**result, "sourcePath": source_path}

    # Shared build tail for both artifact formats: run the cadgen module in a
    # subprocess/worker. Freshness is decided by the recorded source-closure CONTENT
    # hash, so there is nothing to touch afterwards — the descriptor mtime bump this
    # used to do existed only to quiet the old mtime staleness trigger after a
    # rebuild that the CLI had correctly skipped as current.
    def _run_artifact_build(self, module, args, root_path, *, force, error_label):
        full_args = ["--repo-root", root_path, *args]
        if force:
            full_args += ["--force"]
        # NEVER wait out a peer inside a build. cadgen's acquire is blocking by default,
        # which is right for a CLI (an agent asking for a build wants the build) and wrong
        # here: this request runs in the ONE serial warm worker, so a build parked on
        # another process's lock stops every OTHER model's build and export for as long as
        # the peer runs -- measured at 32s for an unrelated, already-current model. The
        # snap.writing pre-check in resolve_artifact narrows the window but cannot close it
        # (a peer can take the lock right after the snapshot, and force= skips the check
        # entirely). This is the part that actually cannot block.
        full_args += ["--lock-timeout", str(_ARTIFACT_LOCK_TIMEOUT_SECONDS)]
        if os.environ.get("VIEWER_STEP_ARTIFACT_VERBOSE") == "1":
            full_args += ["--verbose"]
        result = cadgen_bridge.run_cadgen(module, full_args, root_path)
        if result.get("contended"):
            # A peer holds the lock. Nothing failed and nothing was built: the caller
            # reports the peer's run so the client attaches to its progress.
            return {"ok": True, "contended": True, "error": "", "result": result}
        error = "" if result.get("ok") else str(result.get("error") or error_label)
        return {"ok": bool(result.get("ok")), "error": error, "result": result}

    def resolve_artifact(self, file_ref, force, resolved_root, catalog):
        entry = self.catalog_entry_for_file_ref(catalog, file_ref)
        ref = str((entry or {}).get("url") or "")
        if not artifact_mod.owns_entry(entry):
            return {"ok": True, "state": artifact_mod.ARTIFACT_STATE_READY, "ref": ref}
        fmt = self._artifact_format(entry)
        try:
            artifact_source = fmt["resolve_source"](file_ref, resolved_root)
        except ValueError as exc:
            return {"ok": False, "state": artifact_mod.ARTIFACT_STATE_ERROR, "error": str(exc)}
        # A POST NEVER BLOCKS ON A PEER. This used to wait up to 180 SECONDS in
        # await_generation_lock, discard the timeout's return value, and then build anyway
        # -- so a user who opened a model during a long `cad gen` waited out the CLI run
        # and then paid for a full duplicate rebuild, with the bar restarting from zero.
        # Worse, that queued build then blocked inside the single process-global worker
        # lock, freezing every OTHER model's build and export for the duration.
        #
        # Reporting `generating` immediately lets the client attach to the peer's run and
        # watch its live progress instead, which is both faster and truthful.
        #
        # This check is the FAST PATH, not the guarantee: it is a snapshot, so a peer can
        # take the lock immediately after it, and force= skips it entirely. The guarantee is
        # the bounded --lock-timeout in _run_artifact_build, whose contended result lands on
        # the same answer below.
        snap = artifact_mod.generation_snapshot(scanner.render_package_dir(artifact_source))
        if not force and snap.writing:
            result = {"ok": True, "state": artifact_mod.ARTIFACT_STATE_GENERATING, "ref": ref}
            if snap.run_id:
                result["runId"] = snap.run_id
            return result
        built = fmt["build"](file_ref, force, resolved_root, catalog)
        if built.get("contended"):
            # The peer took the lock between the snapshot above and the build (or force=
            # skipped that check). Same answer as the pre-check: attach to their run.
            result = {"ok": True, "state": artifact_mod.ARTIFACT_STATE_GENERATING, "ref": ref}
            live = artifact_mod.generation_snapshot(scanner.render_package_dir(artifact_source))
            if live.run_id:
                result["runId"] = live.run_id
            return result
        if built["ok"]:
            return {"ok": True, "state": artifact_mod.ARTIFACT_STATE_READY, "ref": ref}
        return {"ok": False, "state": artifact_mod.ARTIFACT_STATE_ERROR, "error": built["error"]}

    # POST /__cad/export — native Save dialog (subprocess) + a cadgen export module
    # (subprocess). Headless fallback writes beside the source + a download URL. One route
    # for every exportable entry: the source file decides which producer runs.
    def generate_export(self, file_ref, fmt, resolved_root, catalog):
        normalized = str(fmt or "").strip().lower()
        if scanner.is_dxf_generator_path(str(normalized_file_ref(file_ref))):
            if normalized != "dxf":
                raise ValueError(f"Unsupported export format for a DXF drawing: {fmt}")
            return self.generate_dxf_export(file_ref, resolved_root)
        if scanner.path_is_implicit_cad_source(str(normalized_file_ref(file_ref))):
            return self.generate_implicit_export(file_ref, normalized, resolved_root)
        if normalized not in _STEP_EXPORT_FORMAT_SUFFIX:
            raise ValueError(f"Unsupported export format: {fmt}")
        resolved = self.resolve_step_source(file_ref, resolved_root)
        step_path = resolved["stepPath"]
        source_path = resolved["sourcePath"]
        if not (step_path == resolved_root["rootPath"] or scanner.path_is_inside(step_path, resolved_root["rootPath"])):
            raise ValueError("Requested file is outside the active CAD Viewer root")
        base_name = re.sub(r"\.(step|stp)$", "", os.path.basename(step_path), flags=re.IGNORECASE)

        def _export(out_path):
            args = ["--repo-root", resolved_root["rootPath"], "--step", step_path, "--format", normalized, "--out", out_path]
            if source_path:
                args += ["--source-path", source_path]
            return cadgen_bridge.run_cadgen("cadgen.step_export_target", args, resolved_root["rootPath"])

        return self._export_with_destination(
            resolved_root,
            run_export=_export,
            base_name=base_name,
            suggested_name=f"{base_name}.{_STEP_EXPORT_FORMAT_SUFFIX[normalized]}",
            default_dir=os.path.dirname(step_path),
            format_name=normalized,
            error_label="STEP export failed",
        )

    # Export a generated `.dxf.py` drawing as a `.dxf` file — cadgen.dxf_artifact with
    # --export ensures the drawing package is fresh (rebuilding if the source changed)
    # and writes the DXF to the chosen path.
    def generate_dxf_export(self, file_ref, resolved_root):
        resolved = self.resolve_dxf_source(file_ref, resolved_root)
        source_path = resolved["sourcePath"]
        base_name = os.path.basename(source_path)[: -len(".dxf.py")]

        def _export(out_path):
            args = ["--repo-root", resolved_root["rootPath"], "--source-path", source_path, "--export", out_path]
            return cadgen_bridge.run_cadgen("cadgen.dxf_artifact", args, resolved_root["rootPath"])

        return self._export_with_destination(
            resolved_root,
            run_export=_export,
            base_name=base_name,
            suggested_name=f"{base_name}.dxf",
            default_dir=os.path.dirname(source_path),
            format_name="dxf",
            error_label="DXF export failed",
        )

    # Export an `.implicit.js` model as STL/GLB/3MF — cadgen.implicit_export runs the
    # shipped implicitjs export CLI in a Node child, under the model's GENERATOR lock.
    #
    # This used to happen in the browser: the client loaded the model module, meshed and
    # serialized it in the tab, and POSTed the bytes here to be written to disk. That kept a
    # second live geometry runtime in the viewer for the sake of one menu item. The mesher
    # is the same JS either way; only the process differs.
    def generate_implicit_export(self, file_ref, fmt, resolved_root):
        normalized = str(fmt or "").strip().lower().lstrip(".")
        if normalized not in _IMPLICIT_EXPORT_FORMATS:
            raise ValueError(f"Unsupported implicit CAD export format: {fmt or '(missing)'}")
        resolved = self.resolve_implicit_source(file_ref, resolved_root)
        source_path = resolved["sourcePath"]
        base_name = re.sub(r"\.implicit\.(?:mjs|js)$", "", os.path.basename(source_path), flags=re.IGNORECASE)

        def _export(out_path):
            args = [
                "--repo-root", resolved_root["rootPath"],
                "--source-path", source_path,
                "--format", normalized,
                "--out", out_path,
            ]
            return cadgen_bridge.run_cadgen("cadgen.implicit_export", args, resolved_root["rootPath"])

        return self._export_with_destination(
            resolved_root,
            run_export=_export,
            base_name=base_name,
            suggested_name=f"{base_name}.{normalized}",
            default_dir=os.path.dirname(source_path),
            format_name=normalized,
            error_label="Implicit CAD export failed",
        )

    # Shared export orchestration for every format: native Save dialog, chosen-path
    # write, or the headless fallback beside the source with a /__cad/download URL.
    def _export_with_destination(
        self, resolved_root, *, run_export, base_name, suggested_name, default_dir, format_name, error_label
    ):
        destination = pick_save_destination(
            suggested_name=suggested_name, default_dir=default_dir,
            prompt=f"Export {base_name} as {format_name.upper()}",
        )
        if destination.get("cancelled"):
            return {"ok": False, "cancelled": True}

        if destination.get("path"):
            result = run_export(os.path.abspath(destination["path"]))
            if not result.get("ok"):
                return {"ok": False, "error": str(result.get("error") or error_label)}
            out_path = os.path.abspath(result.get("path") or destination["path"])
            inside = out_path == resolved_root["rootPath"] or scanner.path_is_inside(out_path, resolved_root["rootPath"])
            return {"ok": True, "path": out_path, "filename": result.get("filename") or os.path.basename(out_path),
                    "format": format_name, "catalogChanged": inside}

        # Headless fallback: write beside the source, hand to the browser via /__cad/download.
        output_path = os.path.join(default_dir, suggested_name)
        if not (output_path == resolved_root["rootPath"] or scanner.path_is_inside(output_path, resolved_root["rootPath"])):
            raise ValueError("Requested file is outside the active CAD Viewer root")
        result = run_export(output_path)
        if not result.get("ok"):
            return {"ok": False, "error": str(result.get("error") or error_label)}
        output_file_ref = _to_posix(os.path.relpath(output_path, resolved_root["rootPath"]))
        return {"ok": True, "fallback": True, "path": output_path, "filename": os.path.basename(output_path),
                "format": format_name, "catalogChanged": True, "outputFileRef": output_file_ref}

