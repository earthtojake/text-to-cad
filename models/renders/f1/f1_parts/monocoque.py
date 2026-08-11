"""Survival cell, cockpit surround, halo — the car's central volume.

The geometry lives in two siblings so neither file is unreadable:

  * `mono_tub`  — the lofted carbon tub, its cockpit trough and rolled rim,
                  the roll-hoop blade and stays, the headrest shoulders and
                  the inboard suspension pickup fairings.
  * `mono_halo` — the titanium halo: central blade pillar, the continuous
                  side loop, and the three machined mounts.

Everything is built directly in car coordinates (spec's frame), so the
assembly is a flat list of correctly-placed children.
"""

from __future__ import annotations

from . import lib, mono_halo, mono_tub


def build_monocoque():
    """The survival cell: tub, cockpit surround, roll structure, pickups."""
    return lib.group("monocoque", mono_tub.build_tub_bodies())


def build_halo():
    """The halo: one continuous titanium loop on a blade pillar."""
    return lib.group("halo", mono_halo.build_halo_bodies())
