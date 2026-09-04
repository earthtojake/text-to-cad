"""The viewer's import: a compile job in the pool, de-duplicated, errors as values.

The private compile pool is gone; ``ImportCompiler`` submits ``submit_compile``
jobs and waits. Driven by a fake ``submit`` so the outcomes are deterministic
and fast: what these cover is the waiter's behaviour — one job per document,
attached requests sharing the answer, a failed job's bare message — and the
ops wiring around it. The pool's own behaviour (slots, coalescing, spares) has
its own suites.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cadgen.viewer.backend import ForbiddenAssetError
from cadgen.viewer.cadgen_ops import CadgenOps
from cadgen.viewer.imports import ImportCompiler


class _FakeJob:
    def __init__(self, code: int = 0, output: str = "", gate: threading.Event | None = None) -> None:
        self.code, self._output, self.gate = code, output, gate

    def wait(self, timeout=None) -> int:
        if self.gate is not None:
            self.gate.wait(timeout)
        return self.code

    def output(self) -> str:
        return self._output


class _FakeSubmit:
    """Records every submit; answers per document name."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, bool]] = []
        self.lock = threading.Lock()
        self.gate: threading.Event | None = None

    def __call__(self, document: Path, *, force: bool = False) -> _FakeJob:
        with self.lock:
            self.calls.append((Path(document), bool(force)))
        name = Path(document).name
        if name.startswith("crash"):
            return _FakeJob(
                1,
                "Traceback (most recent call last):\n  ...\n"
                "RuntimeError: failed to read STEP file: not a STEP\n",
            )
        if name.startswith("mumble"):
            return _FakeJob(2, "the worker said something\nand then died\n")
        if name.startswith("silent"):
            return _FakeJob(3, "")
        if name.startswith("slow"):
            return _FakeJob(0, "", gate=self.gate)
        return _FakeJob(0, "")


class ImportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name, "models")
        self.root.mkdir()
        self.cache = Path(self.tmp.name, "cache")
        self._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = str(self.cache)
        self.addCleanup(self._restore_cache)
        self.submit = _FakeSubmit()

    def _restore_cache(self) -> None:
        if self._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._previous_cache

    def compiler(self) -> ImportCompiler:
        return ImportCompiler(submit=self.submit)

    def ops(self) -> CadgenOps:
        return CadgenOps(str(self.root), client=self.compiler())

    def step(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(f"ISO-10303-21;{name}".encode())
        return str(path)


class ResultsAndErrorsAreValues(ImportTestCase):
    def test_a_successful_compile_answers_with_the_document(self):
        candidate = self.step("ok.step")
        result = self.compiler().compile(candidate)
        self.assertEqual(result, {"ok": True, "document": str(Path(candidate).resolve())})
        self.assertEqual(self.submit.calls, [(Path(candidate).resolve(), False)])

    def test_force_reaches_the_job(self):
        candidate = self.step("ok.step")
        self.compiler().compile(candidate, force=True)
        self.assertEqual(self.submit.calls[0][1], True)

    def test_a_failed_job_answers_with_the_bare_message_and_the_class_apart(self):
        result = self.compiler().compile(self.step("crash.step"))
        self.assertEqual(
            result,
            {"ok": False, "error": "failed to read STEP file: not a STEP", "errorType": "RuntimeError"},
        )

    def test_a_failure_without_an_exception_line_keeps_the_last_thing_said(self):
        result = self.compiler().compile(self.step("mumble.step"))
        self.assertEqual(result, {"ok": False, "error": "and then died"})

    def test_a_silent_failure_still_names_the_document(self):
        result = self.compiler().compile(self.step("silent.step"))
        self.assertEqual(result, {"ok": False, "error": "compiling silent.step failed"})


class Deduplication(ImportTestCase):
    def test_concurrent_requests_for_one_document_are_one_job_with_one_answer(self):
        candidate = self.step("slow.step")
        self.submit.gate = threading.Event()
        compiler = self.compiler()
        results: list[dict] = []

        def request() -> None:
            results.append(compiler.compile(candidate))

        threads = [threading.Thread(target=request) for _ in range(8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not compiler.in_flight(_scope(candidate)):
            time.sleep(0.01)
        self.assertTrue(compiler.in_flight(_scope(candidate)))
        self.submit.gate.set()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(len(self.submit.calls), 1, "one document, one job")
        self.assertEqual(len(results), 8)
        self.assertEqual(set(json.dumps(r, sort_keys=True) for r in results), {json.dumps(results[0], sort_keys=True)})
        self.assertFalse(compiler.in_flight(_scope(candidate)))

    def test_two_documents_are_two_jobs(self):
        compiler = self.compiler()
        compiler.compile(self.step("a.step"))
        compiler.compile(self.step("b.step"))
        self.assertEqual(len(self.submit.calls), 2)


def _scope(candidate: str) -> str:
    from cadgen.viewer.store_paths import build_scope

    return build_scope(candidate)


class OpsWiring(ImportTestCase):
    def test_an_unowned_entry_is_ready_without_a_job(self):
        ops = self.ops()
        self.assertEqual(ops.artifact_status("model.stl"), {"state": "ready"})
        self.assertEqual(ops.build_artifact("model.stl"), {"ok": True, "state": "ready"})
        self.assertEqual(self.submit.calls, [])

    def test_a_foreign_step_is_offered_as_an_import_with_exactly_three_keys(self):
        # No `blocked`: it is set from a `busy` snapshot no producer can emit, and an
        # unreachable flag that flips the client from BUILD to ATTACH is a trap.
        ops = self.ops()
        self.step("ok.step")
        self.assertEqual(
            ops.artifact_status("ok.step"),
            {"state": "needs-build", "reason": "missing_glb", "stepImport": True},
        )

    def test_a_successful_import_is_ready_and_spreads_the_job_answer(self):
        ops = self.ops()
        candidate = self.step("ok.step")
        result = ops.build_artifact("ok.step")
        self.assertEqual(
            result,
            {"ok": True, "state": "ready", "stepImport": True, "document": str(Path(candidate).resolve())},
        )
        self.assertNotIn("contended", result)

    def test_a_failed_import_is_a_500_shaped_payload_with_the_bare_message(self):
        ops = self.ops()
        self.step("crash.step")
        result = ops.build_artifact("crash.step")
        self.assertEqual(
            result,
            {
                "ok": False,
                "state": "error",
                "error": "STEP import failed: failed to read STEP file: not a STEP",
                "errorType": "RuntimeError",
            },
        )

    def test_an_in_flight_import_with_no_progress_record_yet_is_indeterminate_generating(self):
        ops = self.ops()
        self.step("slow.step")
        self.submit.gate = threading.Event()
        thread = threading.Thread(target=lambda: ops.build_artifact("slow.step"))
        thread.start()
        try:
            deadline = time.monotonic() + 5
            status = None
            while time.monotonic() < deadline:
                status = ops.artifact_status("slow.step")
                if status.get("state") == "generating":
                    break
                time.sleep(0.02)
            self.assertEqual((status or {}).get("state"), "generating", status)
        finally:
            self.submit.gate.set()
            thread.join(timeout=5)


class ContainmentHappensBeforeTheJob(ImportTestCase):
    def test_an_absolute_outside_ref_never_reaches_the_pool(self):
        outside = Path(self.tmp.name, "outside.step")
        outside.write_bytes(b"ISO-10303-21;outside")
        ops = self.ops()
        with self.assertRaises(ForbiddenAssetError):
            ops.build_artifact(str(outside))
        self.assertEqual(self.submit.calls, [])

    def test_a_relative_ref_that_walks_out_never_reaches_the_pool(self):
        ops = self.ops()
        with self.assertRaises(ForbiddenAssetError):
            ops.build_artifact("../outside.step")
        self.assertEqual(self.submit.calls, [])

    def test_an_absolute_in_root_ref_is_still_compiled(self):
        ops = self.ops()
        candidate = self.step("inside.step")
        self.assertTrue(ops.build_artifact(candidate)["ok"])
        self.assertEqual(len(self.submit.calls), 1)


if __name__ == "__main__":
    unittest.main()
