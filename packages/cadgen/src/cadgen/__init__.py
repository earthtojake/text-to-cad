"""Shared CAD artifact generation runtime."""

from typing import TYPE_CHECKING

__all__ = [
    "AssemblyHelper",
    "srgb",
    "MateRelation",
    "MateTarget",
    "compound_from_instances",
    "ensure_step_glb_artifact",
    "label_text",
    "label_shape",
    "report",
    "target",
    "track",
    "validate_step_glb_artifact",
]


def __getattr__(name: str):
    if name in {"ensure_step_glb_artifact", "validate_step_glb_artifact"}:
        from cadgen.api import ensure_step_glb_artifact, validate_step_glb_artifact

        return {
            "ensure_step_glb_artifact": ensure_step_glb_artifact,
            "validate_step_glb_artifact": validate_step_glb_artifact,
        }[name]
    if name in {"AssemblyHelper", "MateRelation", "MateTarget", "label_shape", "label_text", "target"}:
        from cadgen.assembly import AssemblyHelper, MateRelation, MateTarget, label_shape, label_text, target

        return {
            "AssemblyHelper": AssemblyHelper,
            "MateRelation": MateRelation,
            "MateTarget": MateTarget,
            "label_text": label_text,
            "label_shape": label_shape,
            "target": target,
        }[name]
    if name in {"srgb", "srgb_to_linear", "linear_to_srgb"}:
        from cadgen import color

        return getattr(color, name)
    if name == "compound_from_instances":
        from cadgen.instances import compound_from_instances

        return compound_from_instances
    if name in {"report", "track"}:
        from cadgen.progress import report, track

        return {"report": report, "track": track}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from cadgen.api import ensure_step_glb_artifact, validate_step_glb_artifact
    from cadgen.assembly import AssemblyHelper, MateRelation, MateTarget, label_shape, label_text, target
    from cadgen.color import srgb, srgb_to_linear, linear_to_srgb
    from cadgen.instances import compound_from_instances
    from cadgen.progress import report, track
