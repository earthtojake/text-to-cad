"""Quick Edit's Send runs the launch's command with the prompt on its input, and answers what it printed."""

from __future__ import annotations

import http.client
import json
import shlex
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app
from cadgen.viewer.send_command import SendCommand

# A command that answers what it was given, upper-cased, and fails on the word "fail".
ECHO = """import sys
text = sys.stdin.read()
if "fail" in text:
    sys.stderr.write("refused: " + text.strip())
    sys.exit(3)
print("got " + text.strip().upper())
"""


class SendRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.script = self.tmp / "echo.py"
        self.script.write_text(ECHO, encoding="utf-8")
        self.app = create_cad_app(host="127.0.0.1", port=0)
        server = handler_module.serve(self.app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def command(self, *args: str) -> str:
        return shlex.join([Path(sys.executable).as_posix(), "-I", self.script.as_posix(), *args])

    def call(self, path: str, body, *, method: str = "POST") -> tuple[int, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=json.dumps(body), headers={"x-cadgen-viewer": "1", "content-type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b"null")
        finally:
            connection.close()

    def server(self) -> dict:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", "/__cad/server")
            return json.loads(connection.getresponse().read())
        finally:
            connection.close()

    def test_without_a_command_nothing_sends(self) -> None:
        self.assertIs(self.server()["send"], False)
        status, answer = self.call("/__cad/send", {"text": "repair"})
        self.assertEqual(status, 404)
        self.assertFalse(answer["ok"])
        self.assertIn("--send-command", answer["error"])

    def test_the_command_reads_the_prompt_and_its_output_is_the_reply(self) -> None:
        self.app.send_command = SendCommand(self.command(), str(self.tmp))
        self.assertIs(self.server()["send"], True)
        status, answer = self.call("/__cad/send", {"text": "repair\n\nFile: \"/models/part.stl\""})
        self.assertEqual((status, answer), (200, {"ok": True, "reply": 'got REPAIR\n\nFILE: "/MODELS/PART.STL"'}))

    def test_a_failing_command_says_why_from_its_standard_error(self) -> None:
        self.app.send_command = SendCommand(self.command(), str(self.tmp))
        status, answer = self.call("/__cad/send", {"text": "fail here"})
        self.assertEqual((status, answer), (200, {"ok": False, "error": "refused: fail here"}))

    def test_a_missing_program_and_a_bad_request_are_said(self) -> None:
        self.app.send_command = SendCommand(shlex.join([(self.tmp / "nothing-here").as_posix()]), str(self.tmp))
        status, answer = self.call("/__cad/send", {"text": "repair"})
        self.assertEqual(status, 200)
        self.assertIn("No program", answer["error"])
        for body in ({"text": "  "}, {"text": 1}, {"note": "repair"}, ["repair"]):
            status, answer = self.call("/__cad/send", body)
            self.assertEqual(status, 400, body)
            self.assertFalse(answer["ok"])

    def test_one_send_at_a_time_and_get_is_refused(self) -> None:
        command = SendCommand(self.command(), str(self.tmp))
        self.app.send_command = command
        with command._running:
            status, answer = self.call("/__cad/send", {"text": "repair"})
        self.assertEqual((status, answer["ok"]), (409, False))
        status, _ = self.call("/__cad/send", {"text": "repair"}, method="GET")
        self.assertEqual(status, 405)

    def test_a_send_that_outlasts_its_time_is_stopped(self) -> None:
        slow = self.tmp / "slow.py"
        slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        self.app.send_command = SendCommand(shlex.join([Path(sys.executable).as_posix(), "-I", slow.as_posix()]), str(self.tmp), seconds=0.5)
        status, answer = self.call("/__cad/send", {"text": "repair"})
        self.assertEqual(status, 200)
        self.assertIn("longer than", answer["error"])


if __name__ == "__main__":
    unittest.main()
