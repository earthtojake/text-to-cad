"""A command's words in UTF-8 on Windows, wherever they go to a pipe or a file.

Python on Windows writes a standard stream that is no console in the ANSI code page (cp1252 and the like), and
whatever reads a command's output there -- an agent, a log, Git Bash -- reads UTF-8: a profile folder
``C:\\Users\\José`` arrived as ``Jos?``, and a ``·`` or a ``—`` as a replacement character. So the ``cad`` command,
and the programs ``cad run`` runs, write such a stream in UTF-8 (``switches``, ``utf8``). A console is left as it is
(Python writes it through the console's own Unicode API), as is every stream on other systems; only the streams'
encoding changes, never how a program opens files (that would be ``PYTHONUTF8``'s), and nothing is handed on to the
processes a program starts.

ENTRY POINTS ONLY: the standard streams are the process's, owned by whoever embedded the library, so a program's own
entry point calls this, never an import.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def switches(stream: Any, system: str = os.name) -> bool:
    """Whether ``stream`` is written in UTF-8 from here on: on Windows (``system``, ``os.name``), one that is no
    console."""
    if system != "nt":
        return False
    try:
        return not stream.isatty()
    except (AttributeError, OSError, ValueError):  # no stream (``pythonw``), or a closed one: nothing to write
        return False


def utf8(system: str = os.name) -> None:
    """The standard output and error written in UTF-8 where ``switches`` says so, each keeping its error handler."""
    for stream in (sys.stdout, sys.stderr):
        if not switches(stream, system):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors=stream.errors)
        except (AttributeError, OSError, ValueError):  # an object of a caller's own, or detached
            pass
