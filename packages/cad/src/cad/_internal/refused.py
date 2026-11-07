"""An argument refused by name before anything ran: the one class a function of the library raises for a
value its caller gave that it does not take -- an option out of range, one of another process -- so the
server's ``cad`` command says it as the command line's mistake (exit 2, ``invalid_argument``), as it says
a value its parser refuses, and never as a failure of the work. The standard library alone."""

from __future__ import annotations

__all__ = ["ArgumentRefused"]


class ArgumentRefused(ValueError):
    """A value refused by name, its words naming the option a command line gives it by (``--process``)."""
