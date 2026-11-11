"""``cad.mujoco``: the mujoco integration -- our code that calls MuJoCo, taking its objects (its extra,
``cad[mujoco]``: ``mujoco-core``, the compiler and the Python bindings, numpy their one dependency, and
``mujoco-studio``, MuJoCo Studio's web viewer; no window system).

An MJCF is MuJoCo's own file and no document type: cad writes one and asks MuJoCo about one, and never
reads or shows one itself. ``check`` compiles a model with MuJoCo's own compiler and answers a check's result
-- what MuJoCo refused or warned of, in its words, the model-health checks, what the model collides as and
its contact excludes (``_check``; ``cad mujoco check FILE`` is its command, the integration's one operation
in ``cad.registry``). ``compile_model`` and ``compile_findings`` are the compile alone. ``cad run
mujoco-studio --model FILE`` shows the person a model in Studio's web viewer (``_command``: the environment's
own ``mujoco-studio``).

What it does for every document: ``spec`` makes one a ``mujoco.MjSpec`` (``_spec``): a model call's
handle, a build123d shape, a STEP or an xbf described as a robot and written as the engine's MJCF
export writes it (``cad.engine.export.mjcf``), for a scene to attach; an MJCF path read as it is.

What it does for a MuJoCo function -- a plain function that makes a robot's spec with ``spec``, makes the
simulator's choices on it in MuJoCo's own API and returns it: ``parts`` lists the spec's parts by label path,
and ``collisions``, ``fit`` and ``decompose`` find and replace one part's collision geoms by it (``_parts``: ``fit`` the kernel's primitive
of the part's exact solid, ``decompose`` CoACD's convex hulls of its mesh), and ``save`` writes the spec as a
folder that travels, by MuJoCo's own writer (``_save``).

Everything loads on first use: ``import cad.mujoco`` imports no mujoco. A helper called where the
extra is missing says so by name (``cad[mujoco]``), as every integration's does.
"""

from __future__ import annotations

from pathlib import Path

from cad.results import CheckResult

__all__ = ["check", "collisions", "compile_findings", "compile_model", "decompose", "fit", "parts", "save", "spec"]


def check(path: Path, *, strict: bool = False, verbose: bool = False) -> CheckResult:
    """Compile one MuJoCo model with MuJoCo and check it.

    MuJoCo's own compiler reads the model, so what it refuses or warns of is said in its words. Then
    the model-health checks of MuJoCo's modelling guide run on the compiled model, and two facts are
    said of it: what collides as what, body by body, and each contact exclude with how its two bodies
    stand at rest (every geom and exclude a row of the result's measurements). Errors always block;
    under ``strict`` warnings do too.

    path: the .xml or .mjcf file to check.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    from cad.mujoco._check import check as _check

    return _check(path, strict=strict, verbose=verbose)


def compile_model(path):
    """The model at ``path`` compiled by MuJoCo (``mujoco.MjModel``), its compile warnings beside it, as
    ``(model, warnings)``; MuJoCo's ``ValueError`` for a model it refuses."""
    from cad.mujoco._compile import compile_model as _compile

    return _compile(path)


def compile_findings(path, *, mode="auto"):
    """Compile the MJCF at ``path`` with MuJoCo and answer findings (``cad._internal.findings.FindingsReport``):
    an error with MuJoCo's words for a model it refuses, a warning for each compile warning, an info saying the
    compile passed or was skipped (``mode`` ``auto``, mujoco not installed here); ``required`` without mujoco
    is an error naming the extra."""
    from cad.mujoco._compile import compile_findings as _findings

    return _findings(path, mode=mode)


def spec(thing, *, assets=None, tolerance=None, zero=None):
    """``thing`` -- a model call's handle, a build123d shape, a ``.step``/``.xbf`` path, or an MJCF path read as
    it is -- as a ``mujoco.MjSpec`` for a scene to attach (``scene.attach(spec(arm()), prefix="arm/",
    frame=...)``). Its meshes are written where MuJoCo will read them when the scene compiles: ``assets``, a
    folder relative to the working directory where the scene is saved, else a folder of the engine's cache named
    by what it holds (``cad.mujoco._spec``). ``tolerance`` meshes them to within it, in mm. ``zero``, a mechanism
    state's name, takes a document's robot there, every joint's zero at that state, as an export's ``--zero`` does
    (an MJCF's zero is its own, and a zero is refused)."""
    from cad.mujoco._spec import spec as _spec

    return _spec(thing, assets=assets, tolerance=tolerance, zero=zero)


def parts(spec):
    """The label paths of every part of ``spec`` (a spec ``spec`` made), sorted: the names ``collisions``, ``fit``
    and ``decompose`` take. A spec read from an MJCF answers its colliding meshes' names (``cad.mujoco._parts``)."""
    from cad.mujoco._parts import parts as _listed

    return _listed(spec)


def collisions(spec, part):
    """The collision geoms (``mujoco.MjsGeom``) of the part ``part`` names in ``spec`` (a spec ``spec`` made): its
    label path, as ``cad model inspect`` prints it, a last segment enough where only one part ends in it; a list,
    empty for a part that collides as nothing. A label that names no part, or two, is refused by name
    (``cad.mujoco._parts``)."""
    from cad.mujoco._parts import collisions as _collisions

    return _collisions(spec, part)


def fit(spec, part, kind):
    """Replace the collision of the part ``part`` names in ``spec`` with the primitive ``kind`` (``box``, ``sphere``,
    ``cylinder``, ``capsule``) the kernel fits to its exact solid (``cad.engine.describe.fit``); refused on a spec
    read from an MJCF (no solids) and for a part read from a mesh. Its collision geoms."""
    from cad.mujoco._parts import fit as _fit

    return _fit(spec, part, kind)


def decompose(spec, part, *, max_hulls=16, threshold=None):
    """Replace the collision of the part ``part`` names in ``spec`` with the convex hulls CoACD cuts its mesh into
    (``cad[coacd]``): ``max_hulls`` at most that many (None for no limit), ``threshold`` CoACD's concavity
    threshold, 0.01 to 1 (its 0.05 where None). Works on a spec read from an MJCF too. Its collision geoms."""
    from cad.mujoco._parts import decompose as _decompose

    return _decompose(spec, part, max_hulls=max_hulls, threshold=threshold)


def save(spec, path):
    """Write ``spec`` (a ``mujoco.MjSpec``) to ``path`` by MuJoCo's own writer, every file it names copied into
    ``assets/`` beside it, a ``scene.xml`` beside it where there is none and the spec has no floor of its own (no
    plane geom on its world body: a scene gets none); the spec handed in is left as it was.
    Prints the check's warnings, what the model collides as, its contact excludes and ``wrote <path>``; the
    path written (``cad.mujoco._save``)."""
    from cad.mujoco._save import save as _save

    return _save(spec, path)
