"""The stdio JSON-RPC transport: framing, concurrency, cancellation, requests out."""

from __future__ import annotations

import io
import json
import os
import queue
import threading
import time
import unittest

from cadgen.mcp.protocol import Connection, RpcError


class _Pipe:
    """A line source the test feeds; iteration ends when it is closed."""

    def __init__(self) -> None:
        self._lines: queue.Queue = queue.Queue()

    def send(self, message: dict) -> None:
        self._lines.put(json.dumps(message).encode() + b"\n")

    def close(self) -> None:
        self._lines.put(None)

    def __iter__(self):
        while (line := self._lines.get()) is not None:
            yield line


class _Sink(io.RawIOBase):
    def __init__(self) -> None:
        self.frames: queue.Queue = queue.Queue()
        self._buffer = b""

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self._buffer += bytes(data)
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            self.frames.put(json.loads(line))
        return len(data)

    def next(self, timeout: float = 5.0) -> dict:
        return self.frames.get(timeout=timeout)


class ConnectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pipe, self.sink = _Pipe(), _Sink()
        self.release = threading.Event()

        def handler(method, params, context):
            if method == "slow":
                self.release.wait(5)
                return {"slow": True}
            if method == "fast":
                return {"fast": True, "meta": context.meta}
            if method == "ask":
                return {"answer": context.connection.request("peer/question", {"q": 1}, timeout=5)}
            if method == "bad":
                raise RpcError(-32602, "bad params", {"field": "x"})
            if method == "boom":
                raise ValueError("kaboom")
            raise RpcError(-32601, f"no {method}")

        self.connection = Connection(self.pipe, self.sink, handler)
        self.thread = threading.Thread(target=self.connection.serve, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.release.set()
        self.pipe.close()
        self.thread.join(5)

    def test_a_slow_request_does_not_block_a_fast_one(self) -> None:
        self.pipe.send({"jsonrpc": "2.0", "id": 1, "method": "slow"})
        self.pipe.send({"jsonrpc": "2.0", "id": 2, "method": "fast", "params": {"_meta": {"threadId": "t"}}})
        first = self.sink.next()
        self.assertEqual(first, {"jsonrpc": "2.0", "id": 2, "result": {"fast": True, "meta": {"threadId": "t"}}})
        self.release.set()
        self.assertEqual(self.sink.next()["id"], 1)

    def test_errors_keep_their_code_and_unexpected_ones_are_internal(self) -> None:
        self.pipe.send({"jsonrpc": "2.0", "id": 1, "method": "bad"})
        self.assertEqual(self.sink.next()["error"], {"code": -32602, "message": "bad params", "data": {"field": "x"}})
        self.pipe.send({"jsonrpc": "2.0", "id": 2, "method": "boom"})
        error = self.sink.next()["error"]
        self.assertEqual(error["code"], -32603)
        self.assertIn("kaboom", error["message"])

    def test_garbage_gets_a_parse_error_and_the_stream_survives(self) -> None:
        self.pipe._lines.put(b"{not json\n")
        self.assertEqual(self.sink.next()["error"]["code"], -32700)
        self.pipe.send({"jsonrpc": "2.0", "id": 3, "method": "fast"})
        self.assertEqual(self.sink.next()["id"], 3)

    def test_a_cancelled_request_gets_no_response(self) -> None:
        self.pipe.send({"jsonrpc": "2.0", "id": 7, "method": "slow"})
        self.pipe.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7}})
        deadline = time.monotonic() + 5
        while not self.connection.is_cancelled(7):  # await the reader, not a fixed sleep
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        self.release.set()
        self.pipe.send({"jsonrpc": "2.0", "id": 8, "method": "fast"})
        self.assertEqual(self.sink.next()["id"], 8)
        self.assertTrue(self.sink.frames.empty())

    def test_a_broken_output_pipe_fails_a_peer_request(self) -> None:
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        with os.fdopen(write_fd, "wb", buffering=0) as writer:
            connection = Connection([], writer, lambda *args: {})
            self.addCleanup(connection.serve)
            with self.assertRaisesRegex(ConnectionError, "closed the connection"):
                connection.request("roots/list", {}, timeout=0)
            self.assertTrue(connection.closed)

    def test_a_request_to_the_peer_waits_for_its_reply(self) -> None:
        self.pipe.send({"jsonrpc": "2.0", "id": 1, "method": "ask"})
        outgoing = self.sink.next()
        self.assertEqual(outgoing["method"], "peer/question")
        self.pipe.send({"jsonrpc": "2.0", "id": outgoing["id"], "result": {"a": 42}})
        self.assertEqual(self.sink.next(), {"jsonrpc": "2.0", "id": 1, "result": {"answer": {"a": 42}}})


class ClaimStdoutTest(unittest.TestCase):
    def test_stray_output_goes_to_stderr_not_the_protocol(self) -> None:
        import subprocess
        import sys

        script = (
            "import os,sys\n"
            "from cadgen.mcp.protocol import claim_stdout\n"
            "out = claim_stdout()\n"
            "print('stray')\n"
            "os.system('echo child')\n"
            "out.write(b'{\"frame\":1}\\n')\n"
        )
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, env={**os.environ}, timeout=60)
        self.assertEqual(done.stdout, b'{"frame":1}\n')
        self.assertIn(b"stray", done.stderr)
        self.assertIn(b"child", done.stderr)


if __name__ == "__main__":
    unittest.main()
