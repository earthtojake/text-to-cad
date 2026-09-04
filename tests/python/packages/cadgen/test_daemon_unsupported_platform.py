"""What the daemon does where it cannot run: nothing, quietly, and builds stay cold.

This guard was written for Windows, which had no transport at all: the daemon spoke
AF_UNIX and CPython does not provide it there. That is no longer the situation --
multiprocessing.connection carries AF_PIPE on Windows and AF_UNIX everywhere else, so
every platform this project supports can now run a daemon.

The guard stays anyway, because "can this platform carry a daemon" is still a question with
a real answer, and the failure mode it prevents is nasty out of proportion to its size: a
missing address family raises where every fallback in the client and its callers is keyed
on OSError or on a None return, so the exception escapes all of them and the command dies
instead of building. Warm is the default, so that would land on `cadgen step gen` rather
than somewhere obscure.

The platform is simulated rather than skipped off, so this holds on machines where it
cannot be reproduced.
"""

from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages", "cadgen", "src")

from cadgen.cli import daemon_status  # noqa: E402
from cadgen.daemon import client, transport  # noqa: E402


def no_transport():
    """Stand in for a platform offering neither AF_UNIX nor AF_PIPE."""
    return mock.patch.object(transport, "supported", return_value=False)


class DaemonSupported(unittest.TestCase):
    def test_it_follows_the_transport(self):
        with no_transport():
            self.assertFalse(client.daemon_supported())

    def test_every_platform_we_ship_on_has_a_family(self):
        # AF_UNIX on POSIX, AF_PIPE on Windows. If this ever fails, the daemon has lost
        # its transport on the machine running the suite.
        self.assertTrue(transport.supported())


class EveryEntryPointDegradesToCold(unittest.TestCase):
    """None is this module's "run it cold" answer; each caller already handles it."""

    def test_run_via_daemon_returns_none(self):
        with no_transport():
            self.assertIsNone(client.run_via_daemon("gen", ["part.py"], "/repo"))

    def test_status_returns_none(self):
        with no_transport():
            self.assertIsNone(client.status())

    def test_nothing_is_dialled_on_the_way_out(self):
        # The guard has to come before the connect, not around it. side_effect rather than
        # a bare Mock so a regression fails HERE: a plain Mock returns a Mock, whose frames
        # never stop arriving, and the caller's read loop would hang instead of failing.
        boom = AssertionError("the daemon was contacted on a platform with no transport")
        with no_transport(), mock.patch.object(
            client, "_connect_or_spawn", side_effect=boom
        ) as connect:
            self.assertIsNone(client.run_via_daemon("gen", ["part.py"], "/repo"))
        connect.assert_not_called()


class StatusCommandTellsTheTruth(unittest.TestCase):
    def test_it_does_not_promise_a_daemon_that_cannot_start(self):
        # "One starts on the next build" would send someone off to wait for a warm process
        # that no build will ever produce.
        out = io.StringIO()
        with no_transport(), contextlib.redirect_stdout(out):
            self.assertEqual(0, daemon_status.main([]))
        text = out.getvalue()
        self.assertIn("cannot run on this platform", text)
        self.assertNotIn("starts on the next build", text)

    def test_it_does_promise_one_where_a_daemon_can_start(self):
        out = io.StringIO()
        with mock.patch.object(transport, "supported", return_value=True), \
                mock.patch.object(client, "status", return_value=None), \
                contextlib.redirect_stdout(out):
            self.assertEqual(0, daemon_status.main([]))
        self.assertIn("starts on the next build", out.getvalue())

    def test_json_output_stays_a_payload(self):
        # --json is consumed by tooling; an unsupported platform is still "nothing warm",
        # not a different shape.
        out = io.StringIO()
        with no_transport(), contextlib.redirect_stdout(out):
            self.assertEqual(0, daemon_status.main(["--json"]))
        self.assertEqual("{}", out.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
