"""The sender and the receiver agree on ``install`` and ``install_app``: every shape cad's telemetry makes of a run of
``cad plugin install`` or ``cad plugin update`` (``cad_server/analytics.py``: ``install``, sent by its real sender) is
read by the real receiver (``apps/api/src/events.mjs``: ``rowsOf``) and made the PostHog events a dashboard reads
(``posthog.mjs``: ``eventOf``), the app the plugin went into under a name of its own (``plugin_app``: a row's ``app``
is the agent app running cad). A word one end has and the other lacks, a fraction of a second, a row twice in a batch
or a run counted as ended in a way its apps deny would refuse a whole batch. The packages run from source, the
receiver under node: nothing installed."""

from __future__ import annotations

import collections
import copy
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
# Reads from stdin the batches the sender sent; writes each one's PostHog events, or why it was refused.
SCRIPT = """
import { readFileSync } from 'node:fs';
import { rowsOf } from %(events)s;
import { eventOf } from %(posthog)s;
const out = [];
for (const batch of JSON.parse(readFileSync(0, 'utf8'))) {
  try {
    out.push({ events: rowsOf(batch).map(row => eventOf(row, null)) });
  } catch (error) {
    out.push({ refused: `${error.name}: ${error.message}` });
  }
}
process.stdout.write(JSON.stringify(out));
"""
RUN = ("by", "outcome", "logo", "colour", "seconds", "found", "failed")
APP = ("plugin_app", "status", "reason", "seconds")


