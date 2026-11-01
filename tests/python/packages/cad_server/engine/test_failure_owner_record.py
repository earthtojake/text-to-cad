"""The page's record of a failed build carries whose the error is to fix (``owner``)."""

from __future__ import annotations

import unittest
from unittest import mock


class DaemonCarriesOwnerTest(unittest.TestCase):
    """The daemon hands the report's ``owner`` to the page's failure record (``Daemon._built``);
    a worker that failed without a report is the engine's."""

    def built(self, answer: dict) -> dict:
        from cad_server.engine.daemon import Daemon

        server = mock.Mock()
        engine = mock.Mock(server=server)
        engine.models.paths.side_effect = lambda _worker, model: [f"id:{model}"] if model else []
        Daemon._built(engine, mock.Mock(progress={"job": "parts.py::plate"}), answer)
        return server.built.call_args.args[0]

    def test_a_report_s_owner_reaches_the_record_and_a_dead_worker_is_internal(self) -> None:
        report = {"ok": False, "model": "parts.py::asserted", "error": "AssertionError", "owner": "model",
                  "child_models": {"parts.py::child": {"id": "child", "ok": False, "error": "x", "owner": "kernel"}}}
        outcomes = self.built({"done": {"reports": [report]}})
        self.assertEqual(outcomes["id:parts.py::asserted"]["owner"], "model")
        self.assertEqual(outcomes["child"]["owner"], "kernel")
        self.assertEqual(self.built({"done": {"reports": [{**report, "owner": None}]}})["id:parts.py::asserted"]["owner"],
                         "internal")
        gone = self.built({"failed": "the worker exited (-11)"})
        self.assertEqual(gone["id:parts.py::plate"]["owner"], "internal")


if __name__ == "__main__":
    unittest.main()
