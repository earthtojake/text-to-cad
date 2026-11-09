"""Open in's Blender: the script a person's own Blender runs (``--python``) when they open a GLB or an STL in it.

Blender opens only its own ``.blend`` files from its command line: handed a GLB or an STL it says the file format is
not supported. So ``apps.open_file`` starts it as ``blender --python <this file> -- <file>``, and this imports the
file into the startup scene, emptied of its objects (the default cube, light and camera), with the person's own
preferences and layout as they are, selects what it imported and frames it in every 3D viewport once the window is up.

The file is the one argument after ``--``, read from ``sys.argv``: the path is data, never code. A file of a kind this
does not import, or none, leaves Blender open as it started, saying why on its console.

The glTF importer poses a part that a clip moves at that clip's first frame, the first clip's where several move it:
for opening a file that is the model, at the start of its first clip. Nothing here plays or changes a clip.

MIT, as the rest of the package. It runs only inside Blender (Blender's Python API, ``bpy``); nothing of the package
imports it.
"""

import importlib
import os
import sys
from typing import Any

# Blender's own module, imported only where Blender runs this file (as ``__main__``, below): importing the module
# elsewhere, as anything that walks the package does, loads nothing of Blender's.
bpy: Any = None

# What each extension is imported by: Blender's own importers (glTF's since 2.80, STL's built in since 4.1, an
# add-on's before).
IMPORTERS = {".glb": "gltf", ".gltf": "gltf", ".stl": "stl"}


def requested(argv: list[str]) -> str | None:
    """The file named after ``--``: the one argument there, else None."""
    if "--" not in argv:
        return None
    rest = argv[argv.index("--") + 1:]
    return rest[0] if len(rest) == 1 and rest[0] else None


def empty(scene) -> None:
    """Remove the scene's objects, and the data only they used: the startup file's cube, light and camera."""
    doomed = list(scene.objects)
    used = {obj.data for obj in doomed if obj.data is not None}
    bpy.data.batch_remove(doomed)
    bpy.data.batch_remove([data for data in used if data.users == 0])


def bring_in(path: str) -> list:
    """Import the file at ``path`` into the current scene: the objects it made."""
    before = set(bpy.data.objects.keys())
    if IMPORTERS[os.path.splitext(path)[1].lower()] == "gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=path)
    else:
        bpy.ops.import_mesh.stl(filepath=path)
    return [obj for obj in bpy.data.objects if obj.name not in before]


def select(view_layer, objects: list) -> None:
    """Select ``objects``' roots alone, the first of them active."""
    made = {obj.name for obj in objects}
    roots = [obj for obj in objects if obj.parent is None or obj.parent.name not in made]
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in roots:
        obj.select_set(True)
    if roots:
        view_layer.objects.active = roots[0]


def frame() -> None:
    """Frame the selection in every 3D viewport of every window: once, from a timer, the window being up by then.
    A viewport that cannot is left as it was."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            region = next((region for region in area.regions if region.type == "WINDOW"), None)
            if area.type != "VIEW_3D" or region is None:
                continue
            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_selected()
            except Exception as error:  # noqa: BLE001 - framing is a nicety; the model is open either way
                print(f"open_in_blender: could not frame the model: {error}", file=sys.stderr)
    return None  # a timer that returns None runs once


def main(argv: list[str]) -> None:
    path = requested(argv)
    if path is None:
        print("open_in_blender: no file named after --", file=sys.stderr)
        return
    if os.path.splitext(path)[1].lower() not in IMPORTERS or not os.path.isfile(path):
        print(f"open_in_blender: {path} is not a GLB, glTF or STL file here", file=sys.stderr)
        return
    context = bpy.context
    empty(context.scene)
    select(context.view_layer, bring_in(path))
    if not bpy.app.background:
        bpy.app.timers.register(frame, first_interval=0.2)


if __name__ == "__main__":  # Blender's --python runs a file as __main__
    bpy = importlib.import_module("bpy")
    main(sys.argv)
