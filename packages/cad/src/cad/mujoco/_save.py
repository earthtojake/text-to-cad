"""``save``: an ``MjSpec`` written as a folder that travels, by MuJoCo's own writer.

A MuJoCo function returns a spec; ``save(spec, path)`` writes it where a person keeps it. A spec ``spec``
made names its files by absolute path (``_spec``: what a scene attaches and compiles anywhere on this
computer), so the file alone would not travel. ``save`` writes the folder MuJoCo Menagerie ships:

- ``path``, the MJCF, as MuJoCo writes it (``MjSpec.to_xml``: its own layout, about six significant
  digits), its ``compiler`` naming ``meshdir`` ``assets`` (and ``texturedir``, where it has a texture file);
- ``assets/``, beside it, a copy of every file the spec names (meshes, textures, heightfields), each by its
  bare name (a second file of one name takes ``_2``);
- ``scene.xml``, beside it, where there is none and the spec has no floor of its own (no plane geom on its
  world body: a robot, not a scene): the export's scene (``mjcf.scene_around``: a floor, a light and the robot
  framed at zero), never written over. A scene function's spec, which has its floor, gets none.

**It works on a copy.** The spec handed in is left as it was, its files still named where they are, so a
scene that attaches a robot's spec after saving it compiles as it did before (``MjSpec.copy``). The copy is
made one spec (``_flat``: compiled to MuJoCo's text and read back), so a scene's attached robots are saved with
it: a child's files resolve against the child's own folders, which the copy's ``meshdir`` does not reach. Its
files are named bare, its folders set (``meshdir`` and ``texturedir`` ``assets``, ``modelfiledir`` the folder
it is staged in), and it is compiled before anything is moved into place: MuJoCo's ``ValueError``, in its own
words, is raised for a spec it refuses, and nothing is written. Where its words are that a file does not open,
the error adds the usual cause: a child read with ``MjSpec.from_file`` and attached names its files relative to
its own folder, and ``spec(path)`` is what reads it with absolute ones. A spec a scene has attached is refused by name
(``_parts.attached``): it is the scene's now, and MuJoCo 4.0.0 crashes compiling it.

**What it removes.** As an export does (``mjcf``'s ``place``): the files are staged beside ``path`` and moved
in only where their bytes changed, and the files the last ``save`` (or export) of ``path`` wrote into
``assets/`` and this one no longer names are removed -- only those its own list names (``.<name>.meshes`` in
``assets/``), never a file another list still names, nor any other file.

Then the file written is checked as ``cad mujoco check`` checks one (``_check.check``): each warning is
printed, then what the model collides as and its contact excludes, one line each, then ``wrote <path>``. A relative ``path`` is taken against the working directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

__all__ = ["save"]

SUFFIXES = (".xml", ".mjcf")


def save(spec: Any, path: str | Path) -> Path:
    """Write ``spec`` (a ``mujoco.MjSpec``) to ``path`` with its files in ``assets/`` beside it and a ``scene.xml``
    where there is none (the module docstring); the path written."""
    try:
        import mujoco
    except ModuleNotFoundError as error:
        from cad.mujoco._spec import EXTRA

        raise ModuleNotFoundError(f"mujoco comes with cad's mujoco integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name=error.name) from None
    if not isinstance(spec, mujoco.MjSpec):
        raise TypeError(f"save writes a mujoco.MjSpec (what spec() and a MuJoCo function return), not "
                        f"{type(spec).__name__}")
    if not isinstance(path, (str, Path)) or not str(path):
        raise TypeError(f"save writes to a file path, not {path!r}")
    target = Path(path).absolute()
    if target.suffix.lower() not in SUFFIXES:
        raise ValueError(f"save writes an MJCF: name the file {target.stem}.xml, not {target.name}")
    from cad.engine.atomic_replace import replace_atomic, same_bytes, staging
    from cad.engine.export.mjcf import SCENE, _stale
    from cad.mujoco._parts import attached

    attached(spec, "save")
    try:
        made = _flat(mujoco, spec)
    except ValueError as error:
        if "opening file" not in str(error):
            raise
        # An attached child read with MjSpec.from_file names its files relative to its own folder, which only
        # the child knew: MuJoCo looks for them beside the working directory and says the file is not there.
        raise ValueError(f"{error}\nsave: MuJoCo did not find a file this spec names. A robot read with "
                         "mujoco.MjSpec.from_file and attached to a scene names its files relative to its own "
                         "folder, which the scene does not hold: read it with cad.mujoco.spec(path), which names "
                         "each file by its absolute path, and attach that") from None
    files = _files(made)
    target.parent.mkdir(parents=True, exist_ok=True)
    folder = target.parent / "assets"
    with staging(target) as staged:
        held = staged.parent / "assets"
        held.mkdir()
        for name, (source, elements) in files.items():
            if not Path(source).is_file():
                raise FileNotFoundError(f"save: the spec names {source}, which is not there")
            shutil.copyfile(source, held / name)
            for element in elements:
                element.file = name
        made.meshdir = "assets"
        if any(texture.file for texture in made.textures):
            made.texturedir = "assets"
        made.modelfiledir = str(staged.parent)
        made.compile()
        staged.write_text(made.to_xml(), encoding="utf-8")
        if files and not folder.exists():
            replace_atomic(held, folder)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            for name in files:
                if not same_bytes(folder / name, held / name):
                    replace_atomic(held / name, folder / name)
        if not same_bytes(target, staged):
            replace_atomic(staged, target)
    said = _said(lambda: _stale(target, folder, dict.fromkeys(files, b""), writer="save"))
    if target.name.lower() != SCENE and not (target.parent / SCENE).exists() and not _floored(mujoco, spec):
        said.append(_scene(mujoco, target, spec.modelname or target.stem))
    for line in said:
        print(line)
    for line in _findings(target):
        print(line)
    print(f"wrote {target}")
    return target


def _flat(mujoco: Any, spec: Any) -> Any:
    """``spec`` as one spec of its own, every file named by its absolute path: a copy with its own files rooted
    (``_rooted``), compiled to MuJoCo's text and read back. An attached child's meshes and textures are resolved
    against the child's own folders when the spec compiles, never the parent's, so a copy whose ``meshdir`` is set
    would not find them; read back from text, they are the spec's own, and ``meshdir`` reaches every one. The
    compile is the spec's check too: MuJoCo's ``ValueError`` for a spec it refuses, before anything is written."""
    from cad.mujoco._spec import _rooted

    return _rooted(mujoco.MjSpec.from_string(_rooted(spec.copy()).to_xml()))


def _files(made: Any) -> dict[str, tuple[str, list[Any]]]:
    """Each file the spec names (``_rooted``: by its absolute path), by the bare name it is saved under, with the
    elements naming it: a second file of one bare name is ``<stem>_2<suffix>``."""
    found: dict[str, tuple[str, list[Any]]] = {}
    by_source: dict[str, str] = {}
    for element in [*made.meshes, *made.textures, *made.hfields]:
        source = element.file
        if not source:
            continue
        name = by_source.get(source)
        if name is None:
            given = Path(source)
            name, at = given.name, 1
            while name in found or name.startswith("."):
                at += 1
                name = f"{given.stem.lstrip('.')}_{at}{given.suffix}"
            by_source[source] = name
            found[name] = (source, [])
        found[name][1].append(element)
    return found


def _floored(mujoco: Any, spec: Any) -> bool:
    """Whether ``spec`` has a floor of its own, a plane geom on its world body: a scene, which no scene includes."""
    return any(geom.type == mujoco.mjtGeom.mjGEOM_PLANE for geom in spec.worldbody.geoms)


def _said(call: Any) -> list[str]:
    """What ``call`` says through the export's ``note``, as lines."""
    from cad.engine.export import _NOTES

    heard: list[str] = []
    token = _NOTES.set(heard)
    try:
        call()
    finally:
        _NOTES.reset(token)
    return heard


