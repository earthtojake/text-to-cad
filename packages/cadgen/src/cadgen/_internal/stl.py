from __future__ import annotations

from pathlib import Path

from OCP.StlAPI import StlAPI_Writer

from cadgen._internal.step_scene import (
    LoadedStepScene,
    scene_export_shape,
)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def export_part_stl_from_scene(step_path: Path, scene: LoadedStepScene, *, target_path: Path) -> Path:
    export_shape_stl(scene_export_shape(scene), target_path)
    return target_path

def export_shape_stl(shape: object, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(shape, str(target_path)):
        raise RuntimeError(f"Failed to write STL output: {_display_path(target_path)}")
    return target_path
