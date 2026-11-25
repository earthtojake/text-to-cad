"""Galatea's left leg on its own, hip yaw actuator included: the page to study the leg's mechanics on."""

from cad import model

from lib.hardware import Hardware
from lib.kit import group
from lib.leg import build_leg


@model
def galatea_leg():
    links = build_leg(Hardware())
    return group("galatea_leg", [group(name, parts) for name, parts in links.items() if parts])


if __name__ == "__main__":
    galatea_leg()
