"""``cad.blender``: the blender integration -- a GLB loaded into Blender's scene for a render, taking and
answering Blender's own objects (its extra, ``cad[blender]``: bpy, Blender as a Python module, which has
builds for Python 3.13 alone).

    from cad.blender import load

    model = load("scene.glb", clip="explode", fps=24)
    model.root, model.box, model.clips      # the root's object, the world box in metres, each clip
    model.objects["arm/head/pin_1"]         # a node's object, by the node's name
    model.play("cycle")                     # another clip; model.play(None) stands still

``load`` imports the file with Blender's own glTF importer and answers a ``Model``: each node's object, the
clips, and the box of the pose the file was written in. It sets the scene's frame rate first (``fps``, with
``render.fps_base`` 1), which keys the clips' seconds. It undoes what that importer gets wrong with a file
that has clips: it leaves a node a clip moves at its first clip's start, so a still shows a pose the file
never held, with no error; only that first clip plays, and clearing it leaves its last pose; and it keys
every clip from frame 0, wherever the scene's range starts. Here every node a clip moves stands where the
file places it, and a clip plays alone (``Model.play``), the scene's range set to its frames, 0 to its
duration.

It opens any GLB, cad's or another tool's (build123d's ``export_gltf``, KiCad's board): a node is known by
its place in the file, never by the name Blender gives its object, so a node with no name, two of one name
and a name Blender cuts short are each found. A skin's joints are no objects but bones, of the armature Blender
makes for the skin (the skinned mesh's parent), found there by name; ``load`` places objects, never a bone.

Everything loads on first use: ``import cad.blender`` imports no bpy, and a script whose environment lacks it
is told which extra brings it. Nothing of Blender's is re-exported: ``import bpy`` stays Blender's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["Clip", "Model", "load"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        from cad.blender import _scene
    except ModuleNotFoundError as error:
        from cad._internal.integrations import missing

        said = missing(error)
        if said is None:
            raise
        raise ModuleNotFoundError(said, name=error.name) from None
    return getattr(_scene, name)


def __dir__() -> list[str]:
    """Its public names (``__all__``), without loading any of them."""
    return sorted({*__all__, *(name for name in globals() if name.startswith("__"))})


if TYPE_CHECKING:
    from cad.blender._scene import Clip, Model, load
