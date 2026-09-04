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

import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages", "cadgen", "src")

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


if __name__ == "__main__":
    unittest.main()
