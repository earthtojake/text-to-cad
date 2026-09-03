"""Shared CAD artifact generation runtime."""

from typing import TYPE_CHECKING

# Before anything imports build123d, which every cadgen entry point eventually does:
# build123d parses EVERY font in the system font folders at import time, with no
# per-file guard, so one malformed file aborts the import and every cadgen command
# with it (issue #322, upstream in build123d's register_folder). This hides
# unparseable fonts from that one listing.
#
# It belongs here rather than in a launcher because the skill shims, the daemon's warm
# workers and `python -m cadgen.X` children all reach cadgen by different routes, and a
# fix that covered only one of them would leave the builds it spawns still broken.
#
# Cost where nothing is wrong: one str.endswith per glob call. CADGEN_FONT_GUARD=0
# opts out.
from cadgen._internal.font_scan import install_font_guard as _install_font_guard
from cadgen._internal.kernel_import_site import install as _install_kernel_import_site

_install_kernel_import_site()
del _install_kernel_import_site

_install_font_guard()
del _install_font_guard

__all__ = [
    "__version__",
    "AssemblyHelper",
    "step",
    "dxf",
    "stl",
    "glb",
    "threemf",
    "revolute",
    "slider",
    "cylindrical",
    "fastened",
    "couple",
    "build123d",
    "srgb",
    "MateTarget",
    "compound_from_instances",
    "read_step",
    "load_step_scene",
    "located_shape",
    "occurrence_selector_id",
    "scene_occurrence_shape",
    "ensure_step_topology_artifact",
    "label_text",
    "label_shape",
    "report",
    "target",
    "track",
]


def __getattr__(name: str):
    if name in {"step", "dxf", "stl", "glb", "threemf"}:
        # A FORMAT NAMESPACE: the declaration decorator and the format's verbs in
        # one callable module (design/format-doors.md). Returning the module
        # rather than cadgen.authoring.<name> keeps a single identity —
        # `import cadgen.stl` would otherwise shadow the decorator.
        import importlib

        return importlib.import_module(f"cadgen.{name}")
    if name in {"revolute", "slider", "cylindrical", "fastened", "couple"}:
        # Typed-mates kinematics vocabulary for the kinematics= dict on
        # @step/@stl/@glb/@threemf (design/pose-animation-split.md).
        from cadgen import kinematics

        return getattr(kinematics, name)
    if name == "build123d":
        # `from cadgen import build123d as bd` — the lazy transparent re-export.
        # Importing the submodule is cheap; the real build123d import happens on
        # first attribute touch inside cadgen.build123d.
        import cadgen.build123d as _bd

        return _bd
    if name == "ensure_step_topology_artifact":
        from cadgen.step_topology_artifact import ensure_step_topology_artifact

        return ensure_step_topology_artifact
    if name in {"AssemblyHelper", "MateTarget", "label_shape", "label_text", "target"}:
        from cadgen.assembly import AssemblyHelper, MateTarget, label_shape, label_text, target

        return {
            "AssemblyHelper": AssemblyHelper,
            "MateTarget": MateTarget,
            "label_text": label_text,
            "label_shape": label_shape,
            "target": target,
        }[name]
    if name in {"read_step", "load_step_scene", "located_shape", "occurrence_selector_id", "scene_occurrence_shape"}:
        from cadgen import step_scene

        return getattr(step_scene, name)
    if name in {"srgb", "srgb_to_linear", "linear_to_srgb"}:
        from cadgen import color

        return getattr(color, name)
    if name == "compound_from_instances":
        from cadgen.instances import compound_from_instances

        return compound_from_instances
    if name in {"report", "track"}:
        from cadgen.progress import report, track

        return {"report": report, "track": track}[name]
    if name == "__version__":
        return _resolve_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    # Mirrors the lazy __getattr__ above so type checkers and editors see the root exports
    # without importing OCP. Every name here must have a branch there. An earlier version
    # of this block pulled two names from the api alias module, since deleted -- they come
    # from their real modules now.
    from cadgen import build123d, dxf, glb, step, stl, threemf
    from cadgen.assembly import AssemblyHelper, MateTarget, label_shape, label_text, target
    from cadgen.color import linear_to_srgb, srgb, srgb_to_linear
    from cadgen.kinematics import couple, cylindrical, fastened, revolute, slider
    from cadgen.instances import compound_from_instances
    from cadgen.progress import report, track
    from cadgen.step_scene import (
        read_step,
        load_step_scene,
        located_shape,
        occurrence_selector_id,
        scene_occurrence_shape,
    )
    from cadgen.step_topology_artifact import ensure_step_topology_artifact


def _resolve_version() -> str:
    """The installed distribution version, falling back to pyproject in a source tree.

    Installed metadata is the authority: it is what a consumer actually has, and it is
    what the skill shims compare their pinned requirement against. A bare source checkout
    has no metadata, so fall back to the pyproject this file ships beside — release
    tooling stamps it from the canonical VERSION, so the two never disagree.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("cadgen")
    except PackageNotFoundError:
        pass

    import pathlib
    import tomllib

    pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject.open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0+unknown"
