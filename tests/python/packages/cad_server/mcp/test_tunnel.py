"""The CAD app's tunnel as an MCP session builds it: over the session's own viewer app."""

from __future__ import annotations

import unittest

from cad_server.mcp import tunnel
from cad_server.mcp.tunnel import ViewerTunnel
from cad_server.viewer.engine_app import ViewerApp


class HandedInAppTest(unittest.TestCase):
    def test_a_handed_in_app_holds_a_call_briefly_and_has_the_page_ask_again_later(self) -> None:
        # ``Sessions._new``: a ViewerApp over the engine's server, handed to the tunnel.
        app = ViewerTunnel(app=ViewerApp(None, host="127.0.0.1", port=0, start=None)).app
        self.assertEqual([(answers.hold_seconds, answers.retry_ms) for answers in (app.drawings, app.boards)],
                         [(tunnel.DRAWING_HOLD_SECONDS, tunnel.DRAWING_RETRY_MS)] * 2)
        self.assertEqual((app.engine_documents.hold_seconds, app.engine_documents.retry_ms),
                         (tunnel.ENGINE_HOLD_SECONDS, tunnel.ENGINE_RETRY_MS))


def setUpModule() -> None:
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
