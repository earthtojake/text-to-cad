"""A LinuxCNC machine, read through ``linuxcncrsh``, the text server LinuxCNC ships for remote clients.

``linuxcncrsh`` (https://linuxcnc.org/docs/html/man/man1/linuxcncrsh.1.html) listens on port 5007 and
takes any number of clients. The reader says ``hello`` with the server's connect password (``EMC`` unless
the machine was started with another: ``?password=``), sets its own session's units to millimetres
(``set linear_unit_conversion mm``: how this connection's answers are written, nothing of the
machine's), and from then on only ``get``s: the actual position, the program's state and line, the
estop and the machine's power. It never asks to be enabled (``set enable``), which every command that
moves or changes the machine needs.
"""

from __future__ import annotations

import socket
import time

from .reading import Reading

# ``abs_act_pos``'s nine values, in LinuxCNC's axis order.
_AXES = ("X", "Y", "Z", "A", "B", "C", "U", "V", "W")
_PROGRAM = {"IDLE": "idle", "RUNNING": "running", "PAUSED": "paused"}


class LinuxcncError(ConnectionError):
    """What ``linuxcncrsh`` said, or did not, that leaves no reading."""


class LinuxcncReader:
    """A LinuxCNC machine at ``address`` (``linuxcnc://host[:port]``, 5007 unless told)."""

    def __init__(self, address, *, timeout: float = 2.0) -> None:
        self.address, self.timeout = address, timeout
        self.sock: socket.socket | None = None
        self.buffer = b""

    def open(self) -> None:
        self.sock = socket.create_connection((self.address.host, self.address.port), timeout=self.timeout)
        self.buffer = b""
        password = self.address.options.get("password", "EMC")
        answer = self._ask(f"hello {password} cad-mirror 1.1")
        if not answer.upper().startswith("HELLO ACK"):
            self.close()
            raise LinuxcncError("linuxcncrsh refused the hello: give its connect password as ?password=" if "NAK" in answer.upper()
                                else f"not a linuxcncrsh server: it answered {answer[:80]!r}")
        self._send("set linear_unit_conversion mm")
        units = self._ask("get linear_unit_conversion")
        if units.split()[-1:] != ["MM"]:
            self.close()
            raise LinuxcncError(f"linuxcncrsh kept its answers in other units than millimetres ({units[:80]!r})")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def read(self) -> Reading:
        position = self._get("abs_act_pos", "ABS_ACT_POS")
        try:
            values = [float(value) for value in position]
        except ValueError:
            raise LinuxcncError(f"linuxcncrsh's position is not numbers: {' '.join(position)!r}") from None
        axes = dict(zip(_AXES, values))
        program = (self._get("program_status", "PROGRAM_STATUS") or ["?"])[0].upper()
        estop = (self._get("estop", "ESTOP") or ["?"])[0].upper()
        power = (self._get("machine", "MACHINE") or ["?"])[0].upper()
        if estop == "ON":
            state, detail = "alarm", "ESTOP"
        elif power == "OFF":
            state, detail = "stopped", "MACHINE OFF"
        elif program in _PROGRAM:
            state, detail = _PROGRAM[program], program
        else:
            raise LinuxcncError(f"linuxcncrsh reported a program state it does not have: {program!r}")
        line_words = self._get("program_line", "PROGRAM_LINE")
        line = int(line_words[0]) if line_words and line_words[0].lstrip("-").isdigit() else None
        name = " ".join(self._get("program", "PROGRAM")) or None
        return Reading(axes=axes, state=state, detail=detail, line=line if line and line > 0 else None,
                       program=None if name in (None, "NONE", "none") else name)

    # --- the protocol: one line out, one line back ----------------------------------------------

    def _send(self, line: str) -> None:
        if self.sock is None:
            raise LinuxcncError("not connected")
        self.sock.sendall(line.encode("ascii") + b"\r\n")

    def _line(self) -> str:
        assert self.sock is not None
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0:
                raise LinuxcncError(f"no answer from {self.address.host} in {self.timeout:g} s")
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise LinuxcncError(f"{self.address.host} closed the connection")
            self.buffer += chunk
            if len(self.buffer) > 65536:
                raise LinuxcncError("linuxcncrsh sent a line longer than any it writes")
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line.decode("utf-8", "replace").strip()

    def _ask(self, line: str) -> str:
        self._send(line)
        return self._line()

    def _get(self, name: str, word: str) -> list[str]:
        """``get <name>``'s answer, the words after ``word``; NAK is an error naming what was asked."""
        answer = self._ask(f"get {name}")
        head, *rest = answer.split()
        if head.upper() != word:
            raise LinuxcncError(f"linuxcncrsh answered get {name} with {answer[:80]!r}")
        if rest and rest[0].upper() == "NAK":
            raise LinuxcncError(f"linuxcncrsh refused get {name}")
        return rest
