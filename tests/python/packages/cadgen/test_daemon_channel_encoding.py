"""The pool's frame channel is utf-8 at both ends, and nothing else re-encodes it.

A warm worker's stdout is not a console: it carries the JSON frames the pool
reads. Its encoding therefore belongs to the protocol, and both ends have to
name it. On Windows they did not -- `text=True` alone decodes the ANSI code
page -- so once the CLI began emitting utf-8 the frames arrived as mojibake and
one failing build reported itself two different ways, cold versus warm.

These assertions hold on every platform. The end-to-end symptom only appears
where the locale is not already utf-8, which is why it reached CI green twice
before Windows caught it.
"""

from __future__ import annotations

import inspect
import os
import sys
import unittest
from unittest import mock

from cadgen.cli import _use_utf8_std_streams
from cadgen.daemon import pool, worker


class FrameChannelEncodingTest(unittest.TestCase):
    def test_the_pool_decodes_worker_frames_as_utf8(self) -> None:
        """Read the Popen call's own keywords, not the file's text: `text=True`
        with no `encoding` is the defect, and it is invisible to a substring
        search that only proves both words appear somewhere."""
        import ast
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(pool.Worker.__init__)))
        spawns = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Popen"
        ]
        self.assertEqual(1, len(spawns), "expected exactly one worker spawn")
        keywords = {kw.arg: kw.value for kw in spawns[0].keywords}
        self.assertIn("encoding", keywords, "text=True without an explicit encoding is the locale's guess")
        self.assertEqual("utf-8", ast.literal_eval(keywords["encoding"]))
        self.assertEqual("backslashreplace", ast.literal_eval(keywords["errors"]))

    def test_the_worker_pins_its_own_channel(self) -> None:
        source = inspect.getsource(worker.serve)
        self.assertIn('encoding="utf-8"', source)
        self.assertIn("sys.stdout", source)


class CliHelperOwnershipTest(unittest.TestCase):
    """The CLI helper reconfigures process globals, so it must not run where the
    streams belong to somebody else -- the worker being the case that bit."""

    def setUp(self) -> None:
        self._prev = os.environ.get("CADGEN_DAEMON_CHILD")
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._prev is None:
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
        else:
            os.environ["CADGEN_DAEMON_CHILD"] = self._prev

    def test_it_does_nothing_inside_a_daemon_worker(self) -> None:
        os.environ["CADGEN_DAEMON_CHILD"] = "1"
        calls = []
        for name in ("stdout", "stderr"):
            stream = mock.Mock()
            stream.reconfigure.side_effect = lambda **kw: calls.append(kw)
            self.enterContext(mock.patch.object(sys, name, stream))
        _use_utf8_std_streams()
        self.assertEqual([], calls, "the helper reconfigured the pool's frame channel")

    def test_it_reconfigures_at_a_real_cli_boundary(self) -> None:
        os.environ.pop("CADGEN_DAEMON_CHILD", None)
        calls = []
        for name in ("stdout", "stderr"):
            stream = mock.Mock()
            stream.reconfigure.side_effect = lambda **kw: calls.append(kw)
            self.enterContext(mock.patch.object(sys, name, stream))
        _use_utf8_std_streams()
        self.assertEqual(
            [{"encoding": "utf-8", "errors": "backslashreplace"}] * 2,
            calls,
        )

    def test_a_stream_without_reconfigure_is_left_alone(self) -> None:
        os.environ.pop("CADGEN_DAEMON_CHILD", None)
        for name in ("stdout", "stderr"):
            self.enterContext(mock.patch.object(sys, name, object()))
        _use_utf8_std_streams()  # must not raise


if __name__ == "__main__":
    unittest.main()
