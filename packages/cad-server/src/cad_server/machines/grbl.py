"""A GRBL-family controller on the network -- FluidNC, grblHAL -- read by its status reports.

The reader sends one thing, the real-time status query ``?``: a single byte GRBL answers out of band,
never queued with the program's lines, whatever state the machine is in. The answer is the status
report, ``<Run|MPos:1.000,2.000,3.000|FS:500,12000|Ln:42|WCO:0.000,0.000,-5.000>``
(https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md, "Real-time Status Reports").

GRBL reports in millimetres or inches by its ``$13`` setting, and reading the setting is a ``$$``, a
line that enters the controller's command stream beside the program's. So the reader never asks: it
takes millimetres (``$13=0``, the default) and says so, and an address with ``?units=inch`` reads inches.
A report gives the machine's position (``MPos``) or the work position (``WPos``) by ``$10``; the work
position is turned into the machine's with the last work offset (``WCO``) the controller sent, and until
it has sent one the reading waits for it rather than guess.

Over USB, GRBL shares one serial port with the program that runs it, so it is not read here (the
package's docstring).
"""

from __future__ import annotations

import socket
import time

from .reading import AXES, Reading

INCH = 25.4

# GRBL's states (the report's first field, before any ``:`` substate) in the page's words.
_STATES = {"Idle": "idle", "Run": "running", "Jog": "running", "Home": "running", "Check": "idle",
           "Hold": "paused", "Door": "paused", "Alarm": "alarm", "Sleep": "stopped"}


class GrblError(ConnectionError):
    """What the controller said, or did not, that leaves no reading."""


def _numbers(text: str, field: str) -> list[float]:
    try:
        return [float(value) for value in text.split(",")]
    except ValueError:
        raise GrblError(f"the controller's {field} is not numbers: {text!r}") from None


class StatusParser:
    """Status reports into readings. It keeps the last work offset, which GRBL sends only now and then."""

    def __init__(self, *, units: str = "mm") -> None:
        self.scale = INCH if units == "inch" else 1.0
        self.assumed = () if units == "inch" else (
            "GRBL reports in millimetres or inches by its $13 setting, which watching never asks; "
            "this takes millimetres. Add ?units=inch to the address if it is set to inches.",)
        self.offset: list[float] | None = None

    def parse(self, report: str) -> Reading | None:
        """One ``<...>`` report as a reading; None for a work position before any work offset came."""
        text = report.strip()
        if not (text.startswith("<") and text.endswith(">")):
            raise GrblError(f"not a GRBL status report: {text[:80]!r}")
        fields = text[1:-1].split("|")
        word = fields[0]
        state = _STATES.get(word.split(":")[0])
        if state is None:
            raise GrblError(f"GRBL reported a state it does not have: {word!r}")
        values = {}
        for entry in fields[1:]:
            name, _, value = entry.partition(":")
            values[name] = value
        if "WCO" in values:
            self.offset = _numbers(values["WCO"], "work offset")
        if "MPos" in values:
            machine = _numbers(values["MPos"], "machine position")
        elif "WPos" in values:
            if self.offset is None:
                return None
            work = _numbers(values["WPos"], "work position")
            if len(work) != len(self.offset):
                raise GrblError("the controller's work position and work offset have different axes")
            machine = [w + o for w, o in zip(work, self.offset)]
        else:
            raise GrblError(f"the status report has no position: {text[:80]!r}")
        if len(machine) > len(AXES):
            raise GrblError(f"the controller reported {len(machine)} axes; a machine has at most {len(AXES)}")
        # GRBL's axes are X Y Z then, on grblHAL and FluidNC, A B C (U V W after them on some builds).
        letters = ("X", "Y", "Z", "A", "B", "C", "U", "V", "W")[:len(machine)]
        axes = {letter: (value if letter in ("A", "B", "C") else value * self.scale)
                for letter, value in zip(letters, machine)}
        feed = spindle = None
        if "FS" in values:
            numbers = _numbers(values["FS"], "feed and speed")
            feed = numbers[0] * self.scale
            spindle = numbers[1] if len(numbers) > 1 else None
        elif "F" in values:
            feed = _numbers(values["F"], "feed")[0] * self.scale
        line = None
        if "Ln" in values:
            try:
                line = int(values["Ln"])
            except ValueError:
                raise GrblError(f"the controller's line number is not a number: {values['Ln']!r}") from None
        return Reading(axes=axes, state=state, detail=word, feed=feed, spindle=spindle, line=line, assumed=self.assumed)


class GrblReader:
    """A GRBL-family controller at ``address`` (``grbl://host[:port]``, telnet's 23 unless told)."""

    def __init__(self, address, *, timeout: float = 2.0) -> None:
        self.address, self.timeout = address, timeout
        self.parser = StatusParser(units=address.options.get("units", "mm"))
        self.sock: socket.socket | None = None
        self.buffer = b""

    def open(self) -> None:
        self.sock = socket.create_connection((self.address.host, self.address.port), timeout=self.timeout)
        self.buffer = b""

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def read(self) -> Reading | None:
        """Ask once (``?``) and answer the first status report that comes back; None while the reading
        waits for a work offset. Everything else the controller says between is let pass."""
        if self.sock is None:
            raise GrblError("not connected")
        self.sock.sendall(b"?")
        deadline = time.monotonic() + self.timeout
        while True:
            start = self.buffer.find(b"<")
            end = self.buffer.find(b">", start) if start >= 0 else -1
            if end >= 0:
                report, self.buffer = self.buffer[start:end + 1], self.buffer[end + 1:]
                return self.parser.parse(report.decode("ascii", "replace"))
            if start < 0:
                self.buffer = b""  # nothing in it is part of a report
            if len(self.buffer) > 4096:
                raise GrblError("the controller sent a status report longer than any GRBL sends")
            left = deadline - time.monotonic()
            if left <= 0:
                raise GrblError(f"no status report from {self.address.host} in {self.timeout:g} s: is it a GRBL controller?")
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(1024)
            except socket.timeout:
                continue
            if not chunk:
                raise GrblError(f"{self.address.host} closed the connection")
            self.buffer += chunk
