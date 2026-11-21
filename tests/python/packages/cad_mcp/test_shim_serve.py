"""The stdio transport ends quietly on Ctrl+C (``cad_mcp.shim.serve``): an interrupt
lands the same way SIGTERM does, through ``_Leaving``, not as a ``KeyboardInterrupt``
traceback in the host's terminal."""

from __future__ import annotations

import io
import signal
import threading
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
                # and SIGTERM terminates the process outright. _Leaving ignores the
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
                self.fail("SIGINT raised KeyboardInterrupt instead of leaving through _Leaving")
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


class ShimServeSignalsWhileLeavingTest(unittest.TestCase):
    """A host's stop often sends more than one signal (a stop of the process group reaches ``cad mcp`` directly
    and again through the ``uvx`` it runs under; SIGINT then SIGTERM). Signals that come while the transport
    leaves never cut the session's end short, and never raise inside ``threading``'s waits, where a ``SystemExit``
    raised as a lock is re-acquired turns into ``RuntimeError: release unlocked lock``."""

    def setUp(self) -> None:
        self.numbers = [getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, name)]
        for number in self.numbers:
            self.addCleanup(signal.signal, number, signal.getsignal(number))

    def _serve(self, first_signal):
        """``shim.serve`` with a session open, whose end the server answers only once more signals have come.
        ``first_signal``: the signal that ends the serving, or None for the input's end. The later signals are
        raised on a thread of their own, as a signal the system hands to any thread but the main one is, while
        the main thread waits in the close: Python runs their handler on the main thread as that wait returns,
        inside ``threading``'s re-acquiring of the wait's lock.
        Returns the ``SystemExit`` ``serve`` raises and the session-end requests the server was sent."""
        proxy = shim.Proxy(holder=None)
        proxy.session, proxy.protocol = "the-session", "2025-06-18"
        ended = []

        def call(method, path, body=b"", headers=None, timeout=None):
            waiting, answered = threading.Event(), threading.Event()

            def host():
                waiting.wait()  # the close is past its thread's start
                for number in self.numbers * 3:  # more than one, several of each
                    signal.raise_signal(number)
                answered.set()

            raising = threading.Thread(target=host, daemon=True)
            raising.start()
            waiting.set()
            answered.wait()
            raising.join()
            ended.append((method, headers, timeout))
            return 200, {}, b""

        proxy.call = call

        def stop():
            if first_signal is not None:
                signal.raise_signal(first_signal)

        with mock.patch.object(shim, "Holder"), \
                mock.patch.object(shim, "Proxy", return_value=proxy), \
                mock.patch.object(shim, "Connection") as mock_connection, \
                mock.patch.object(shim, "claim_stdin", return_value=io.BytesIO(b"")), \
                mock.patch.object(shim, "claim_stdout", return_value=io.BytesIO()), \
                mock.patch.object(shim, "launcher", return_value=None):
            mock_connection.return_value.serve.side_effect = stop
            with self.assertRaises(SystemExit) as caught:
                shim.serve()
        return caught.exception, ended

    def test_signals_after_the_first_leave_the_session_ended_and_the_first_signals_exit(self) -> None:
        error, ended = self._serve(signal.SIGTERM)
        self.assertEqual([(method, headers) for method, headers, _timeout in ended],
                         [("DELETE", {"Mcp-Session-Id": "the-session"})])
        self.assertEqual(error.code, 128 + signal.SIGTERM)
        # No later signal cuts the session's end short, so its own bound ends a server that never answers it.
        self.assertEqual(ended[0][2], shim.CLOSE_SECONDS)

    def test_signals_after_the_input_ended_leave_the_session_ended_and_exit_as_the_first(self) -> None:
        error, ended = self._serve(None)
        self.assertEqual([method for method, _headers, _timeout in ended], ["DELETE"])
        self.assertIn(error.code, [128 + number for number in self.numbers])


if __name__ == "__main__":
    unittest.main()
