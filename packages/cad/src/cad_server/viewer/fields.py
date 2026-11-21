"""The field route's rules: ``GET /api/v1/documents/gsl/<id>/field`` and ``.../field/textures/<name>``.

A GSL model is drawn as its field, the page marching it: ``field`` is what the page marches it with, the shader
library omega's ``gsl`` writes of the model (``cad_server._internal.fields``), as JSON: ``{"schema", "key",
"target", "code", "entry", "uniformBlock", "blockBytes", "uniforms", "sliders", "textures", "bodies",
"region"}``. ``code`` is a GLSL ES 3.00 library with no entry point; ``uniforms`` and ``sliders`` say where each
value sits in the block, so a slider moves by writing one number, with no request; each of ``textures`` is read
as raw texels from the route beside this one, by its ``name``.

It is made off the request, one per key at a time (every request for that key joins it): a request waits on it
as long as ``hold_seconds``, then answers 202 ``{"state": "compiling", "retryMs"}`` and is asked again; gsl
never runs on a request's thread. The key is the model's bytes and the bytes of what it imports
(``fields.key``), worked out again whenever the file's ``mtime_ns``, size or inode differs, so a changed model
is a new key and nothing stale is answered. The last ``HELD`` answers are kept in memory by key, a refusal among
them (a model gsl does not compile is a 400 in gsl's words until the model changes); what gsl wrote is kept on
disk by the same key. Each 200 carries ``etag: "<key>"``; a request naming it (``If-None-Match``) is answered
304. A texture is read only by a name the kept payload gives, from that key's folder.
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .backend import absolute_path
from .scanner import node_basename

__all__ = ["HELD", "HOLD_SECONDS", "FieldAnswers"]

# How long a request waits on a field before it answers 202.
HOLD_SECONDS = 2.0
# Answers kept in memory, by key: a large model's shader is a few hundred kilobytes.
HELD = 12


class _Work:
    __slots__ = ("done", "status", "body")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.status = 500
        self.body: Any = {"error": "the field's work stopped before it finished"}


class FieldAnswers:
    """The field route's work, off the request, and the answers it made (see the module)."""

    def __init__(self, *, hold_seconds: float = HOLD_SECONDS, retry_ms: int = 0, on_crash=None, shader=None) -> None:
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self._on_crash = on_crash
        # ``shader`` stands in for gsl's in a test; the engine's is ``fields.shader``.
        self._shader = shader
        self._lock = threading.Lock()
        self._work: dict[str, _Work] = {}
        self._held: OrderedDict[str, _Work] = OrderedDict()
        self._keys: dict[str, tuple[tuple[int, int, int], str]] = {}

    @staticmethod
    def _model(file_ref) -> str | None:
        """The absolute ``.gsl`` this ref names, or None for a 404; ``ValueError`` for a ref the route will not
        take."""
        if not file_ref:
            raise ValueError("a field is read from the absolute path of a .gsl")
        candidate = absolute_path(file_ref)
        if not candidate.lower().endswith(".gsl"):
            raise ValueError(f"a field is a .gsl's; {node_basename(candidate)} is not one")
        return candidate if os.path.isfile(candidate) else None

    def key(self, path: str) -> str:
        """The model's key (``fields.key``), worked out again when its stat changes."""
        from cad_server._internal.fields import key

        info = os.stat(path)
        stamp = (info.st_ino, info.st_size, info.st_mtime_ns)
        known = self._keys.get(path)
        if known is not None and known[0] == stamp:
            return known[1]
        found = key(path)
        self._keys[path] = (stamp, found)
        return found

    def response(self, file_ref, *, if_none_match: str = "") -> tuple[int, Any, str]:
        """``(status, body, key)``: the field's ``compressed.Coded`` at 200, 304 for the key the client named,
        202 while it is made, or a JSON error dict."""
        candidate = self._model(file_ref)
        if candidate is None:
            return 404, {"error": "Not found"}, ""
        try:
            field_key = self.key(candidate)
        except OSError as error:
            return 400, {"error": f"{node_basename(candidate)} could not be read ({error}); "
                                  "check that it is a file this user may read"}, ""
        if if_none_match and if_none_match.strip() in (f'"{field_key}"', f'W/"{field_key}"'):
            return 304, b"", field_key
        with self._lock:
            work = self._held.get(field_key)
            if work is not None:
                self._held.move_to_end(field_key)
                return work.status, work.body, field_key
            work = self._work.get(field_key)
            if work is None:
                work = self._work[field_key] = _Work()
                threading.Thread(target=self._make, args=(work, field_key, Path(candidate)), name="cad-field",
                                 daemon=True).start()
        if work.done.wait(self.hold_seconds):
            return work.status, work.body, field_key
        return 202, {"state": "compiling", "retryMs": self.retry_ms}, field_key

    def texture(self, file_ref, name: str) -> str | None:
        """The file of the texture ``name`` of this model's field as it is now, or None: one the kept payload
        names, in its key's folder, and nothing else (no other file there, no path)."""
        from cad_server._internal.fields import folder

        candidate = self._model(file_ref)
        if candidate is None or not name:
            return None
        try:
            kept = folder(self.key(candidate))
            named = {texture.get("name") for texture in json.loads((kept / "payload.json").read_bytes())["textures"]}
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if name not in named:
            return None
        found = kept / name
        return str(found) if found.parent == kept and found.is_file() else None

    def _make(self, work: _Work, field_key: str, model: Path) -> None:
        from cad.omega._shader import ShaderRefused
        from cad_server._internal.fields import made

        from .compressed import Coded

        keep = True
        try:
            work.status, work.body = 200, Coded(made(model, field_key, self._shader))
        except ShaderRefused as error:
            work.status, work.body = 400, {"error": str(error)}
        except Exception as error:  # noqa: BLE001 - answered as the GET funnel answers a route's bug
            keep = False
            if self._on_crash is not None:
                self._on_crash(error)
            work.status, work.body = 400, {"error": str(error) or type(error).__name__}
        finally:
            with self._lock:
                self._work.pop(field_key, None)
                if keep:
                    self._held[field_key] = work
                    while len(self._held) > HELD:
                        self._held.popitem(last=False)
            work.done.set()
