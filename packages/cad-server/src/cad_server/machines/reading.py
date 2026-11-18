"""What a controller says of its machine, in one shape whatever the controller (``Reading``), and the
address that names a controller (``parse_address``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

# The machine's state, in the page's words; ``Reading.detail`` keeps the controller's own.
STATES = ("idle", "running", "paused", "alarm", "stopped")

# Each address's scheme, the protocol it names, and the port that protocol listens on unless told.
ADDRESS_SCHEMES = {"mtconnect": 5000, "linuxcnc": 5007, "grbl": 23}

# A machine's axes, as every controller here names them: linear X Y Z U V W in millimetres, rotary
# A B C in degrees.
LINEAR_AXES = ("X", "Y", "Z", "U", "V", "W")
ROTARY_AXES = ("A", "B", "C")
AXES = LINEAR_AXES + ROTARY_AXES


@dataclass(frozen=True)
class Reading:
    """The machine as its controller last reported it.

    ``axes``: each axis it reported, by its letter, in machine coordinates: millimetres for a linear
    axis, degrees for a rotary one. ``state``: one of ``STATES``; ``detail``: the controller's own word
    for it. ``feed`` (mm/min), ``spindle`` (rpm), ``line`` and ``program``: None where the controller
    does not say. ``assumed``: what the reader took as given because the controller does not say it,
    each in a sentence the page shows.
    """

    axes: dict[str, float]
    state: str
    detail: str
    feed: float | None = None
    spindle: float | None = None
    line: int | None = None
    program: str | None = None
    assumed: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"a machine's state is one of {', '.join(STATES)}, not {self.state!r}")
        unknown = sorted(set(self.axes) - set(AXES))
        if unknown:
            raise ValueError(f"a machine's axes are {' '.join(AXES)}, not {' '.join(unknown)}")

    def as_json(self) -> dict:
        return {"axes": dict(self.axes), "state": self.state, "detail": self.detail, "feed": self.feed,
                "spindle": self.spindle, "line": self.line, "program": self.program, "assumed": list(self.assumed)}


@dataclass(frozen=True)
class Address:
    """A controller's address: its protocol (the scheme), host, port, path and options."""

    protocol: str
    host: str
    port: int
    path: str
    options: dict[str, str]

    def __str__(self) -> str:
        query = "&".join(f"{key}={value}" for key, value in sorted(self.options.items()))
        return f"{self.protocol}://{self.host}:{self.port}{self.path}" + (f"?{query}" if query else "")


# The options each protocol's address takes (``?name=value``): a closed set each.
OPTIONS = {"mtconnect": {"device": None}, "linuxcnc": {"password": None}, "grbl": {"units": ("mm", "inch")}}


def parse_address(text: str) -> Address:
    """``text`` as a controller's address -- ``mtconnect://host[:port][/device]``,
    ``linuxcnc://host[:port]``, ``grbl://host[:port]`` -- or ``ValueError`` saying what one looks like."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("a machine's address is like mtconnect://192.168.1.20:5000, linuxcnc://mill.local or grbl://fluidnc.local")
    parts = urlsplit(text.strip())
    protocol = parts.scheme.lower()
    if protocol not in ADDRESS_SCHEMES:
        raise ValueError(f"a machine's address starts with {', '.join(f'{name}://' for name in ADDRESS_SCHEMES)}"
                         f", not {text.strip()!r}")
    if not parts.hostname:
        raise ValueError(f"{text.strip()!r} names no host")
    try:
        port = parts.port or ADDRESS_SCHEMES[protocol]
    except ValueError:
        raise ValueError(f"{text.strip()!r} has no port number after its host's colon") from None
    path = parts.path.rstrip("/")
    if path and protocol != "mtconnect":
        raise ValueError(f"a {protocol} address has no path: {text.strip()!r}")
    if parts.username or parts.password or parts.fragment:
        raise ValueError(f"a machine's address has no user, password or fragment: {text.strip()!r}")
    options: dict[str, str] = {}
    for name, values in parse_qs(parts.query, keep_blank_values=True).items():
        allowed = OPTIONS[protocol]
        if name not in allowed:
            named = ", ".join(allowed) or "none"
            raise ValueError(f"a {protocol} address takes the options {named}, not {name!r}")
        if len(values) != 1 or not values[0]:
            raise ValueError(f"the option {name!r} takes one value")
        if allowed[name] is not None and values[0] not in allowed[name]:
            raise ValueError(f"{name} is {' or '.join(allowed[name])}, not {values[0]!r}")
        options[name] = values[0]
    if protocol == "mtconnect" and path and "device" in options:
        raise ValueError("name an MTConnect device by the address's path or by ?device=, not both")
    if protocol == "mtconnect" and path:
        options["device"], path = path.lstrip("/"), ""
    return Address(protocol, parts.hostname, port, path, options)
