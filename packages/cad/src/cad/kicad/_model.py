"""A saved board in 3D as KiCad draws it, for the CAD Viewer's 3D view: its body, its copper (tracks, vias,
pads and zones), its silkscreen and solder mask, and its parts' 3D models, as one binary glTF.

``model(board, out_dir)`` runs ``kicad-cli pcb export glb`` with the finder and the private environment every
export uses (``_program.ready``, ``_program.private_run``), with ``FLAGS``: what ``cad kicad_pcb export --to
glb`` writes (the body and the parts, STEP models substituted for VRML ones) and the board's copper, silkscreen
and solder mask, which KiCad's own 3D viewer draws. The board is read where it is, so a model a footprint
names relative to the project (``${KIPRJMOD}``) is found; nothing beside it is left changed
(``project_as_found``). A part whose model file is not found (kicode carries none of KiCad's libraries) is
drawn as KiCad draws it: not at all; ``missing`` names them, and ``modelled`` the parts the file holds a body
of, each glTF node of a part named by its reference (``U3``).

``python -m cad.kicad._model BOARD OUT_DIR`` runs it for the engine, in the environment of ``cad[kicad]``,
and prints ``{"glb", "modelled", "missing"}`` as one JSON line; a failure is said on stderr, exit status 1.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from ._export import _step_written, missing_parts
from ._program import KicadRunError, private_run, project_as_found, ready
from ._program import quiet as _quiet

__all__ = ["FLAGS", "MODEL_SECONDS", "model", "part_nodes"]

#: What the 3D view draws beside the body and the parts: KiCad's 3D viewer's copper, silkscreen and mask.
FLAGS = ("--subst-models", "--include-tracks", "--include-pads", "--include-zones", "--include-silkscreen",
         "--include-soldermask")
#: How long kicad-cli may take to write a board's 3D model (a large board takes a minute).
MODEL_SECONDS = 900.0


def part_nodes(glb: bytes) -> list[str]:
    """The names of a KiCad GLB's part nodes: the children of its scene's root that carry a name, each a
    footprint's reference (``U3``); the board's own meshes have none."""
    # The first chunk of a binary glTF is its JSON (the container's header is the GLB writer's to declare).
    if len(glb) < 20 or glb[16:20] != b"JSON":
        return []
    length = struct.unpack_from("<I", glb, 12)[0]
    try:
        gltf = json.loads(glb[20:20 + length])
    except ValueError:
        return []
    nodes = gltf.get("nodes") or []
    scenes = gltf.get("scenes") or [{}]
    names: list[str] = []
    for root in scenes[int(gltf.get("scene") or 0)].get("nodes") or ():
        for child in (nodes[root].get("children") or ()) if root < len(nodes) else ():
            name = str(nodes[child].get("name") or "") if child < len(nodes) else ""
            if name and not name.startswith("=>") and name not in names:
                names.append(name)
    return names


def model(board: Path | str, out_dir: Path | str, *, cli: Path | None = None,
          timeout: float = MODEL_SECONDS) -> dict[str, Any]:
    """``board`` in 3D (the module) written into ``out_dir`` as ``<board>.glb``: ``{"glb", "modelled",
    "missing"}``. Raises :class:`KicadRunError` when kicad-cli cannot run or refuses the board."""
    board, out_dir = Path(board).resolve(), Path(out_dir).resolve()
    if board.suffix.lower() != ".kicad_pcb" or not board.is_file():
        raise KicadRunError(f"{board} is not a saved KiCad board (.kicad_pcb)")
    if cli is None:
        cli = ready()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{board.stem}.glb"
    command = [str(cli), "pcb", "export", "glb", *FLAGS, "--force", "-o", str(out), str(board)]
    with private_run("cad-model-", cli) as (_scratch, env), project_as_found(board):
        try:
            completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                       timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise KicadRunError(f"kicad-cli pcb export glb did not finish in {timeout:g} s") from None
        except OSError as error:
            raise KicadRunError(f"kicad-cli could not be started ({error})") from None
    if (completed.returncode != 0 and not _step_written("glb", completed, out)) or not out.is_file():
        said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
        raise KicadRunError(f"kicad-cli pcb export glb failed on {board}: {said}")
    return {"glb": str(out), "modelled": part_nodes(out.read_bytes()),
            "missing": missing_parts(f"{completed.stdout}\n{completed.stderr}")}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m cad.kicad._model BOARD OUT_DIR", file=sys.stderr)
        return 2
    try:
        made = model(args[0], args[1])
    except Exception as error:  # noqa: BLE001 - said to the engine in one line
        print(str(error).strip().splitlines()[-1] if str(error).strip() else type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps(made, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
