"""Deterministic unit tests for the /__cad/artifact freshness logic.

Builds a synthetic imported-.step component-GLB package (no cadgen/OCP) and
checks the state machine: ready / stale_step_artifact / missing_glb /
unsupported, the owns_entry gate, and the generation-lock reader.
"""

import ast
import inspect
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time

try:
    import fcntl
except ImportError:  # Windows -- see GenerationLock, which is the only user.
    fcntl = None
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import artifact, scanner  # noqa: E402

from cadgen._internal import drawing_package as _drawing_package  # noqa: E402
from cadgen._internal.drawing_package import (  # noqa: E402
    DXF_PACKAGE_SCHEMA_VERSION,
    drawing_preview_bake_settings,
)
from cadgen._internal import implicit_package as _implicit_package  # noqa: E402
from cadgen._internal.implicit_package import (  # noqa: E402
    IMPLICIT_PACKAGE_SCHEMA_VERSION,
    implicit_bake_settings,
)
from cadgen._internal.package_freshness import (  # noqa: E402
    STEP_PACKAGE_VERSION as _STEP_SCHEMA_VERSION,
    canonical_bake_hash,
)
from cadgen._internal.source_hash import closure_for_files  # noqa: E402


def _dump(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _closure_for(source, base):
    return closure_for_files(pathlib.Path(source), [pathlib.Path(source)], base=pathlib.Path(base))

_DXF_SCHEMA_VERSION = DXF_PACKAGE_SCHEMA_VERSION
_IMPLICIT_SCHEMA_VERSION = IMPLICIT_PACKAGE_SCHEMA_VERSION

# Sentinel for "write no such key at all", distinct from "write an empty one".
_OMIT = object()


def _write_package(
    root,
    step_name,
    *,
    source_kind="step",
    step_hash=None,
    components=None,
    schema_version=_STEP_SCHEMA_VERSION,
    bake_hash=None,
):
    """Create <root>/<step_name> + its __cadgen__/models/<step_name> package."""
    step_path = os.path.join(root, step_name)
    with open(step_path, "wb") as h:
        h.write(b"ISO-10303-21;\nfake step\n")
    with open(step_path, "rb") as h:
        actual_hash = hashlib.sha256(h.read()).hexdigest()
    pkg = os.path.join(root, "__cadgen__", "models", step_name)
    comp_dir = os.path.join(pkg, "components")
    os.makedirs(comp_dir, exist_ok=True)
    comps = {}
    for cid in (components if components is not None else ["c0"]):
        rel = f"components/{cid}.glb"
        with open(os.path.join(pkg, rel), "wb") as h:
            h.write(b"glTF\x02\x00\x00\x00")
        comps[cid] = {"glb": rel}
    descriptor = {
        "kind": "assembly-package",
        "sourceKind": source_kind,
        "components": comps,
    }
    if schema_version is not None:
        descriptor["packageSchemaVersion"] = schema_version
    if step_hash is not _OMIT:
        descriptor["stepHash"] = step_hash if step_hash is not None else actual_hash
    if bake_hash is not None:
        descriptor["bakeHash"] = bake_hash
    with open(os.path.join(pkg, "assembly.json"), "w") as h:
        json.dump(descriptor, h)
    return step_path, pkg


class OwnsEntry(unittest.TestCase):
    def test_step_and_generated_step_py_are_owned(self):
        self.assertTrue(artifact.owns_entry({"file": "/x/a.step"}))
        self.assertTrue(artifact.owns_entry({"file": "/x/a.STP"}))
        # Generated models are owned too — they get the needs-build/build flow so a
        # not-yet-built .step.py is listed and built on demand.
        self.assertTrue(artifact.owns_entry({"file": "/x/a.step.py"}))
        self.assertTrue(artifact.owns_entry({"file": "/x/a.STP.py"}))
        self.assertFalse(artifact.owns_entry({"file": "/x/a.stl"}))
        self.assertFalse(artifact.owns_entry({"file": "/x/lib.py"}))  # plain .py is not a model
        self.assertFalse(artifact.owns_entry(None))


class ImportedStepFreshness(unittest.TestCase):
    def test_fresh_package_is_ready(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step")
            self.assertEqual(artifact.validate_step_freshness(d, step), (True, None))

    def test_stale_step_hash(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", step_hash="deadbeef")
            self.assertEqual(artifact.validate_step_freshness(d, step), (False, "stale_step_artifact"))

    def test_missing_component_glb(self):
        with tempfile.TemporaryDirectory() as d:
            step, pkg = _write_package(d, "imp.step")
            os.remove(os.path.join(pkg, "components", "c0.glb"))
            self.assertEqual(artifact.validate_step_freshness(d, step), (False, "missing_glb"))

    def test_unsupported_descriptor(self):
        with tempfile.TemporaryDirectory() as d:
            step, pkg = _write_package(d, "imp.step")
            with open(os.path.join(pkg, "assembly.json"), "w") as h:
                json.dump({"kind": "something-else"}, h)
            self.assertEqual(artifact.validate_step_freshness(d, step), (False, "unsupported_step_topology"))

    def test_missing_package_is_buildable(self):
        with tempfile.TemporaryDirectory() as d:
            step = os.path.join(d, "imp.step")
            open(step, "wb").close()
            self.assertEqual(artifact.validate_step_freshness(d, step), (False, "missing_glb"))


class ImportedDigestFailsClosed(unittest.TestCase):
    """A descriptor that records no digest for a source file that exists cannot be shown
    to be current, and must report needs-build rather than ready. This was the validator's
    last fail-OPEN path; cadgen's producer gate has always compared the file's real hash
    against whatever was recorded, so a blank one never satisfied it either."""

    def test_absent_step_hash_is_needs_build(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", step_hash=_OMIT)
            ok, code = artifact.validate_step_freshness(d, step)
            self.assertFalse(ok)
            self.assertEqual(code, "missing_step_hash")
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_blank_step_hash_is_needs_build(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", step_hash="   ")
            self.assertEqual(
                artifact.validate_step_freshness(d, step), (False, "missing_step_hash")
            )

    def test_digest_field_is_named_per_format_not_aliased(self):
        # `stepHash` is load-bearing at a dozen cadgen sites beyond the render descriptor,
        # so it is not renamed and not aliased -- the spec table names the field per format.
        self.assertEqual(artifact._STEP_PACKAGE["source_digest_field"], "stepHash")
        self.assertEqual(artifact._DRAWING_PACKAGE["source_digest_field"], "sourceDigest")
        for spec in (artifact._STEP_PACKAGE, artifact._DRAWING_PACKAGE):
            self.assertIn(spec["missing_digest"], artifact.BUILDABLE_ARTIFACT_CODES)

    def test_generated_entry_is_unaffected_by_the_digest_gate(self):
        # sourceKind=python returns on the closure branch; a python descriptor carries no
        # stepHash by design and must stay ready.
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py")
            self.assertEqual(artifact.validate_step_freshness(root, py), (True, None))


class SchemaVersionGate(unittest.TestCase):
    """packageSchemaVersion is the stack's single invalidation channel: strict equality,
    no tolerant reader. A descriptor that does not record exactly the current version is
    unsupported (and unsupported is buildable, so it rebuilds lazily on reopen)."""

    def test_step_descriptor_without_a_schema_version_is_unsupported(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", schema_version=None)
            self.assertEqual(
                artifact.validate_step_freshness(d, step), (False, "unsupported_step_topology")
            )

    def test_step_descriptor_with_an_older_schema_version_is_unsupported(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", schema_version=_STEP_SCHEMA_VERSION - 1)
            self.assertEqual(
                artifact.validate_step_freshness(d, step), (False, "unsupported_step_topology")
            )

    def test_a_stringified_schema_version_does_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", schema_version=str(_STEP_SCHEMA_VERSION))
            self.assertEqual(
                artifact.validate_step_freshness(d, step), (False, "unsupported_step_topology")
            )

    def test_generated_step_descriptor_is_gated_too(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", schema_version=None)
            self.assertEqual(
                artifact.validate_step_freshness(root, py), (False, "unsupported_step_topology")
            )

    def test_drawing_descriptor_without_a_schema_version_is_unsupported(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", schema_version=None)
            self.assertEqual(
                artifact.validate_dxf_freshness(root, py), (False, "unsupported_dxf_artifact")
            )

    def test_drawing_descriptor_with_a_newer_schema_version_is_unsupported(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(
                root, "outline.dxf.py", schema_version=_DXF_SCHEMA_VERSION + 1
            )
            self.assertEqual(
                artifact.validate_dxf_freshness(root, py), (False, "unsupported_dxf_artifact")
            )

    def test_every_spec_row_gates_on_an_int_version(self):
        for spec in (artifact._STEP_PACKAGE, artifact._DRAWING_PACKAGE):
            self.assertIsInstance(spec["schema_version"], int)
            self.assertIn(spec["unsupported"], artifact.BUILDABLE_ARTIFACT_CODES)


class BakeHashGate(unittest.TestCase):
    """The bake block is the format settings a build froze into its payload. No other
    freshness signal can see a settings change -- source unchanged, payload present,
    closure matching -- so without this gate a stale bake renders silently."""

    def test_canonical_hash_ignores_key_order_but_not_values(self):
        self.assertEqual(
            canonical_bake_hash({"a": 1, "b": {"c": 2, "d": 3}}),
            canonical_bake_hash({"b": {"d": 3, "c": 2}, "a": 1}),
        )
        self.assertNotEqual(
            canonical_bake_hash({"widthMm": 0.42}), canonical_bake_hash({"widthMm": 0.43})
        )
        # Array order is content.
        self.assertNotEqual(canonical_bake_hash({"a": [1, 2]}), canonical_bake_hash({"a": [2, 1]}))

    def test_no_bake_settings_hashes_to_none(self):
        self.assertIsNone(canonical_bake_hash(None))

    def test_step_package_bakes_nothing_so_a_recorded_bake_is_stale(self):
        # STEP passes None (design §5.3): a descriptor carrying a bakeHash did not come
        # from this producer, and cannot be shown to match settings it no longer has.
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", bake_hash=canonical_bake_hash({"x": 1}))
            self.assertEqual(
                artifact.validate_step_freshness(d, step), (False, "stale_step_artifact")
            )

    def test_generated_step_package_with_a_recorded_bake_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", bake_hash="deadbeef")
            self.assertEqual(
                artifact.validate_step_freshness(root, py), (False, "stale_step_artifact")
            )

    def test_drawing_package_with_a_recorded_bake_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", bake_hash="deadbeef")
            self.assertEqual(
                artifact.validate_dxf_freshness(root, py), (False, "stale_dxf_artifact")
            )

    def test_a_settings_change_invalidates_every_package_of_that_format(self):
        # Drive the mechanism through the real validator by giving the STEP row a bake
        # owner, exactly as toolpath/implicit will: the SAME descriptor is ready under the
        # settings it recorded and stale under changed ones. Without this, a settings edit
        # would leave every already-built package rendering its old bake.
        settings = {"detailMode": "full", "widthMm": 0.42}
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step", bake_hash=canonical_bake_hash(settings))
            spec = dict(artifact._STEP_PACKAGE)
            spec["bake_settings"] = lambda: settings
            self.assertEqual(
                artifact._validate_render_package(
                    spec, step, artifact._step_payload_refs, d
                ),
                (True, None),
            )
            spec["bake_settings"] = lambda: {**settings, "widthMm": 0.43}
            self.assertEqual(
                artifact._validate_render_package(spec, step, artifact._step_payload_refs, d),
                (False, "stale_step_artifact"),
            )

    def test_a_baking_format_with_no_recorded_bake_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            step, _ = _write_package(d, "imp.step")
            spec = dict(artifact._STEP_PACKAGE)
            spec["bake_settings"] = lambda: {"widthMm": 0.42}
            self.assertEqual(
                artifact._validate_render_package(spec, step, artifact._step_payload_refs, d),
                (False, "stale_step_artifact"),
            )


@unittest.skipIf(
    fcntl is None,
    "these drive raw fcntl.flock, which is the POSIX backend specifically. The Windows "
    "backend's equivalent cross-process coverage lives in "
    "tests/python/packages/cadgen/test_coordination_lock.py::RealBackendRegressionTests, "
    "which runs on whatever platform it finds.",
)
class GenerationLock(unittest.TestCase):
    """The snapshot reports what the kernel says. There is no pid, heartbeat, or age to
    fake, so these drive the real fcntl states — including from a separate process,
    which is the case that actually matters."""

    def _lock_for(self, package_dir):
        from cadgen.coordination.paths import write_lock_path

        return str(write_lock_path(package_dir))

    def test_unheld_lock_is_idle(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "x.step")
            open(self._lock_for(pkg), "wb").close()
            self.assertEqual("idle", artifact.generation_snapshot(pkg).state)

    def test_never_built_artifact_is_idle(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                "idle", artifact.generation_snapshot(os.path.join(d, "never-built.step")).state
            )

    def test_reading_status_does_not_create_the_sentinel(self):
        """The old probe opened the sentinel "a+b", so merely asking for status
        materialised a lock file for an artifact that had never been built."""
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "x.step")
            artifact.generation_snapshot(pkg)
            self.assertFalse(os.path.exists(self._lock_for(pkg)))

    def test_empty_path_is_idle(self):
        self.assertEqual("idle", artifact.generation_snapshot("").state)

    def test_held_lock_reads_as_writing(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "x.step")
            handle = open(self._lock_for(pkg), "a+b")
            self.addCleanup(handle.close)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self.assertEqual("writing", artifact.generation_snapshot(pkg).state)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            self.assertEqual("idle", artifact.generation_snapshot(pkg).state)

    def test_concurrent_readers_do_not_see_a_phantom_build(self):
        """flock conflicts per open file description, so the previous LOCK_EX probe
        conflicted with OTHER PROBES: two status reads racing over an idle, fresh model
        made one of them report a build in flight (~6% with four threads)."""
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "x.step")
            open(self._lock_for(pkg), "wb").close()
            seen = []
            guard = threading.Lock()

            def worker():
                hits = sum(
                    1 for _ in range(1500) if artifact.generation_snapshot(pkg).state != "idle"
                )
                with guard:
                    seen.append(hits)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(0, sum(seen))

    def test_lock_held_by_another_process_is_writing(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "x.step")
            lp = self._lock_for(pkg)
            ready = os.path.join(d, "ready")
            code = (
                "import fcntl,os,sys,time\n"
                f"h=open({lp!r},'a+b')\n"
                "fcntl.flock(h.fileno(), fcntl.LOCK_EX)\n"
                f"open({ready!r},'wb').close()\n"
                "time.sleep(30)\n"
            )
            proc = subprocess.Popen([sys.executable, "-c", code])
            try:
                for _ in range(200):
                    if os.path.exists(ready):
                        break
                    time.sleep(0.02)
                self.assertTrue(os.path.exists(ready), "helper never acquired the lock")
                self.assertEqual("writing", artifact.generation_snapshot(pkg).state)
                # SIGKILL: no unwind, no cleanup handler. The kernel must still release.
                proc.kill()
                proc.wait(timeout=10)
                for _ in range(200):
                    if artifact.generation_snapshot(pkg).state == "idle":
                        break
                    time.sleep(0.02)
                self.assertEqual(
                    "idle",
                    artifact.generation_snapshot(pkg).state,
                    "a killed builder must leave no stale lock",
                )
            finally:
                if proc.poll() is None:
                    proc.kill()

    def test_a_dead_runs_record_is_not_shown_as_live_progress(self):
        """A SIGKILLed build leaves a non-terminal record on disk forever. Attributing it
        to whoever holds the lock NEXT is what made the viewer render "Meshing components
        31/50" for a run that had meshed nothing, then jump backwards."""
        from cadgen.coordination import record as record_mod
        from cadgen.coordination.paths import status_path

        with tempfile.TemporaryDirectory() as d:
            pkg = os.path.join(d, "x.step")
            record_mod.write_record(
                status_path(pkg),
                record_mod.build_record(
                    run_id="deadbeef",
                    kind="step-package",
                    intent="write",
                    started_at_ms=0.0,
                    outcome=None,
                    progress={"phase": "components", "done": 31, "total": 50, "ratio": 0.77},
                ),
            )
            handle = open(self._lock_for(pkg), "a+b")
            self.addCleanup(handle.close)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            snap = artifact.generation_snapshot(pkg)
            self.assertEqual("writing", snap.state)
            self.assertIsNone(snap.progress)


def _reference_closure_hash(root, relative_files):
    """Independent re-derivation of the closure digest cadgen records.

    Deliberately NOT calling server_py.source_hash: a fixture built by the module
    under test could not catch a bug in that module's digest construction. Parity
    with the real cadgen implementation is pinned separately in
    tests/python/global/test_viewer_cadgen_mirror.py.
    """
    pairs = []
    for rel in relative_files:
        path = os.path.join(root, rel)
        with open(path, "rb") as handle:
            raw = handle.read()
        if rel.endswith(".py"):
            file_hash = "ast1:" + hashlib.sha256(
                ast.dump(ast.parse(raw)).encode("utf-8")
            ).hexdigest()
        else:
            file_hash = hashlib.sha256(raw).hexdigest()
        pairs.append((rel, file_hash))
    digest = hashlib.sha256()
    for rel, file_hash in sorted(pairs):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _write_generated_package(
    root,
    py_name,
    *,
    closure_extra=None,
    with_package=True,
    closure_hash=True,
    schema_version=_STEP_SCHEMA_VERSION,
    bake_hash=None,
):
    """A gen_step generator + optionally its generated component-GLB package
    (sourceKind=python), keyed by the .step.py name like cadgen writes it."""
    py_path = os.path.join(root, py_name)
    with open(py_path, "w") as h:
        h.write("def gen_step():\n    return None\n")
    for rel in (closure_extra or []):
        with open(os.path.join(root, rel), "w") as h:
            h.write("# closure dep\n")
    if not with_package:
        return py_path, None
    pkg = os.path.join(root, "__cadgen__", "models", py_name)
    os.makedirs(os.path.join(pkg, "components"), exist_ok=True)
    with open(os.path.join(pkg, "components", "c0.glb"), "wb") as h:
        h.write(b"glTF\x02\x00\x00\x00")
    closure_files = [py_name] + list(closure_extra or [])
    descriptor = {
        "kind": "assembly-package",
        "sourceKind": "python",
        "sourcePath": py_name,
        "sourceClosureFiles": closure_files,
        "components": {"c0": {"glb": "components/c0.glb"}},
    }
    if schema_version is not None:
        descriptor["packageSchemaVersion"] = schema_version
    if bake_hash is not None:
        descriptor["bakeHash"] = bake_hash
    if closure_hash:
        descriptor["sourceClosureHash"] = _reference_closure_hash(root, closure_files)
    with open(os.path.join(pkg, "assembly.json"), "w") as h:
        json.dump(descriptor, h)
    return py_path, pkg


class GeneratedStepFreshness(unittest.TestCase):
    def test_built_generated_is_ready(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", closure_extra=["lib.py"])
            ok, code = artifact.validate_step_freshness(root, py)
            self.assertTrue(ok, code)

    def test_unbuilt_generated_is_needs_build(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", with_package=False)
            ok, code = artifact.validate_step_freshness(root, py)
            self.assertFalse(ok)
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_stale_when_closure_dep_content_changes(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", closure_extra=["lib.py"])
            with open(os.path.join(root, "lib.py"), "w") as h:
                h.write("VALUE = 2\n")
            ok, code = artifact.validate_step_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "stale_step_artifact")

    def test_touch_alone_does_not_invalidate(self):
        """The old mtime trigger fired here and forced a rebuild the CLI then
        skipped as current. Content is unchanged, so both sides say fresh."""
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", closure_extra=["lib.py"])
            time.sleep(0.01)
            os.utime(os.path.join(root, "lib.py"), None)
            os.utime(py, None)
            self.assertEqual(artifact.validate_step_freshness(root, py), (True, None))

    def test_comment_only_edit_stays_fresh(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py")
            with open(py, "w") as h:
                h.write("# a new comment\ndef gen_step():\n    return None  # trailing\n")
            self.assertEqual(artifact.validate_step_freshness(root, py), (True, None))

    def test_missing_closure_file_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", closure_extra=["lib.py"])
            os.remove(os.path.join(root, "lib.py"))
            ok, code = artifact.validate_step_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "stale_step_artifact")

    def test_descriptor_without_closure_hash_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_generated_package(root, "widget.step.py", closure_hash=False)
            ok, code = artifact.validate_step_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "stale_step_artifact")


class ScannerListsGenerated(unittest.TestCase):
    def test_unbuilt_step_py_is_collected(self):
        with tempfile.TemporaryDirectory() as root:
            py = os.path.join(root, "widget.step.py")
            with open(py, "w") as h:
                h.write("def gen_step():\n    return None\n")
            # No __cadgen__ at all — it must still be listed (built on demand).
            self.assertIn(py, scanner._collect_cad_source_files(root, []))

    def test_unbuilt_dxf_py_is_collected(self):
        with tempfile.TemporaryDirectory() as root:
            py = os.path.join(root, "outline.dxf.py")
            with open(py, "w") as h:
                h.write("def gen_dxf():\n    return None\n")
            self.assertIn(py, scanner._collect_cad_source_files(root, []))


def _write_drawing_package(
    root,
    py_name,
    *,
    closure_extra=None,
    with_package=True,
    kind="drawing-package",
    closure_hash=True,
    schema_version=_DXF_SCHEMA_VERSION,
    bake_hash=_OMIT,
    preview=True,
):
    """A gen_dxf generator + optionally its drawing package, keyed by the
    .dxf.py name like cadgen writes it. The package carries its ONE payload: the baked
    preview.glb the viewport renders."""
    py_path = os.path.join(root, py_name)
    with open(py_path, "w") as h:
        h.write("def gen_dxf():\n    return None\n")
    for rel in (closure_extra or []):
        with open(os.path.join(root, rel), "w") as h:
            h.write("# closure dep\n")
    if not with_package:
        return py_path, None
    pkg = os.path.join(root, "__cadgen__", "models", py_name)
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "preview.glb"), "wb") as h:
        h.write(b"glTF\x02\x00\x00\x00")
    with open(os.path.join(pkg, "geometry.json"), "w") as h:
        h.write("{}")
    closure_files = [py_name] + list(closure_extra or [])
    descriptor = {
        "kind": kind,
        "sourceKind": "python",
        "sourcePath": py_name,
        "sourceHash": "abc123",
        "geometry": "geometry.json",
        "sourceClosureFiles": closure_files,
    }
    if preview:
        descriptor["preview"] = "preview.glb"
    if schema_version is not None:
        descriptor["packageSchemaVersion"] = schema_version
    descriptor["bakeHash"] = (
        canonical_bake_hash(drawing_preview_bake_settings()) if bake_hash is _OMIT else bake_hash
    )
    if descriptor["bakeHash"] is None:
        del descriptor["bakeHash"]
    if closure_hash:
        descriptor["sourceClosureHash"] = _reference_closure_hash(root, closure_files)
    with open(os.path.join(pkg, "drawing.json"), "w") as h:
        json.dump(descriptor, h)
    return py_path, pkg


def _write_imported_drawing_package(root, dxf_name, *, source_digest=True, preview=True):
    """An imported .dxf + its package. Same payloads, imported provenance -- a plain content
    digest of the file rather than a source closure, exactly like an imported .step."""
    dxf_path = os.path.join(root, dxf_name)
    with open(dxf_path, "w") as h:
        h.write("0\nSECTION\n0\nEOF\n")
    with open(dxf_path, "rb") as h:
        digest = hashlib.sha256(h.read()).hexdigest()
    pkg = os.path.join(root, "__cadgen__", "models", dxf_name)
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "preview.glb"), "wb") as h:
        h.write(b"glTF\x02\x00\x00\x00")
    with open(os.path.join(pkg, "geometry.json"), "w") as h:
        h.write("{}")
    descriptor = {
        "kind": "drawing-package",
        "packageSchemaVersion": _DXF_SCHEMA_VERSION,
        "sourceKind": "dxf",
        "sourcePath": dxf_name,
        "dxf": "drawing.dxf",
        "dxfHash": digest,
        "geometry": "geometry.json",
        "bakeHash": canonical_bake_hash(drawing_preview_bake_settings()),
    }
    if preview:
        descriptor["preview"] = "preview.glb"
    if source_digest:
        descriptor["sourceDigest"] = digest
    with open(os.path.join(pkg, "drawing.json"), "w") as h:
        json.dump(descriptor, h)
    return dxf_path, pkg


class OwnsDxfEntry(unittest.TestCase):
    def test_both_dxf_inputs_are_owned(self):
        self.assertTrue(artifact.owns_entry({"file": "/x/outline.dxf.py"}))
        self.assertTrue(artifact.owns_dxf_entry({"file": "/x/outline.DXF.PY"}))
        # An imported .dxf is artifact-managed too: the package's preview.glb is the only
        # 3D DXF renderer there is, so it needs a build for the same reason an imported
        # .step does (design §0.1, §5.5).
        self.assertTrue(artifact.owns_entry({"file": "/x/outline.dxf"}))
        self.assertTrue(artifact.owns_dxf_entry({"file": "/x/OUTLINE.DXF"}))
        self.assertFalse(artifact.owns_dxf_entry({"file": "/x/a.step.py"}))
        self.assertFalse(artifact.owns_dxf_entry({"file": "/x/notes.dxf.txt"}))
        self.assertFalse(artifact.owns_dxf_entry(None))


class GeneratedDxfFreshness(unittest.TestCase):
    def test_built_drawing_is_ready(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", closure_extra=["lib.py"])
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertTrue(ok, code)

    def test_unbuilt_drawing_is_needs_build(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", with_package=False)
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "missing_dxf_artifact")
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_missing_preview_glb_is_buildable(self):
        # The package's ONE payload. A missing GLB has to read as needs-build here, or the
        # request settles `ready` and the viewer renders nothing with no explanation
        # (design §4.7).
        with tempfile.TemporaryDirectory() as root:
            py, pkg = _write_drawing_package(root, "outline.dxf.py")
            os.remove(os.path.join(pkg, "preview.glb"))
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "missing_dxf_artifact")
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_descriptor_that_names_no_preview_is_buildable(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", preview=False)
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "missing_dxf_artifact")

    def test_drawing_payload_refs_names_the_render_artifacts(self):
        # The GLB and the parsed contours the curved-bend remesh reads. A cached
        # `drawing.dxf` is still not a payload: an imported drawing's DXF is the user's own
        # file, and a generated one is exported on demand.
        self.assertEqual(
            ["preview.glb", "geometry.json"],
            artifact._drawing_payload_refs({
                "dxf": "drawing.dxf",
                "preview": "preview.glb",
                "geometry": "geometry.json",
            }),
        )

    def test_a_changed_bake_format_makes_every_drawing_stale(self):
        # The other half of cadgen's own package-freshness pin:
        # the SAME callable owns the bake on both sides, so an edit to the producer's
        # settings invalidates packages here too instead of rendering an old bake silently.
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py")
            self.assertEqual(artifact.validate_dxf_freshness(root, py), (True, None))
            with mock.patch.object(
                _drawing_package, "DRAWING_PREVIEW_BAKE_FORMAT", "dxf-preview-glb-vNEXT"
            ):
                self.assertEqual(
                    artifact.validate_dxf_freshness(root, py), (False, "stale_dxf_artifact")
                )

    def test_the_two_authorities_agree_on_the_same_package(self):
        # A check one side makes and the other does not is a SILENT failure: the producer
        # reports skipped, the request settles ready, and the stale package renders.
        with tempfile.TemporaryDirectory() as root:
            py, pkg = _write_drawing_package(root, "outline.dxf.py")
            self.assertEqual(artifact.validate_dxf_freshness(root, py), (True, None))
            self.assertTrue(_drawing_package.drawing_package_current(pathlib.Path(py)))
            os.remove(os.path.join(pkg, "preview.glb"))
            self.assertFalse(artifact.validate_dxf_freshness(root, py)[0])
            self.assertFalse(_drawing_package.drawing_package_current(pathlib.Path(py)))

    def test_unsupported_descriptor(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", kind="something-else")
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "unsupported_dxf_artifact")

    def test_stale_when_closure_dep_content_changes(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", closure_extra=["lib.py"])
            with open(os.path.join(root, "lib.py"), "w") as h:
                h.write("VALUE = 2\n")
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "stale_dxf_artifact")

    def test_stale_when_source_content_changes(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py")
            with open(py, "w") as h:
                h.write("def gen_dxf():\n    return 'changed'\n")
            ok, code = artifact.validate_dxf_freshness(root, py)
            self.assertFalse(ok)
            self.assertEqual(code, "stale_dxf_artifact")

    def test_touch_alone_does_not_invalidate(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", closure_extra=["lib.py"])
            time.sleep(0.01)
            os.utime(os.path.join(root, "lib.py"), None)
            os.utime(py, None)
            self.assertEqual(artifact.validate_dxf_freshness(root, py), (True, None))

    def test_comment_only_edit_stays_fresh(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py")
            with open(py, "w") as h:
                h.write("# new comment\ndef gen_dxf():\n    return None\n")
            self.assertEqual(artifact.validate_dxf_freshness(root, py), (True, None))


class GeneratedPackageParity(unittest.TestCase):
    """The two formats must answer identically-shaped questions identically. The
    no-closure case used to disagree: STEP returned fresh, DXF returned stale."""

    def test_descriptor_without_closure_hash_is_stale_for_both(self):
        with tempfile.TemporaryDirectory() as root:
            step_py, _ = _write_generated_package(root, "widget.step.py", closure_hash=False)
            dxf_py, _ = _write_drawing_package(root, "outline.dxf.py", closure_hash=False)
            step_ok, step_code = artifact.validate_step_freshness(root, step_py)
            dxf_ok, dxf_code = artifact.validate_dxf_freshness(root, dxf_py)
            self.assertEqual((step_ok, dxf_ok), (False, False))
            self.assertEqual(step_code, "stale_step_artifact")
            self.assertEqual(dxf_code, "stale_dxf_artifact")

    def test_touch_is_fresh_for_both_and_content_change_is_stale_for_both(self):
        with tempfile.TemporaryDirectory() as root:
            step_py, _ = _write_generated_package(root, "widget.step.py")
            dxf_py, _ = _write_drawing_package(root, "outline.dxf.py")
            time.sleep(0.01)
            os.utime(step_py, None)
            os.utime(dxf_py, None)
            self.assertTrue(artifact.validate_step_freshness(root, step_py)[0])
            self.assertTrue(artifact.validate_dxf_freshness(root, dxf_py)[0])
            for path, body in ((step_py, "def gen_step():\n    return 1\n"),
                               (dxf_py, "def gen_dxf():\n    return 1\n")):
                with open(path, "w") as h:
                    h.write(body)
            self.assertFalse(artifact.validate_step_freshness(root, step_py)[0])
            self.assertFalse(artifact.validate_dxf_freshness(root, dxf_py)[0])

    def test_deleted_generator_is_missing_source_path_for_both(self):
        with tempfile.TemporaryDirectory() as root:
            step_py, _ = _write_generated_package(root, "widget.step.py")
            dxf_py, _ = _write_drawing_package(root, "outline.dxf.py")
            os.remove(step_py)
            os.remove(dxf_py)
            self.assertEqual(artifact.validate_step_freshness(root, step_py), (False, "missing_source_path"))
            self.assertEqual(artifact.validate_dxf_freshness(root, dxf_py), (False, "missing_source_path"))


class ScannerDxfEntry(unittest.TestCase):
    def test_built_drawing_entry_has_no_static_dxf_asset(self):
        with tempfile.TemporaryDirectory() as root:
            py, pkg = _write_drawing_package(root, "outline.dxf.py")
            entry = scanner.create_generated_dxf_entry(root, root, py)
            self.assertEqual(entry["kind"], "dxf")
            self.assertEqual(entry["file"], "outline.dxf.py")
            self.assertEqual(entry["sourceKind"], "python")
            # No static asset: the cache holds no DXF, so a download regenerates through the
            # export route rather than linking a file.
            self.assertEqual("", entry["url"])
            self.assertEqual("abc123", entry["hash"])
            self.assertEqual(entry["source"]["sourceHash"], "abc123")

    def test_unbuilt_drawing_entry_has_no_asset(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py", with_package=False)
            entry = scanner.create_generated_dxf_entry(root, root, py)
            self.assertEqual(entry["kind"], "dxf")
            self.assertEqual(entry["url"], "")
            self.assertEqual(entry["hash"], "")

    def test_scan_directory_lists_generated_and_raw_dxf(self):
        with tempfile.TemporaryDirectory() as root:
            _write_drawing_package(root, "outline.dxf.py")
            with open(os.path.join(root, "imported.dxf"), "w") as h:
                h.write("0\nEOF\n")
            catalog = scanner.scan_cad_directory(root, include_artifact_status=False)
            by_file = {entry["file"]: entry for entry in catalog["entries"]}
            self.assertIn("outline.dxf.py", by_file)
            self.assertIn("imported.dxf", by_file)
            self.assertEqual(by_file["outline.dxf.py"]["kind"], "dxf")
            self.assertEqual(by_file["outline.dxf.py"].get("sourceKind"), "python")
            self.assertEqual(by_file["imported.dxf"]["kind"], "dxf")
            self.assertNotIn("sourceKind", by_file["imported.dxf"])



class ImportedDxfFreshness(unittest.TestCase):
    """An imported .dxf is artifact-managed exactly like an imported .step: same package,
    same validator, imported provenance."""

    def test_built_imported_drawing_is_ready(self):
        with tempfile.TemporaryDirectory() as root:
            dxf, _ = _write_imported_drawing_package(root, "vendor.dxf")
            self.assertEqual(artifact.validate_dxf_freshness(root, dxf), (True, None))

    def test_unbuilt_imported_drawing_is_needs_build(self):
        with tempfile.TemporaryDirectory() as root:
            dxf = os.path.join(root, "vendor.dxf")
            with open(dxf, "w") as h:
                h.write("0\nEOF\n")
            ok, code = artifact.validate_dxf_freshness(root, dxf)
            self.assertFalse(ok)
            self.assertEqual(code, "missing_dxf_artifact")
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_edited_imported_drawing_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            dxf, _ = _write_imported_drawing_package(root, "vendor.dxf")
            with open(dxf, "a") as h:
                h.write("999\nchanged\n")
            self.assertEqual(
                artifact.validate_dxf_freshness(root, dxf), (False, "stale_dxf_artifact")
            )

    def test_descriptor_with_no_digest_fails_closed(self):
        # The imported branch must never answer `ready` on a descriptor that cannot be
        # shown to match the file sitting right there.
        with tempfile.TemporaryDirectory() as root:
            dxf, _ = _write_imported_drawing_package(root, "vendor.dxf", source_digest=False)
            self.assertEqual(
                artifact.validate_dxf_freshness(root, dxf), (False, "stale_dxf_artifact")
            )

    def test_missing_preview_glb_is_buildable_for_an_import_too(self):
        with tempfile.TemporaryDirectory() as root:
            dxf, pkg = _write_imported_drawing_package(root, "vendor.dxf")
            os.remove(os.path.join(pkg, "preview.glb"))
            self.assertEqual(
                artifact.validate_dxf_freshness(root, dxf), (False, "missing_dxf_artifact")
            )

    def test_both_authorities_agree_about_an_import(self):
        with tempfile.TemporaryDirectory() as root:
            dxf, _ = _write_imported_drawing_package(root, "vendor.dxf")
            self.assertTrue(artifact.validate_dxf_freshness(root, dxf)[0])
            self.assertTrue(_drawing_package.drawing_package_current(pathlib.Path(dxf)))
            with open(dxf, "a") as h:
                h.write("999\nchanged\n")
            self.assertFalse(artifact.validate_dxf_freshness(root, dxf)[0])
            self.assertFalse(_drawing_package.drawing_package_current(pathlib.Path(dxf)))


def _write_implicit_package(
    root,
    source_name,
    *,
    with_package=True,
    kind="implicit-package",
    schema_version=_IMPLICIT_SCHEMA_VERSION,
    bake_hash=_OMIT,
    glb=True,
    closure_hash=True,
    closure_extra=None,
):
    """An `.implicit.js` model + optionally its baked render package.

    An implicit model is a GENERATED entry whose generator happens to be JavaScript: the
    descriptor records sourceKind "python" (the validator's generated-vs-imported
    discriminator, not a claim about the language) and a source closure over the `.js`
    files the model actually loaded."""
    source_path = os.path.join(root, source_name)
    with open(source_path, "w") as h:
        h.write("export const model = { sdf: 'return length(p) - 1.0;' };\n")
    for rel in (closure_extra or []):
        with open(os.path.join(root, rel), "w") as h:
            h.write("// closure dep\n")
    if not with_package:
        return source_path, None
    pkg = os.path.join(root, "__cadgen__", "models", source_name)
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "model.glb"), "wb") as h:
        h.write(b"glTF\x02\x00\x00\x00")
    closure_files = [source_name] + list(closure_extra or [])
    descriptor = {
        "kind": kind,
        "sourceKind": "python",
        "sourceLanguage": "javascript",
        "sourcePath": source_name,
        "sourceClosureFiles": closure_files,
    }
    if glb:
        descriptor["glb"] = "model.glb"
    if schema_version is not None:
        descriptor["packageSchemaVersion"] = schema_version
    descriptor["bakeHash"] = (
        canonical_bake_hash(implicit_bake_settings()) if bake_hash is _OMIT else bake_hash
    )
    if descriptor["bakeHash"] is None:
        del descriptor["bakeHash"]
    if closure_hash:
        descriptor["sourceClosureHash"] = _reference_closure_hash(root, closure_files)
    with open(os.path.join(pkg, "implicit.json"), "w") as h:
        json.dump(descriptor, h)
    return source_path, pkg


class OwnsImplicitEntry(unittest.TestCase):
    def test_implicit_sources_are_owned(self):
        self.assertTrue(artifact.owns_entry({"file": "/x/gyroid.implicit.js"}))
        self.assertTrue(artifact.owns_implicit_entry({"file": "/x/gyroid.implicit.mjs"}))
        self.assertTrue(artifact.owns_implicit_entry({"file": "/x/Gyroid.IMPLICIT.JS"}))
        self.assertFalse(artifact.owns_implicit_entry({"file": "/x/params.js"}))
        self.assertFalse(artifact.owns_implicit_entry({"file": "/x/a.step"}))
        self.assertFalse(artifact.owns_implicit_entry(None))

    def test_the_owned_suffixes_come_from_the_producer(self):
        # Imported, not hand-copied: the set of sources the viewer asks to build cannot
        # drift from the set the builder accepts.
        self.assertEqual(artifact.IMPLICIT_SUFFIXES, _implicit_package.IMPLICIT_SUFFIXES)


class ImplicitFreshness(unittest.TestCase):
    def test_built_package_is_ready(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", closure_extra=["lib.js"])
            ok, code = artifact.validate_implicit_freshness(root, src)
            self.assertTrue(ok, code)

    def test_unbuilt_package_is_needs_build(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", with_package=False)
            ok, code = artifact.validate_implicit_freshness(root, src)
            self.assertFalse(ok)
            self.assertEqual(code, "missing_implicit_artifact")
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_missing_model_glb_is_buildable(self):
        with tempfile.TemporaryDirectory() as root:
            src, pkg = _write_implicit_package(root, "gyroid.implicit.js")
            os.remove(os.path.join(pkg, "model.glb"))
            self.assertEqual(
                artifact.validate_implicit_freshness(root, src),
                (False, "missing_implicit_artifact"),
            )

    def test_descriptor_that_names_no_glb_is_buildable(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", glb=False)
            self.assertEqual(
                artifact.validate_implicit_freshness(root, src),
                (False, "missing_implicit_artifact"),
            )

    def test_unsupported_descriptor(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", kind="something-else")
            self.assertEqual(
                artifact.validate_implicit_freshness(root, src),
                (False, "unsupported_implicit_artifact"),
            )

    def test_schema_version_is_gated_strictly(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", schema_version=None)
            self.assertEqual(
                artifact.validate_implicit_freshness(root, src),
                (False, "unsupported_implicit_artifact"),
            )

    def test_a_changed_bake_resolution_makes_every_package_stale(self):
        # The bake IS the artifact: a resolution change is invisible to every other
        # freshness signal, so without this gate a stale mesh renders silently.
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js")
            self.assertTrue(artifact.validate_implicit_freshness(root, src)[0])
            with mock.patch.object(
                _implicit_package, "DEFAULT_BAKE_RESOLUTION", 128, create=False
            ):
                self.assertEqual(
                    artifact.validate_implicit_freshness(root, src),
                    (False, "stale_implicit_artifact"),
                )

    def test_stale_when_closure_dep_content_changes(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", closure_extra=["lib.js"])
            with open(os.path.join(root, "lib.js"), "w") as h:
                h.write("// different\nexport const k = 2;\n")
            self.assertEqual(
                artifact.validate_implicit_freshness(root, src),
                (False, "stale_implicit_artifact"),
            )

    def test_the_two_authorities_agree_on_the_same_package(self):
        # The viewer's validator and the producer's currency gate must reach the same
        # verdict, or a stale package either renders silently or rebuilds forever.
        with tempfile.TemporaryDirectory() as root:
            src, pkg = _write_implicit_package(root, "gyroid.implicit.js")
            self.assertTrue(artifact.validate_implicit_freshness(root, src)[0])
            self.assertTrue(_implicit_package.implicit_package_current(pathlib.Path(src)))
            os.remove(os.path.join(pkg, "model.glb"))
            self.assertFalse(artifact.validate_implicit_freshness(root, src)[0])
            self.assertFalse(_implicit_package.implicit_package_current(pathlib.Path(src)))

    def test_spec_row_matches_the_producer(self):
        spec = artifact._IMPLICIT_PACKAGE
        self.assertEqual(spec["descriptor"], _implicit_package.IMPLICIT_DESCRIPTOR_NAME)
        self.assertEqual(spec["package_kind"], _implicit_package.IMPLICIT_PACKAGE_KIND)
        self.assertEqual(
            spec["schema_version"], _implicit_package.IMPLICIT_PACKAGE_SCHEMA_VERSION
        )
        self.assertIs(spec["bake_settings"], _implicit_package.implicit_bake_settings)
        self.assertIsInstance(spec["schema_version"], int)
        for code in (spec["missing"], spec["unsupported"], spec["stale"], spec["missing_digest"]):
            self.assertIn(code, artifact.BUILDABLE_ARTIFACT_CODES)

    def test_payload_refs_names_the_baked_mesh(self):
        self.assertEqual(artifact._implicit_payload_refs({"glb": "model.glb"}), ["model.glb"])


class ScannerPublishesPackageGlb(unittest.TestCase):
    """An entry with no renderable geometry of its own publishes its package's baked GLB as
    a `glb` relation, so the client resolves it through the ordinary mesh-asset path."""

    def test_implicit_entry_publishes_the_baked_mesh(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js")
            entry = scanner.create_single_asset_entry(root, root, src, ".js")
            self.assertEqual(entry["kind"], "implicit")
            relation = entry["relations"]["glb"]
            self.assertIn("__cadgen__/models/gyroid.implicit.js/model.glb", relation["url"])
            self.assertEqual(relation["file"], "__cadgen__/models/gyroid.implicit.js/model.glb")
            self.assertTrue(relation["hash"])
            self.assertEqual(relation["bytes"], 8)

    def test_unbuilt_implicit_entry_publishes_no_mesh(self):
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js", with_package=False)
            entry = scanner.create_single_asset_entry(root, root, src, ".js")
            self.assertNotIn("relations", entry)

    def test_generated_drawing_entry_publishes_its_preview(self):
        with tempfile.TemporaryDirectory() as root:
            py, _ = _write_drawing_package(root, "outline.dxf.py")
            entry = scanner.create_generated_dxf_entry(root, root, py)
            relation = entry["relations"]["glb"]
            self.assertIn("__cadgen__/models/outline.dxf.py/preview.glb", relation["url"])

    def test_imported_drawing_entry_publishes_its_preview(self):
        with tempfile.TemporaryDirectory() as root:
            dxf, _ = _write_imported_drawing_package(root, "vendor.dxf")
            entry = scanner.create_single_asset_entry(root, root, dxf, ".dxf")
            relation = entry["relations"]["glb"]
            self.assertIn("__cadgen__/models/vendor.dxf/preview.glb", relation["url"])

    def test_the_asset_dir_is_unresolved_while_the_lock_dir_is_resolved(self):
        # Two derivations of one directory, deliberately (design §8). The lock sentinel
        # must be realpath'd so two paths reaching one package exclude each other; an asset
        # URL must NOT be, because a realpath that leaves the scan root yields a URL that
        # escapes it. macOS's /var -> /private/var makes this reachable from a tmpdir.
        with tempfile.TemporaryDirectory() as root:
            src, _ = _write_implicit_package(root, "gyroid.implicit.js")
            asset_dir = scanner.render_package_asset_dir(src)
            self.assertTrue(asset_dir.startswith(os.path.abspath(root) + os.sep))
            self.assertEqual(
                scanner.render_package_dir(src), os.path.realpath(asset_dir)
            )

    def test_scan_directory_lists_an_implicit_model_with_its_mesh(self):
        with tempfile.TemporaryDirectory() as root:
            _write_implicit_package(root, "gyroid.implicit.js")
            catalog = scanner.scan_cad_directory(root, include_artifact_status=False)
            by_file = {entry["file"]: entry for entry in catalog["entries"]}
            self.assertIn("gyroid.implicit.js", by_file)
            self.assertEqual(by_file["gyroid.implicit.js"]["kind"], "implicit")
            self.assertIn("glb", by_file["gyroid.implicit.js"]["relations"])


class ArtifactFormatDispatchIsTotal(unittest.TestCase):
    """`_artifact_format` must be a total predicate->record table, not an if/else that falls
    through to STEP. A half-wired format answering as STEP would validate an assembly.json
    that does not exist, report `ready` for the missing-source code, and never build."""

    def setUp(self):
        from server_py import backend as backend_mod

        self.backend = backend_mod.LocalAssetBackend()

    def test_each_owned_kind_selects_its_own_producer(self):
        cases = {
            "/x/outline.dxf.py": ("validate_dxf_freshness", "generate_dxf_artifact"),
            "/x/vendor.dxf": ("validate_dxf_freshness", "generate_dxf_artifact"),
            "/x/gyroid.implicit.js": ("validate_implicit_freshness", "generate_implicit_artifact"),
            "/x/part.step": ("validate_step_freshness", "generate_step_artifact"),
            "/x/part.step.py": ("validate_step_freshness", "generate_step_artifact"),
        }
        for file_ref, (validate_name, build_name) in cases.items():
            with self.subTest(file=file_ref):
                fmt = self.backend._artifact_format({"file": file_ref})
                self.assertIs(fmt["validate"], getattr(artifact, validate_name))
                self.assertEqual(fmt["build"].__name__, build_name)

    def test_an_unowned_entry_raises_instead_of_answering_as_step(self):
        for entry in ({"file": "/x/mesh.stl"}, {"file": "/x/toolpath.gcode"}, None):
            with self.subTest(entry=entry):
                self.assertFalse(artifact.owns_entry(entry))
                with self.assertRaises(ValueError):
                    self.backend._artifact_format(entry)

    def test_every_producer_the_backend_shells_out_to_is_worker_dispatchable(self):
        # The warm worker keeps its own module allowlist; a producer missing from it fails at
        # RUNTIME with "Unknown cadgen module for worker", which no unit test of either side
        # alone would catch.
        from server_py import worker

        dispatch = worker._module_dispatch()
        for module in (
            "cadgen.step_artifact_cli",
            "cadgen.dxf_artifact",
            "cadgen.implicit_artifact",
            "cadgen.step_export_target",
            "cadgen.implicit_export",
        ):
            with self.subTest(module=module):
                self.assertIn(module, dispatch)
                # The worker calls run(args, reset_runtime_closure=True) on every one.
                self.assertIn(
                    "reset_runtime_closure",
                    inspect.signature(dispatch[module]).parameters,
                )


if __name__ == "__main__":
    unittest.main()


class DrawingProfileGate(unittest.TestCase):
    """A dimensioned drawing bakes no prism, and must not be chased for one (issue #246)."""

    def test_a_drawing_package_without_a_bake_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "workshop.dxf.py")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("def gen_dxf():\n    raise NotImplementedError\n")
            package = os.path.join(directory, "__cadgen__", "models", "workshop.dxf.py")
            os.makedirs(package, exist_ok=True)
            with open(os.path.join(package, "geometry.json"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            closure = _closure_for(source, directory)
            _dump(os.path.join(package, "drawing.json"), {
                "kind": "drawing-package",
                "packageSchemaVersion": DXF_PACKAGE_SCHEMA_VERSION,
                "profile": "drawing",
                "sourceKind": "python",
                "sourcePath": "workshop.dxf.py",
                "geometry": "geometry.json",
                "sourceClosureHash": closure.closure_hash,
                "sourceClosureFiles": list(closure.files),
            })
            self.assertEqual((True, None), artifact.validate_dxf_freshness(directory, source))

    def test_a_drawing_package_that_claims_a_bake_is_still_stale(self) -> None:
        # The exemption is "records no bake", not "drawings skip the gate": a bakeHash on a
        # package that baked nothing is a claim about a payload that does not exist.
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "workshop.dxf.py")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("def gen_dxf():\n    raise NotImplementedError\n")
            package = os.path.join(directory, "__cadgen__", "models", "workshop.dxf.py")
            os.makedirs(package, exist_ok=True)
            with open(os.path.join(package, "geometry.json"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            closure = _closure_for(source, directory)
            _dump(os.path.join(package, "drawing.json"), {
                "kind": "drawing-package",
                "packageSchemaVersion": DXF_PACKAGE_SCHEMA_VERSION,
                "profile": "drawing",
                "sourceKind": "python",
                "sourcePath": "workshop.dxf.py",
                "geometry": "geometry.json",
                "bakeHash": "deadbeef",
                "sourceClosureHash": closure.closure_hash,
                "sourceClosureFiles": list(closure.files),
            })
            self.assertEqual(
                (False, "stale_dxf_artifact"),
                artifact.validate_dxf_freshness(directory, source),
            )
