"""Specctra DSN and SES: a KiCad board as the routing problem Freerouting reads, and its answer.

Freerouting, the open-source autorouter KiCad users run, reads a board as a
Specctra design file (DSN) and answers with a Specctra session (SES): the wires
and vias it added. ``kicad-cli`` has no DSN export, so :func:`board_dsn` writes
the DSN itself, from a board tree in KiCad 10's format and the project's net
classes, and :func:`read_session` reads the session back as KiCad tracks and
vias, which :func:`with_routes` adds to the board. Nothing here runs a program
(:mod:`cadgen.kicad.route` runs Freerouting); every function is pure, so the
same board always writes the same DSN.

Frame
-----
DSN coordinates are micrometres, y up, from the board's drill/place origin --
the board script's own (0, 0): a KiCad point ``(x, y)`` mm is
``(1000 (x - ox), 1000 (oy - y))`` µm. The resolution is a tenth of a
micrometre, so the session's integers are tenths of a micrometre and come back
to KiCad's nanometres exactly.

Names
-----
Freerouting's reader splits a pin reference at its first ``-``, strips any
``.<digits>`` from a padstack name and reads a tab as part of a name, so no
spelling of the board's own goes into the file: nets, parts, pins, padstacks,
images and classes get aliases of letters, digits, ``_`` and ``@``
(``N3_GND``, ``R1``, ``@4``), and the :class:`Dsn` keeps the way back.

What goes in
------------
- the copper layers, front to back;
- the outline (``Edge.Cuts``, a footprint's included) as the boundary, kept the
  board's edge clearance from copper;
- each footprint as an image seen from the top, placed ``back`` and turned
  180 degrees more when it sits on the bottom (how KiCad's own exporter places
  a flipped footprint), its pads as padstacks;
- every net with two or more pads, less the nets asked to stay unrouted, in its
  net class: track width, clearance (never under the board's minimum) and via;
- every other obstacle to tracks as a pin of no net on a locked part: a hole in
  the outline (kept the edge clearance), an unplated hole (grown by the hole
  clearance), a keepout zone that forbids tracks, copper drawn or written on a
  copper layer. Freerouting 2.4's search keeps a keepout's bare clearance while
  its trace insertion asks a little more, so a route that hugs a keepout is
  found and then refused; around a pin the two agree. A zone that forbids only
  vias is a via keepout;
- the board's own tracks and vias as fixed wiring: Freerouting continues from
  them and routes around them, and never moves one.

A shape Freerouting has no word for is written larger than it is, never
smaller: a rounded or oval pad as a polygon outside its curve, an arc of the
outline on the side away from the copper, an arc track as a wider polyline.
Every clearance is written :data:`MARGIN` above the board's. KiCad's DRC runs
on the routed board and judges the result; an approximation only ever costs
the router room.
"""

from __future__ import annotations

from cadgen.kicad.specctra.dsn import MARGIN, RESOLUTION, Dsn, ViaKind, board_dsn
from cadgen.kicad.specctra.session import RoutedTrack, RoutedVia, Routes, SessionError, read_session, with_routes
from cadgen.kicad.specctra.shapes import DsnFrame

__all__ = [
    "MARGIN",
    "RESOLUTION",
    "Dsn",
    "DsnFrame",
    "RoutedTrack",
    "RoutedVia",
    "Routes",
    "SessionError",
    "ViaKind",
    "board_dsn",
    "read_session",
    "with_routes",
]
