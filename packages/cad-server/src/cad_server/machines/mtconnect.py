"""A machine an MTConnect agent publishes, read by the agent's ``probe`` and ``current`` requests.

MTConnect (https://www.mtconnect.org, the standard's Part 2 for devices and Part 3 for streams) is
read-only by design: an agent serves what its adapters report, over HTTP, to any number of clients.
The reader asks the agent's ``probe`` once, for the device's axes and the data items each has, then its
``current`` each time it reads. An axis is a ``Linear`` or ``Rotary`` component by its name (X, Y, Z,
A, B, C ...); its value is its ``POSITION`` (linear, millimetres) or ``ANGLE`` (rotary, degrees),
the actual one in machine coordinates where the device has it, else the actual one it has. A rotary
component that is a spindle (its rotary mode ``SPINDLE``, or named like one) is the spindle's speed,
never an axis.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree

from .reading import AXES, Reading

_LIMIT = 4 * 1024 * 1024

_EXECUTION = {"READY": "idle", "ACTIVE": "running", "INTERRUPTED": "paused", "FEED_HOLD": "paused",
              "OPTIONAL_STOP": "paused", "PROGRAM_STOPPED": "paused", "PROGRAM_COMPLETED": "idle",
              "STOPPED": "stopped", "WAIT": "paused"}


class MtconnectError(ConnectionError):
    """What the agent answered, or did not, that leaves no reading."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class Probe:
    """The data items of one device the reader reads, from a probe document."""

    def __init__(self, document: bytes, device: str | None) -> None:
        root = ElementTree.fromstring(document)
        if _local(root.tag) == "MTConnectError":
            raise MtconnectError(f"the agent refused its probe: {_error_text(root)}")
        devices = [element for element in root.iter() if _local(element.tag) == "Device"]
        if not devices:
            raise MtconnectError("the agent's probe names no device")
        if device is None:
            if len(devices) > 1:
                names = ", ".join(sorted(element.get("name") or "?" for element in devices))
                raise MtconnectError(f"the agent publishes several devices ({names}): name one in the address, mtconnect://host/<device>")
            chosen = devices[0]
        else:
            matches = [element for element in devices if device in (element.get("name"), element.get("uuid"))]
            if not matches:
                names = ", ".join(sorted(element.get("name") or "?" for element in devices))
                raise MtconnectError(f"the agent publishes no device {device!r}: it has {names}")
            chosen = matches[0]
        self.device = chosen.get("name") or device or ""
        # id -> (what it is, its axis or None, its units)
        self.items: dict[str, tuple[str, str | None, str | None]] = {}
        candidates: dict[str, list[tuple[int, str, str | None]]] = {}
        self._walk(chosen, None, None, candidates)
        # Each axis's position: machine coordinates and actual first, then actual, then any.
        for axis, found in candidates.items():
            found.sort()
            rank, ident, units = found[0]
            self.items[ident] = ("axis", axis, units)

    def _walk(self, element, component, axis, candidates) -> None:
        kind = _local(element.tag)
        if kind in ("Linear", "Rotary"):
            name = (element.get("name") or "").upper()
            spindle = kind == "Rotary" and (name in ("S", "SPINDLE") or name.startswith("S") and name[1:].isdigit()
                                             or _rotary_mode(element) == "SPINDLE")
            component, axis = ("spindle" if spindle else kind), (None if spindle else name)
        for child in element:
            tag = _local(child.tag)
            if tag == "DataItems":
                for data in child:
                    if _local(data.tag) == "DataItem":
                        self._item(data, component, axis, candidates)
            elif tag == "Components":
                for inner in child:
                    self._walk(inner, component, axis, candidates)

    def _item(self, data, component, axis, candidates) -> None:
        ident, kind = data.get("id"), (data.get("type") or "").upper()
        sub = (data.get("subType") or "").upper()
        units = data.get("units")
        if not ident:
            return
        if axis in AXES and ((component == "Linear" and kind == "POSITION") or (component == "Rotary" and kind == "ANGLE")):
            if sub not in ("", "ACTUAL"):
                return
            system = (data.get("coordinateSystem") or "").upper()
            rank = (0 if system == "MACHINE" else 1 if not system else 2) * 2 + (0 if sub == "ACTUAL" else 1)
            candidates.setdefault(axis, []).append((rank, ident, units))
        elif kind == "EXECUTION":
            self.items.setdefault(ident, ("execution", None, None))
        elif kind == "EMERGENCY_STOP":
            self.items.setdefault(ident, ("estop", None, None))
        elif kind == "PATH_FEEDRATE" and sub in ("", "ACTUAL"):
            self.items.setdefault(ident, ("feed", None, units))
        elif component == "spindle" and kind in ("ROTARY_VELOCITY", "SPINDLE_SPEED") and sub in ("", "ACTUAL"):
            self.items.setdefault(ident, ("spindle", None, None))
        elif kind == "PROGRAM":
            self.items.setdefault(ident, ("program", None, None))
        elif kind in ("LINE_NUMBER", "LINE"):
            self.items.setdefault(ident, ("line", None, None))


