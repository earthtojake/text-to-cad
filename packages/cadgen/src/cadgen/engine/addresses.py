"""Document names: an on-disk CAD file's path, or a document's id, and the id each names.

Every verb, tool and ref names a document one of two ways: an on-disk CAD file by its path, or any
document by its id (``ids``) -- a model's, which ``python script.py`` prints, or a file's. A Python
script is never a document: nothing here reads, imports or builds one. A path is keyed by its
canonical spelling (``ids.canonical``); ``#owner/element`` selects geometry inside the document.
Nothing here reads, builds, or persists a model.
"""
from __future__ import annotations

import os
from pathlib import Path

from cadgen.engine.ids import canonical, file_id, is_id

__all__ = ["document_id", "is_id", "key", "split"]


def key(value: str | os.PathLike) -> Path | str:
    """A document's key: an id stays itself, a path is its canonical ``Path``."""
    text = os.fspath(value)
    if is_id(text):
        return text
    return Path(canonical(Path(text).expanduser()))


def document_id(value: str | os.PathLike) -> str:
    """The id of the document ``value`` names: an id itself, else the file's at that path."""
    text = os.fspath(value)
    return text if is_id(text) else file_id(Path(text).expanduser())


def split(value: str | os.PathLike) -> tuple[str, str | None]:
    """``FILE#REF`` as ``(the document's key, the ref)``; the ref None where there is no ``#``."""
    source, separator, ref = os.fspath(value).partition("#")
    return str(key(source)), ref if separator else None
