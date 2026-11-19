"""A GSL model's field, made for the page with omega's ``gsl`` and kept by the model's bytes: what the viewer's
``field`` route answers (``cad_server.viewer.fields``).

The shader library is written by ``cad.omega._shader``, run here where this environment holds omega-core (a
checkout's), else with the Python of ``cad[omega]``'s environment, made on first need. What it wrote is kept on
disk under cad's cache (``omega/fields/<key>/``: ``payload.json`` and each texture's file), so the engine's next
start answers the same bytes without asking gsl again. ``key`` is the model's bytes and the bytes of the files it
imports, and this code's; a refusal is kept in memory alone, by the route.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from cad._internal.atomic_replace import replace_atomic

__all__ = ["SCHEMA", "folder", "key", "made", "shader"]

#: The payload's version, part of its key: raised when what is asked of gsl, or what is kept, changes.
SCHEMA = 1
_TIMEOUT = 300


def key(model: Path | str) -> str:
    """What a model's field is kept under: its bytes and those of the files it imports (``cad.omega._mesh.key``)."""
    from cad.omega._mesh import key as made_of

    return made_of(Path(model), "", None, f"field/{SCHEMA}")


def folder(field_key: str) -> Path:
    """Where the field of that key is kept."""
    from cad.engine.places import cache_dir

    return cache_dir() / "omega" / "fields" / field_key


def shader(model: Path, out_dir: Path) -> dict[str, Any]:
    """``cad.omega._shader.payload`` where omega-core is: in this process, or in ``cad[omega]``'s environment.
    ``cad.omega._shader.ShaderRefused`` in gsl's words when it writes none."""
    from cad.omega._shader import ShaderRefused
    from cad_server._internal import integration_env

    if integration_env.carries("omega"):
        from cad.omega._program import OmegaMissingError
        from cad.omega._shader import payload

        try:
            return payload(model, out_dir)
        except OmegaMissingError as error:
            raise ShaderRefused(str(error)) from None
    python = integration_env.environment("omega", lambda _line: None, engine=False)
    try:
        done = subprocess.run([python, "-P", "-m", "cad.omega._shader", str(model), str(out_dir)],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise ShaderRefused(f"gsl did not write the field in {_TIMEOUT} s") from None
    if done.returncode != 0:
        said = [line for line in done.stderr.splitlines() if line.strip()]
        raise ShaderRefused(said[-1] if said else f"gsl's shader exited {done.returncode}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def made(model: Path, field_key: str, write=None) -> bytes:
    """The field's payload as the route answers it (JSON, UTF-8): what is kept under ``field_key``, else made
    now with ``write`` (``shader``, or a test's stand-in) and kept. Each texture is named by its file in
    ``folder(field_key)``."""
    kept = folder(field_key)
    record = kept / "payload.json"
    try:
        return record.read_bytes()
    except OSError:
        pass
    kept.mkdir(parents=True, exist_ok=True)
    found = (write or shader)(Path(model), kept)
    textures = [{key: value for key, value in texture.items() if key != "file"} | {"name": texture["file"]}
                for texture in found.get("textures") or ()]
    body = json.dumps({"schema": SCHEMA, "key": field_key, **{k: v for k, v in found.items() if k != "textures"},
                       "textures": textures}, separators=(",", ":")).encode("utf-8")
    # The record last: one that is there names textures that are.
    making = kept / "payload.json.making"
    making.write_bytes(body)
    replace_atomic(making, record)
    return body
