"""Whose an error is to fix: the person's, or cadgen's. One rule, by class.

**An error is the person's if it is a ``UserError``. Every other error is cadgen's.**

- ``CadError`` is the base of every error cadgen raises on purpose. It is never raised itself.
- ``UserError``: the person must change their model, their input or their request to fix it -- a
  refusal (``ExportRefused``, ``SnapshotRefused``, ``FormatError`` ...), said by name, before
  anything is written. cadgen code that takes what the person gave it -- a value, a colour, a path, a
  file -- checks it and raises a ``UserError`` saying what is wrong; it never lets the value fail a later
  line.
- ``InternalError``: cadgen's own code reached a state it cannot go on from -- an "impossible" branch,
  a dependency mechanism it pins that is gone. Raise it where you would have raised ``RuntimeError``
  or written ``assert`` about cadgen's own state.

A refusal keeps the built-in class it always had beside ``UserError``
(``class ExportRefused(UserError, ValueError)``), so code that catches ``ValueError`` still catches it.

``owner`` applies the rule. It answers ``None`` for an error that is no ``CadError`` -- one Python
raised, or another library, or the person's own code -- and the caller decides those by its fallback:
the server's frame rule (``cad_server.analytics.told_signature``), which reads where the error was
raised. That fallback shrinks as cadgen's plain ``raise ValueError`` and ``raise RuntimeError`` become
``UserError`` and ``InternalError``; the ``CadError`` answer always comes first.

Where it is read: a failed build's report carries ``owner`` (``cad.engine.build``); the daemon's page
record carries ``reportable`` from it, which decides the Report Issue button; and the server's
telemetry counts a crash by the same answer. The standard library alone: a model imports this, and so
does every process of the server.
"""

from __future__ import annotations

from typing import Literal

__all__ = ["CadError", "InternalError", "Owner", "UserError", "owner"]

Owner = Literal["user", "ours"]


class CadError(Exception):
    """Every error cadgen raises on purpose. Never raised itself: raise a ``UserError`` or an
    ``InternalError``."""


class UserError(CadError):
    """The person's to fix: their model, their input or their request. Its message says what is wrong
    and, where it can, what to do instead."""


class InternalError(CadError):
    """cadgen's to fix: its own code reached a state it cannot go on from."""


def owner(error: BaseException) -> Owner | None:
    """Whose ``error`` is to fix by its class: ``"user"`` for a ``UserError``, ``"ours"`` for any other
    ``CadError``, ``None`` for an error that is no ``CadError`` (the caller's fallback decides it)."""
    if isinstance(error, UserError):
        return "user"
    if isinstance(error, CadError):
        return "ours"
    return None
