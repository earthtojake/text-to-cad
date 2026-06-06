"""Shared CAD artifact generation runtime."""

__all__ = [
    "AssemblyHelper",
    "MateRelation",
    "MateTarget",
    "ensure_step_glb_artifact",
    "label_text",
    "label_shape",
    "target",
    "validate_step_glb_artifact",
]


def __getattr__(name: str):
    if name in {"ensure_step_glb_artifact", "validate_step_glb_artifact"}:
        from cadpy.api import ensure_step_glb_artifact, validate_step_glb_artifact

        return {
            "ensure_step_glb_artifact": ensure_step_glb_artifact,
            "validate_step_glb_artifact": validate_step_glb_artifact,
        }[name]
    if name in {"AssemblyHelper", "MateRelation", "MateTarget", "label_shape", "label_text", "target"}:
        from cadpy.assembly import AssemblyHelper, MateRelation, MateTarget, label_shape, label_text, target

        return {
            "AssemblyHelper": AssemblyHelper,
            "MateRelation": MateRelation,
            "MateTarget": MateTarget,
            "label_text": label_text,
            "label_shape": label_shape,
            "target": target,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