def _rotary_mode(element) -> str:
    for item in element.iter():
        if _local(item.tag) == "DataItem" and (item.get("type") or "").upper() == "ROTARY_MODE":
            for constraint in item.iter():
                if _local(constraint.tag) == "Value" and constraint.text:
                    return constraint.text.strip().upper()
    return ""


def _error_text(root) -> str:
    return "; ".join((element.text or "").strip() for element in root.iter() if _local(element.tag) in ("Error", "ErrorMessage")) or "no reason given"


def parse_current(document: bytes, probe: Probe) -> Reading:
    """A ``current`` document as the reading of ``probe``'s device."""
    root = ElementTree.fromstring(document)
    if _local(root.tag) == "MTConnectError":
        raise MtconnectError(f"the agent refused its current: {_error_text(root)}")
    axes: dict[str, float] = {}
    state, detail, feed, spindle, line, program, estop = None, "", None, None, None, None, False
    for element in root.iter():
        ident = element.get("dataItemId")
        if ident not in probe.items:
            continue
        what, axis, units = probe.items[ident]
        text = (element.text or "").strip()
        if text.upper() == "UNAVAILABLE":
            continue
        if what == "axis":
            value = _number(text)
            if value is None:
                raise MtconnectError(f"axis {axis}'s position is not a number: {text[:40]!r}")
            expected = "DEGREE" if axis in ("A", "B", "C") else "MILLIMETER"
            if units and units.upper() != expected:
                raise MtconnectError(f"axis {axis} is in {units}; MTConnect's positions are in {expected}")
            axes[axis] = value
        elif what == "execution":
            word = text.upper()
            if word not in _EXECUTION:
                raise MtconnectError(f"the agent reported an execution state MTConnect does not have: {text!r}")
            state, detail = _EXECUTION[word], word
        elif what == "estop":
            estop = text.upper() == "TRIGGERED"
        elif what == "feed":
            value = _number(text)
            per_second = (units or "MILLIMETER/SECOND").upper() == "MILLIMETER/SECOND"
            feed = None if value is None else value * 60 if per_second else value
        elif what == "spindle":
            spindle = _number(text)
        elif what == "line":
            number = _number(text)
            line = int(number) if number is not None else None
        elif what == "program":
            program = text or None
    if estop:
        state, detail = "alarm", "EMERGENCY_STOP"
    if state is None:
        # A device with no execution state says nothing of what it is doing; the reading says so.
        state, detail = "idle", "no execution state"
    assumed = () if detail != "no execution state" else ("The agent reports no execution state for this device, so it is shown as idle.",)
    return Reading(axes=axes, state=state, detail=detail, feed=feed, spindle=spindle, line=line, program=program, assumed=assumed)


class MtconnectReader:
    """The device an MTConnect agent at ``address`` publishes (``mtconnect://host[:port][/device]``)."""

    def __init__(self, address, *, timeout: float = 2.0) -> None:
        self.address, self.timeout = address, timeout
        self.probe: Probe | None = None
        device = address.options.get("device")
        self.base = f"http://{address.host}:{address.port}"
        self.prefix = f"{self.base}/{urllib.request.quote(device)}" if device else self.base

    def _get(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"accept": "application/xml"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:  # noqa: S310 -- http to the address the person gave
                body = answer.read(_LIMIT + 1)
        except urllib.error.HTTPError as error:
            raise MtconnectError(f"the agent answered {error.code} for {url}") from None
        except (urllib.error.URLError, OSError) as error:
            raise MtconnectError(f"cannot reach the agent at {self.base}: {getattr(error, 'reason', error)}") from None
        if len(body) > _LIMIT:
            raise MtconnectError("the agent's answer is larger than any device's")
        return body

    def open(self) -> None:
        try:
            self.probe = Probe(self._get(f"{self.prefix}/probe"), self.address.options.get("device"))
        except ElementTree.ParseError as error:
            raise MtconnectError(f"the agent's probe is not XML: {error}") from None
        if not any(what == "axis" for what, _, _ in self.probe.items.values()):
            raise MtconnectError(f"device {self.probe.device!r} reports no axis position")

    def close(self) -> None:
        self.probe = None

    def read(self) -> Reading:
        if self.probe is None:
            raise MtconnectError("not connected")
        try:
            return parse_current(self._get(f"{self.prefix}/current"), self.probe)
        except ElementTree.ParseError as error:
            raise MtconnectError(f"the agent's current is not XML: {error}") from None
