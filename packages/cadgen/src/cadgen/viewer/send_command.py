"""Quick Edit's Send, where the launch named a command to send to (``cadgen viewer --send-command``).

POST /__cad/send takes ``{"text": ...}``: the prompt as Copy Prompt writes it (the note, the file,
the snapshot inline or by its path). The command runs once per send, in the launch's folder, with
that text on its standard input, and what it prints is its answer: exit 0 answers 200
``{"ok": true, "reply": stdout}``, any other exit 200 ``{"ok": false, "error": ...}`` (its standard
error, else its output: what it says is wrong), which keeps the note. The command is the launch's,
split into arguments without a shell; the page gives only the text. One send runs at a time: a
second while one runs is refused as busy, and a send that outlasts ``SEND_SECONDS`` is stopped.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading

__all__ = ["SEND_ROUTE", "MAX_SEND_BYTES", "SendCommand"]

SEND_ROUTE = "/__cad/send"
# A prompt is text: its snapshot rides inline only while small, else by path.
MAX_SEND_BYTES = 1024 * 1024
# What a send may take: a command that rebuilds a model and redraws it takes minutes, not hours.
SEND_SECONDS = 900.0
# What an answer carries back to the page: its last lines, which say what happened.
MAX_REPLY_CHARS = 4000
_REQUEST_KEYS = frozenset({"text"})


def _tail(text: str) -> str:
    # Lines as the page shows them, whichever platform's program wrote them.
    text = text.replace("\r\n", "\n").strip()
    return text if len(text) <= MAX_REPLY_CHARS else "…" + text[-MAX_REPLY_CHARS:]


class SendCommand:
    """The launch's command (``argv``, empty: nothing to send to) and the folder it runs in."""

    def __init__(self, command: str = "", cwd: str | None = None, *, seconds: float = SEND_SECONDS) -> None:
        self.argv = shlex.split(command) if command and command.strip() else []
        self.cwd = cwd
        self.seconds = seconds
        self._running = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.argv)

    def send(self, body: bytes) -> tuple[int, dict]:
        """Run the command with the request's text on its input: ``(status, answer)``."""
        if not self.argv:
            return 404, {"ok": False, "error": "This viewer was launched without a command to send to (cadgen viewer --send-command)."}
        try:
            request = json.loads(body or b"null")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"a send is requested as JSON: {error}") from None
        if type(request) is not dict or set(request) != _REQUEST_KEYS or type(request["text"]) is not str or not request["text"].strip():
            raise ValueError("a send is {text}: the prompt, not empty")
        if not self._running.acquire(blocking=False):
            return 409, {"ok": False, "error": "The previous send is still running."}
        try:
            done = subprocess.run(self.argv, cwd=self.cwd, input=request["text"].encode("utf-8"),
                                  capture_output=True, timeout=self.seconds, check=False)
        except FileNotFoundError:
            return 200, {"ok": False, "error": f"No program {self.argv[0]} to send to."}
        except subprocess.TimeoutExpired:
            return 200, {"ok": False, "error": f"{self.argv[0]} took longer than {self.seconds:.0f} s and was stopped."}
        finally:
            self._running.release()
        out = done.stdout.decode("utf-8", errors="replace")
        if done.returncode == 0:
            return 200, {"ok": True, "reply": _tail(out)}
        said = _tail(done.stderr.decode("utf-8", errors="replace")) or _tail(out)
        return 200, {"ok": False, "error": said or f"{self.argv[0]} exited with {done.returncode}."}
