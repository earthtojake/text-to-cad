"""A machine tool's live position, read off its controller over the network, for the viewer to mirror.

A machine's twin is a model whose mechanism has a joint per machine axis; the page poses it where the
controller says the machine is. This package is the reading half: one module per controller's own
protocol, each opened by an address whose scheme names it (``ADDRESS_SCHEMES``), each answering a
``Reading`` (``reading.py``), and the watches the viewer's routes keep (``watch.py``).

Watching never commands a machine. Every reader sends only what its protocol defines as a read: an
MTConnect agent's ``probe`` and ``current`` (``mtconnect.py``), LinuxCNC's ``linuxcncrsh`` ``get``s and
its session's own unit setting (``linuxcnc.py``), and GRBL's real-time status query, ``?``, which by
design never enters the planner (``grbl.py``). A controller that shares one serial port with the program
running it (a USB GRBL board) cannot be watched this way: opening the port takes it from that program,
and on many boards resets the controller. Those are left out on purpose, not by oversight.
"""

from .reading import ADDRESS_SCHEMES, STATES, Reading, parse_address

__all__ = ["ADDRESS_SCHEMES", "STATES", "Reading", "parse_address"]
