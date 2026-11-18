"""The sender and the receiver agree on ``arrival`` and ``update``: every shape cad's telemetry makes of them
(``cad_server/analytics.py``: ``arrival``, ``update``, sent by its real sender) is read by the real receiver
(``apps/api/src/events.mjs``: ``rowsOf``) and made the PostHog event a dashboard reads (``posthog.mjs``: ``eventOf``).
A word one end has and the other lacks would refuse a whole batch. The packages run from source, the receiver
under node: nothing installed."""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps/api/src"
# Reads from stdin the batches the sender sent; writes each one's rows and PostHog events, or why it was refused.
SCRIPT = """
import { readFileSync } from 'node:fs';
import { rowsOf } from %(events)s;
import { eventOf } from %(posthog)s;
const out = [];
for (const batch of JSON.parse(readFileSync(0, 'utf8'))) {
  try {
    const rows = rowsOf(batch);
    out.push({ rows, events: rows.map(row => eventOf(row, null)) });
  } catch (error) {
    out.push({ refused: `${error.name}: ${error.message}` });
  }
}
process.stdout.write(JSON.stringify(out));
"""


class ArrivalSenderAndReceiverAgree(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="arrival-contract-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "",
                                                   "CAD_TELEMETRY": "", "CAD_API_URL": "http://127.0.0.1:9"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_every_arrival_the_sender_makes_is_one_the_receiver_reads(self) -> None:
        from cad_server import analytics
        from cad_server._internal import telemetry_send

        settings = analytics.settings_path()
        analytics.choose(True, by="cli", path=settings)
        shapes = []
        for step, outcomes in analytics.ARRIVAL_OUTCOMES.items():
            for outcome in sorted(outcomes):
                reasons = sorted(analytics.ARRIVAL_FAILURES[step]) if outcome == "failed" else [None]
                attempts = [0, 1, analytics.MAX_ATTEMPTS] if step == "handover" else [None]
                for route, earlier, reason, tried in itertools.product(sorted(analytics.ROUTES),
                                                                       (None, "0.11.10", "0.11.11-dev.20261115120000"),
                                                                       reasons, attempts):
                    shapes.append(dict(step=step, route=route, earlier=earlier, outcome=outcome, reason=reason,
                                       attempts=tried))
        with mock.patch.object(telemetry_send, "start_now"):  # sent below, by the sender, in this process
            for shape in shapes:
                self.assertTrue(analytics.arrival(**shape), shape)
        batches: list[dict] = []
        telemetry_send.send(settings, send=lambda batch: batches.append(batch) or True)
        self.assertEqual(sum(len(batch["events"]) for batch in batches), len(shapes))

        node = shutil.which("node")
        self.assertIsNotNone(node, "node runs the receiver's code")
        script = SCRIPT % {"events": json.dumps((API / "events.mjs").as_uri()),
                           "posthog": json.dumps((API / "posthog.mjs").as_uri())}
        done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(batches),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        read = json.loads(done.stdout)
        self.assertEqual([found.get("refused") for found in read], [None] * len(batches))
        events = [event for found in read for event in found["events"]]
        self.assertEqual({event["event"] for event in events}, {"version_arrival"})
        made = {(shape["step"], shape["route"], shape["earlier"] or "none", shape["outcome"], shape["reason"],
                 shape["attempts"]) for shape in shapes}
        stored = {(event["properties"]["step"], event["properties"]["route"], event["properties"]["from"],
                   event["properties"]["outcome"], event["properties"].get("reason"), event["properties"].get("attempts"))
                  for event in events}
        self.assertEqual(stored, made)
        self.assertTrue(all(event["properties"]["count"] == 1 and event["properties"]["process"] == "cli"
                            for event in events))

    def received(self, batches: list[dict]) -> list[dict]:
        """The PostHog events the real receiver makes of ``batches``; every batch read."""
        node = shutil.which("node")
        self.assertIsNotNone(node, "node runs the receiver's code")
        script = SCRIPT % {"events": json.dumps((API / "events.mjs").as_uri()),
                           "posthog": json.dumps((API / "posthog.mjs").as_uri())}
        done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(batches),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        read = json.loads(done.stdout)
        self.assertEqual([found.get("refused") for found in read], [None] * len(batches))
        return [event for found in read for event in found["events"]]

    def test_every_update_the_sender_makes_is_one_the_receiver_reads(self) -> None:
        from cad_server import analytics
        from cad_server._internal import telemetry_send

        settings = analytics.settings_path()
        analytics.choose(True, by="cli", path=settings)
        shapes = []
        for outcome in sorted(analytics.UPDATE_OUTCOMES):
            reasons = sorted(analytics.UPDATE_FAILURES.get(outcome, ())) or [None]
            plugins = sorted(analytics.UPDATE_PLUGIN) if outcome == "installed" else ["none"]
            for earlier, reason, tries, installer, asked, plugin in itertools.product(
                    (None, "0.11.12", "0.11.12-dev.20261118120000"), reasons, (1, analytics.MAX_ATTEMPTS),
                    sorted(analytics.UPDATE_INSTALLERS), (False, True), plugins):
                shapes.append(dict(earlier=earlier, outcome=outcome, reason=reason, tries=tries, installer=installer,
                                   asked=asked, plugin=plugin))
        with mock.patch.object(telemetry_send, "start_now"):  # sent below, by the sender, in this process
            for shape in shapes:
                self.assertTrue(analytics.update(**shape), shape)
        batches: list[dict] = []
        telemetry_send.send(settings, send=lambda batch: batches.append(batch) or True)
        self.assertEqual(sum(len(batch["events"]) for batch in batches), len(shapes))
        events = self.received(batches)
        self.assertEqual({event["event"] for event in events}, {"cad_updated"})
        names = ("from", "outcome", "reason", "tries", "installer", "asked", "plugin")
        made = {(shape["earlier"] or "none", *(shape[name] for name in names[1:])) for shape in shapes}
        stored = {tuple(event["properties"].get(name) for name in names) for event in events}
        self.assertEqual(stored, made)


if __name__ == "__main__":
    unittest.main()
