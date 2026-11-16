"""Galatea's neck and head on their own: the page to study the face on."""

from cad import model

from lib.hardware import Hardware
from lib.head import build_head
from lib.kit import group


@model
def galatea_head():
    links = build_head(Hardware(), [])
    return group("galatea_head", [group(name, parts) for name, parts in links.items() if parts])


if __name__ == "__main__":
    galatea_head()
