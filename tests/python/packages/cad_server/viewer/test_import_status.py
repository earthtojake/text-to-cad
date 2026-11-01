"""The viewer's engine-document route while the engine imports a STEP (``cad_server.viewer.documents``):
its 202 carries the import's last frame, and a held request comes back as soon as the frame moves,
so a page asking again shows each stage as it comes rather than one word for the whole wait."""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

from cad_server.viewer.documents import EngineDocuments


class _ImportingEngine:
    """An engine whose ``add`` runs until released, saying its import's frames meanwhile (``build_of``)."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.state: dict = {"building": None, "failed": None, "progress": 0}

    def add(self, path: Path) -> str:
        assert self.release.wait(30), "the test never released the import"
        return "doc-1"

    def holds(self, ident: str) -> bool:
        return False

    def build_of(self, ident: str) -> dict:
        with self.lock:
            return dict(self.state)

    def say(self, frame: dict | None) -> None:
        with self.lock:
            self.state.update(building=frame, progress=self.state["progress"] + 1)


def _frame(detail: str, done: int = 0, total: int | None = None) -> dict:
    """An import's progress event (``cad.engine.progress``): the read, or the parts collected, counted."""
    return {"kind": "import", "stage": "read" if total is None else "collect", "job": "part.step", "outputs": [],
            "detail": detail, "done": done, "total": total, "elapsedMs": 0}


class ImportStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="import-status-")))
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        self.step = folder / "part.step"
        self.step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        self.engine = _ImportingEngine()

    def test_a_202_carries_the_imports_frame_and_a_held_request_comes_back_as_it_moves(self) -> None:
        reading = _frame("reading part.step (1 KB)")
        self.engine.say(reading)
        # A request that hears nothing new is held its whole hold, then answered with the frame there is.
        quick = EngineDocuments(hold_seconds=0.2, retry_ms=0, server=self.engine)
        self.assertEqual(quick.response(str(self.step)), (202, {"state": "reading", "retryMs": 0, "building": reading}))
        # A request held for long comes back the moment the import moves, with the frame it moved to: it
        # returns at all only because it does (the hold outlives the test's patience).
        patient = EngineDocuments(hold_seconds=30.0, retry_ms=0, server=self.engine)
        collecting = _frame("collecting parts", 120, 628)
        threading.Timer(0.05, self.engine.say, args=(collecting,)).start()
        status, body = patient.response(str(self.step))
        self.assertEqual((status, body["state"], body["building"]), (202, "reading", collecting))
        # The import in: the document, where every request for it joined one serve.
        self.engine.say(None)
        self.engine.release.set()
        for documents in (quick, patient):
            self.assertEqual(documents.response(str(self.step)), (200, {"doc": "doc-1"}))

    def test_without_an_engine_the_202_says_no_frame(self) -> None:
        documents = EngineDocuments(hold_seconds=0.0, retry_ms=0, server=None)
        status, body = documents.response(str(self.step))
        self.assertEqual((status, body.get("building")), (202, None) if status == 202 else (400, None))


if __name__ == "__main__":
    unittest.main()