def _scene(mujoco: Any, target: Path, name: str) -> str:
    """``scene.xml`` written beside ``target``, around the model's geometry at zero; what to say of it."""
    import numpy as np

    from cad.engine.atomic_replace import put
    from cad.engine.export.mjcf import SCENE, scene_around

    model = mujoco.MjModel.from_xml_path(str(target))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    signs = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float)
    corners = []
    for geom in range(model.ngeom):
        if int(model.geom_type[geom]) == mujoco.mjtGeom.mjGEOM_PLANE:
            continue
        centre, half = model.geom_aabb[geom][:3], model.geom_aabb[geom][3:]
        turn = data.geom_xmat[geom].reshape(3, 3)
        corners.append((centre + signs * half) @ turn.T + data.geom_xpos[geom])
    if corners:
        every = np.concatenate(corners)
        low, high = every.min(axis=0), every.max(axis=0)
    else:
        low, high = np.full(3, -0.05), np.full(3, 0.05)
    text = scene_around(name, low, high, target.name)
    put(target.parent / SCENE, lambda staged: Path(staged).write_text(text, encoding="utf-8"))
    return f"wrote {SCENE} beside it: a floor and a light around the robot, yours to edit (save never writes over it)"


def _findings(target: Path) -> list[str]:
    """What ``cad mujoco check`` says of the file written (``_check.check``), each a line: the health checks' errors
    and warnings, then what the model collides as and its contact excludes, the two facts a MuJoCo function's
    choices change."""
    from cad.mujoco._check import check

    found = check(target)
    lines = [f"{finding.severity}: {finding.message}" + (f" ({finding.hint})" if finding.hint else "")
             for finding in found.findings if finding.severity in ("error", "warning")]
    return lines + [f"{finding.code}: {finding.message}" for finding in found.findings
                    if finding.code in ("collisions", "excludes")]
