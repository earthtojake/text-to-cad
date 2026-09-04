"""Run ONE test file under its dotted path (like scripts/test/unittest_files.py) and
emit JSON: wall seconds, import seconds, test count, outcome, and per-test seconds.

    python scripts/test/time_module.py <repo top> <test file> <out.json>

A helper of scripts/test/time-python.sh; nothing else calls it.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
import unittest


def dotted(path: str, top: str) -> str:
    rel = os.path.relpath(os.path.abspath(path), top)
    return os.path.splitext(rel)[0].replace(os.sep, ".")


class TimingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.times: dict[str, float] = {}
        self._t0 = 0.0

    def startTest(self, test):
        self._t0 = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        self.times[test.id()] = time.perf_counter() - self._t0


def main() -> int:
    top, path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path[0] = ""
    t0 = time.perf_counter()
    name = dotted(path, top)
    try:
        module = importlib.import_module(name)
    except BaseException as error:  # noqa: BLE001
        payload = {
            "module": name,
            "seconds": time.perf_counter() - t0,
            "tests": 0,
            "status": f"import-failed: {type(error).__name__}: {error}",
            "per_test": {},
        }
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return 1
    import_seconds = time.perf_counter() - t0
    suite = unittest.TestLoader().loadTestsFromModule(module)
    with open(os.devnull, "w", encoding="utf-8") as sink:
        runner = unittest.TextTestRunner(stream=sink, verbosity=0, resultclass=TimingResult)
        result = runner.run(suite)
    status = "ok"
    if not result.wasSuccessful():
        status = f"failed: failures={len(result.failures)} errors={len(result.errors)}"
    payload = {
        "module": name,
        "seconds": time.perf_counter() - t0,
        "import_seconds": import_seconds,
        "tests": result.testsRun,
        "skipped": len(result.skipped),
        "status": status,
        "per_test": result.times,
    }
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
