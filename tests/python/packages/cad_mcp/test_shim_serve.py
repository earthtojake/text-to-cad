"""The stdio transport ends quietly on Ctrl+C (``cad_mcp.shim.serve``): an interrupt
lands the same way SIGTERM does, through ``_leave``, not as a ``KeyboardInterrupt``
traceback in the host's terminal."""

from __future__ import annotations

import io
import signal
import unittest
from unittest import mock

from cad_mcp import shim


class ShimServeInterruptTest(unittest.TestCase):
    """SIGINT during ``serve`` raises ``SystemExit`` with the signal's code (128 + 2),
    exactly as SIGTERM does (128 + 15) -- never a ``KeyboardInterrupt`` traceback."""

    def setUp(self) -> None:
        self._handlers = {}
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            if hasattr(signal, name):
                number = getattr(signal, name)
                self._handlers[number] = signal.getsignal(number)

    def tearDown(self) -> None:
        for number, handler in self._handlers.items():
            signal.signal(number, handler)

    def _serve_with(self, interrupt_in):
        """Run ``shim.serve`` with its collaborators stubbed; ``interrupt_in`` names
        where the interrupt lands (``serve`` or ``close``) and delivers SIGINT there by
        invoking the handler ``serve`` installed. Returns the ``SystemExit`` ``serve``
        raises."""
        with mock.patch.object(shim, "Holder"), \
                mock.patch.object(shim, "Proxy") as mock_proxy, \
                mock.patch.object(shim, "Connection") as mock_connection, \
                mock.patch.object(shim, "claim_stdin", return_value=io.BytesIO(b"")), \
                mock.patch.object(shim, "claim_stdout", return_value=io.BytesIO()), \
                mock.patch.object(shim, "launcher", return_value=None):
            def interrupt():
                # Deliver the signal by invoking the handler serve() installed:
                # os.kill(os.getpid(), ...) kills this interpreter on Windows,
                # where SIGINT is not delivered through Python's signal machinery
                # and SIGTERM terminates the process outright. _leave ignores the
                # frame, so this is exactly what the OS would invoke.
                signal.getsignal(signal.SIGINT)(signal.SIGINT, None)

            if interrupt_in == "serve":
                mock_connection.return_value.serve.side_effect = interrupt
            else:
                mock_proxy.return_value.close.side_effect = interrupt
            try:
                with self.assertRaises(SystemExit) as caught:
                    shim.serve()
            except KeyboardInterrupt:
                # unittest re-raises KeyboardInterrupt instead of recording it,
                # which would kill this file's whole run: name the failure instead.
                self.fail("SIGINT raised KeyboardInterrupt instead of leaving through _leave")
            return caught.exception

    def test_sigint_during_serve_leaves_like_sigterm(self) -> None:
        error = self._serve_with("serve")
        self.assertEqual(error.code, 128 + signal.SIGINT)

    def test_sigint_during_close_leaves_without_a_traceback(self) -> None:
        # The issue's traceback: the interrupt lands inside the ``finally`` block's
        # ``proxy.close()`` while the session is being ended.
        error = self._serve_with("close")
        self.assertEqual(error.code, 128 + signal.SIGINT)

    def test_sigterm_during_serve_still_leaves_with_its_own_code(self) -> None:
        with mock.patch.object(shim, "Holder"), \
                mock.patch.object(shim, "Proxy"), \
                mock.patch.object(shim, "Connection") as mock_connection, \
                mock.patch.object(shim, "claim_stdin", return_value=io.BytesIO(b"")), \
                mock.patch.object(shim, "claim_stdout", return_value=io.BytesIO()), \
                mock.patch.object(shim, "launcher", return_value=None):
            def interrupt():
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

            mock_connection.return_value.serve.side_effect = interrupt
            with self.assertRaises(SystemExit) as caught:
                shim.serve()
            self.assertEqual(caught.exception.code, 128 + signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
