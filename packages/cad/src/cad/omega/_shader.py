"""A GSL model's field as the page draws it: the shader library omega's ``gsl`` writes of it, as the CAD Viewer's
``field`` route answers (``cad_server.viewer.fields``).

A field is shown by marching it, with no mesh. ``gsl eval``'s ``shader`` (omega-core 0.1.2 or later) writes what a
page needs for that, in GLSL ES 3.00 for WebGL2: a library with no entry point that defines ``gsl_field(p)`` and
``gsl_march(...)`` (the first surface along a ray, as omega's own viewer marches), one uniform block carrying
time and the model's sliders, each with the byte it sits at, and the textures the field reads, as raw texels
written to a folder. ``payload`` asks for it and answers with it as plain data, each texture named by its file in
that folder and never by a path.

Run as ``python -P -m cad.omega._shader MODEL OUT_DIR`` in the environment of ``cad[omega]``, for a server whose own
environment does not hold omega-core: the payload is one line of JSON on stdout, a refusal gsl's words on stderr
with exit status 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["TARGET", "ShaderRefused", "main", "payload"]

#: The language the page's renderer is written in: WebGL2's.
TARGET = "glsl-es300"


class ShaderRefused(RuntimeError):
    """``gsl`` wrote no shader of the model: its words (a model that does not compile, a field that reads a
    texture it cannot write), or that this ``gsl`` has no such question."""


def _asked(gsl: Path, model: Path, out_dir: Path) -> dict[str, Any]:
    """``gsl eval``'s ``shader`` of ``model``, its textures written into ``out_dir``. Raises
    ``omega_core.EvalError`` in gsl's words."""
    import omega_core

    with omega_core.Session(source_paths=(model.parent,), program=str(gsl)) as session:
        return dict(session.request({"op": "shader", "source": str(model), "target": TARGET, "outDir": str(out_dir)}))


def payload(model: Path, out_dir: Path) -> dict[str, Any]:
    """The field of ``model`` for the page: gsl's answer, its textures in ``out_dir`` and named by their files
    there. ``ShaderRefused`` where gsl writes none, saying why; ``cad.omega._program.OmegaMissingError`` where
    there is no gsl to ask."""
    import omega_core

    from cad.omega._program import find_gsl

    model, out_dir = Path(model).absolute(), Path(out_dir).absolute()
    gsl = find_gsl()
    try:
        answer = _asked(gsl, model, out_dir)
    except omega_core.EvalError as error:
        said = str(error)
        if 'op "shader"' in said and "one of" in said:
            raise ShaderRefused(f"this gsl's eval has no shader ({gsl}), so the field cannot be drawn: set CAD_GSL "
                                "to the gsl of omega-core 0.1.2 or later") from None
        raise ShaderRefused(said) from None
    textures = []
    for texture in answer.get("textures") or ():
        named = {key: value for key, value in texture.items() if key != "path"}
        named["file"] = Path(str(texture.get("path", ""))).name
        textures.append(named)
    return {key: answer.get(key) for key in ("target", "code", "entry", "uniformBlock", "blockBytes", "uniforms",
                                             "sliders", "bodies", "region")} | {"textures": textures}


def main(argv: list[str] | None = None) -> int:
    from cad.omega._program import OmegaMissingError

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m cad.omega._shader MODEL OUT_DIR", file=sys.stderr)
        return 64
    try:
        found = payload(Path(args[0]), Path(args[1]))
    except (ShaderRefused, OmegaMissingError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(found, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