class InstallSenderAndReceiverAgree(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="install-contract-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "",
                                                   "CAD_TELEMETRY": "", "CAD_API_URL": "http://127.0.0.1:9"})
        environment.start()
        self.addCleanup(environment.stop)

    def read(self, batches: list[dict]) -> list[dict]:
        """What the real receiver makes of each of ``batches``: its PostHog ``events``, or why it ``refused`` it."""
        node = shutil.which("node")
        self.assertIsNotNone(node, "node runs the receiver's code")
        script = SCRIPT % {"events": json.dumps((API / "events.mjs").as_uri()),
                           "posthog": json.dumps((API / "posthog.mjs").as_uri())}
        done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(batches),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def runs(self) -> list[dict]:
        """Runs covering every word: each beginner, logo and colour, ended each way, and between them every app of
        cad's table with every status and, failed, every reason; seconds none, a fraction, and past the most."""
        from cad_server import analytics
        from cad_server.plugin.apps import APPS

        most = analytics.MAX_INSTALL_SECONDS
        done = itertools.cycle([(app.key, status, None, seconds)
                                for app, seconds in zip(APPS, itertools.cycle((0.0, 3.9, 59.99)))
                                for status in sorted(analytics.INSTALL_STATUSES - {"failed"})])
        failed = itertools.cycle([(app.key, "failed", reason, seconds)
                                  for app, seconds in zip(APPS, itertools.cycle((0.2, 120.0, most + 7.0)))
                                  for reason in sorted(analytics.INSTALL_FAILURES)])
        runs = []
        for by, logo, colour in itertools.product(sorted(analytics.INSTALL_BY), sorted(analytics.INSTALL_LOGOS),
                                                  sorted(analytics.INSTALL_COLOURS)):
            said = dict(by=by, logo=logo, colour=colour)
            runs.append(dict(said, busy=True, seconds=0.01, apps=[]))
            runs.append(dict(said, seconds=0.4, apps=[]))
            runs.append(dict(said, seconds=12.7, apps=[next(done), next(failed), next(done), next(failed), next(done)]))
            runs.append(dict(said, seconds=most + 5.0, apps=[next(failed), next(failed)]))
        runs.extend([runs[2]] * 2)  # the same run again, twice: one row, counted
        return runs

    def test_every_run_the_sender_makes_is_one_the_receiver_reads(self) -> None:
        from cad_server import analytics
        from cad_server._internal import telemetry_send
        from cad_server.plugin.apps import APPS

        settings = analytics.settings_path()
        analytics.choose(True, by="cli", path=settings)
        most = analytics.MAX_INSTALL_SECONDS
        runs = self.runs()
        made_runs: collections.Counter = collections.Counter()
        made_apps: collections.Counter = collections.Counter()
        for each in runs:  # what each should be read as, worked out here from the run alone
            broke = [app for app in each["apps"] if app[1] == "failed"]
            outcome = "busy" if each.get("busy") else "failed" if broke and len(broke) == len(each["apps"]) else "ok"
            made_runs[(each["by"], outcome, each["logo"], each["colour"], min(int(each["seconds"]), most),
                       len(each["apps"]), len(broke))] += 1
            for key, status, reason, seconds in each["apps"]:
                made_apps[(key, status, reason, min(int(seconds), most))] += 1
        self.assertEqual({outcome for _, outcome, *_ in made_runs}, analytics.INSTALL_OUTCOMES)
        self.assertEqual({key for key, *_ in made_apps}, {app.key for app in APPS}, "every app of the table")
        self.assertEqual({(status, reason) for _, status, reason, _ in made_apps},
                         {(status, None) for status in analytics.INSTALL_STATUSES - {"failed"}}
                         | {("failed", reason) for reason in analytics.INSTALL_FAILURES})

        with mock.patch.object(telemetry_send, "start_now"):  # sent below, by the sender, in this process
            for each in runs:
                self.assertTrue(analytics.install(**each), each)
        batches: list[dict] = []
        telemetry_send.send(settings, send=lambda batch: batches.append(batch) or True)
        self.assertGreater(len(batches), 1, "more rows than one batch holds: the rest in the next")
        self.assertEqual({batch["schema"] for batch in batches}, {analytics.SCHEMA})
        self.assertEqual(sum(len(batch["events"]) for batch in batches), len(made_runs) + len(made_apps))

        read = self.read(batches)
        self.assertEqual([found.get("refused") for found in read], [None] * len(batches))
        events = [event for found in read for event in found["events"]]
        self.assertEqual({event["event"] for event in events}, {"plugin_installed", "plugin_app_installed"})
        stored_runs: collections.Counter = collections.Counter()
        stored_apps: collections.Counter = collections.Counter()
        for event in events:
            properties = event["properties"]
            self.assertEqual((properties["process"], properties["app"]), ("cli", batches[0]["app"]),
                             "a row's app is the batch's: the agent app running cad")
            if event["event"] == "plugin_installed":
                stored_runs[tuple(properties[name] for name in RUN)] += properties["count"]
                self.assertNotIn("plugin_app", properties)
            else:
                stored_apps[tuple(properties.get(name) for name in APP)] += properties["count"]
        self.assertEqual(stored_runs, made_runs)
        self.assertEqual(stored_apps, made_apps)
        self.assertEqual(stored_runs[("person", "ok", "failed", "24bit", 12, 5, 2)], 3, "runs alike: one row, counted")

    def test_the_receiver_refuses_what_the_sender_is_made_never_to_send(self) -> None:
        """Why the sender decides a run's outcome from its apps, sends whole seconds, leaves a reason out but for a
        failure and merges rows alike: the receiver refuses each of the others, and a batch refused is dropped whole."""
        from cad_server import analytics
        from cad_server._internal import telemetry_send

        settings = analytics.settings_path()
        analytics.choose(True, by="cli", path=settings)
        with mock.patch.object(telemetry_send, "start_now"):
            self.assertTrue(analytics.install(by="server", seconds=901.0, apps=[
                ("claude", "updated", None, 3.0), ("codex", "failed", "timeout", 898.0)]))
        batches: list[dict] = []
        telemetry_send.send(settings, send=lambda batch: batches.append(batch) or True)
        [batch] = batches
        run, done, failed = batch["events"]
        self.assertEqual((run["name"], run["outcome"], done["status"], failed["status"]),
                         ("install", "ok", "updated", "failed"))

        def changed(index: int, **fields) -> dict:
            other = copy.deepcopy(batch)
            other["events"][index] = {name: value for name, value in {**other["events"][index], **fields}.items()
                                      if value is not ...}
            return other

        refused = {
            "failed, with an app that did not fail": changed(0, outcome="failed"),
            "failed, with no app found": changed(0, outcome="failed", found=0, failed=0),
            "ok, with every app found failed": changed(0, found=1, failed=1),
            "busy, with apps found": changed(0, outcome="busy"),
            "more failed than found": changed(0, failed=3),
            "a fraction of a second": changed(0, seconds=901.5),
            "an app's fraction of a second": changed(1, seconds=3.5),
            "a null reason": changed(1, reason=None),
            "a reason on an app that did not fail": changed(1, reason="other"),
            "a failure with no reason": changed(2, reason=...),
            "a row twice": {**batch, "events": [*batch["events"], batch["events"][1]]},
        }
        read = self.read([batch, *refused.values()])
        self.assertNotIn("refused", read[0])
        for why, found in zip(refused, read[1:]):
            self.assertIn("refused", found, why)


if __name__ == "__main__":
    unittest.main()
