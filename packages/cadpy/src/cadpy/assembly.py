from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


SEMANTIC_LABEL_KINDS = {
    "assembly",
    "component",
    "module",
    "feature",
    "datum",
    "mate",
    "mate_target",
    "hardware",
    "tool",
}


@dataclass(frozen=True)
class MateTarget:
    """A named native build123d joint on a part-like shape."""

    part: Any
    frame: str


@dataclass(frozen=True)
class MateRelation:
    """A source-level placement relationship recorded by AssemblyHelper."""

    label: str
    relation: str
    fixed: str
    moving: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


def semantic_label(kind: str, name: str, *details: object) -> str:
    """Build a compact STEP-friendly semantic label such as component:base."""

    label_kind = _normalize_label_token(kind, field_name="kind")
    if label_kind not in SEMANTIC_LABEL_KINDS:
        allowed = ", ".join(sorted(SEMANTIC_LABEL_KINDS))
        raise ValueError(f"Unsupported semantic label kind {kind!r}; expected one of {allowed}")
    tokens = [_normalize_label_token(name, field_name="name")]
    tokens.extend(_normalize_label_token(detail, field_name="detail") for detail in details)
    return ":".join((label_kind, *tokens))


def label_shape(
    shape: Any,
    kind: str,
    name: str,
    *details: object,
    color: Any | None = None,
) -> Any:
    """Assign native build123d label/color metadata and return the shape."""

    shape.label = semantic_label(kind, name, *details)
    if color is not None:
        shape.color = color
    return shape


def mate_label(name: str) -> str:
    """Return the native joint label used for semantic mate frames."""

    raw = str(name).strip()
    if raw.startswith("mate:"):
        return raw
    return semantic_label("mate", raw)


def target(part: Any, frame: str) -> MateTarget:
    return MateTarget(part=part, frame=str(frame).strip())


class AssemblyHelper:
    """Small semantic wrapper around native build123d joints and compounds.

    Generated CAD scripts should express named part-local frames and semantic
    relationships here; this helper realizes those relationships with native
    build123d Joint objects and returns a labeled Compound assembly.
    """

    def __init__(self, name: str, *, kind: str = "assembly") -> None:
        self.label = semantic_label(kind, name)
        self.children: list[Any] = []
        self.relations: list[MateRelation] = []

    def add(
        self,
        shape: Any,
        name: str,
        *,
        kind: str = "component",
        color: Any | None = None,
    ) -> Any:
        label_shape(shape, kind, name, color=color)
        self.children.append(shape)
        return shape

    def add_module(self, name: str, children: Sequence[Any], *, color: Any | None = None) -> Any:
        module = self.compound(children, label=semantic_label("module", name))
        if color is not None:
            module.color = color
        self.children.append(module)
        return module

    def feature(
        self,
        shape: Any,
        name: str,
        *details: object,
        color: Any | None = None,
    ) -> Any:
        return label_shape(shape, "feature", name, *details, color=color)

    def datum(
        self,
        shape: Any,
        name: str,
        *details: object,
        color: Any | None = None,
    ) -> Any:
        return label_shape(shape, "datum", name, *details, color=color)

    def rigid_frame(self, part: Any, name: str, location: Any) -> MateTarget:
        return add_rigid_frame(part, name, location)

    def revolute_frame(self, part: Any, name: str, axis: Any, **joint_options: Any) -> MateTarget:
        return add_axis_frame(part, name, axis, joint_type="RevoluteJoint", **joint_options)

    def linear_frame(self, part: Any, name: str, axis: Any, **joint_options: Any) -> MateTarget:
        return add_axis_frame(part, name, axis, joint_type="LinearJoint", **joint_options)

    def cylindrical_frame(self, part: Any, name: str, axis: Any, **joint_options: Any) -> MateTarget:
        return add_axis_frame(part, name, axis, joint_type="CylindricalJoint", **joint_options)

    def ball_frame(self, part: Any, name: str, location: Any, **joint_options: Any) -> MateTarget:
        return add_joint_frame(
            part,
            name,
            joint_type="BallJoint",
            joint_location=location,
            **joint_options,
        )

    def connect(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        relation: str = "rigid",
        label: str | None = None,
        **connect_options: Any,
    ) -> MateRelation:
        fixed_target = _normalize_target(fixed)
        moving_target = _normalize_target(moving)
        fixed_joint_label, fixed_joint = _joint_for_target(fixed_target)
        moving_joint_label, moving_joint = _joint_for_target(moving_target)
        options = {key: value for key, value in connect_options.items() if value is not None}
        fixed_joint.connect_to(moving_joint, **options)
        relation_record = MateRelation(
            label=label or semantic_label("mate", relation, fixed_joint_label, moving_joint_label),
            relation=relation,
            fixed=fixed_joint_label,
            moving=moving_joint_label,
            parameters=options,
        )
        self.relations.append(relation_record)
        return relation_record

    def face_to_face(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        offset: float | Sequence[float] | Any | None = None,
        label: str | None = None,
    ) -> MateRelation:
        fixed_target = _normalize_target(fixed)
        if offset is not None:
            fixed_target = offset_target(fixed_target, offset, label=label)
        return self.connect(
            fixed_target,
            moving,
            relation="face_to_face",
            label=label,
        )

    def coaxial(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        offset: float | Sequence[float] | Any | None = None,
        label: str | None = None,
    ) -> MateRelation:
        fixed_target = _normalize_target(fixed)
        if offset is not None:
            fixed_target = offset_target(fixed_target, offset, label=label)
        return self.connect(
            fixed_target,
            moving,
            relation="coaxial",
            label=label,
        )

    def revolute(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        angle: float | None = None,
        label: str | None = None,
    ) -> MateRelation:
        return self.connect(fixed, moving, relation="revolute", label=label, angle=angle)

    def linear(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        position: float | None = None,
        label: str | None = None,
    ) -> MateRelation:
        return self.connect(fixed, moving, relation="linear", label=label, position=position)

    def compound(self, children: Sequence[Any] | None = None, *, label: str | None = None) -> Any:
        build123d = _import_build123d()
        return build123d.Compound(
            label=label or self.label,
            children=list(children if children is not None else self.children),
        )

    def build(self) -> Any:
        return self.compound()


def add_rigid_frame(part: Any, name: str, location: Any) -> MateTarget:
    return add_joint_frame(
        part,
        name,
        joint_type="RigidJoint",
        joint_location=location,
    )


def add_axis_frame(part: Any, name: str, axis: Any, *, joint_type: str, **joint_options: Any) -> MateTarget:
    return add_joint_frame(
        part,
        name,
        joint_type=joint_type,
        axis=axis,
        **joint_options,
    )


def add_joint_frame(part: Any, name: str, *, joint_type: str, **joint_options: Any) -> MateTarget:
    build123d = _import_build123d()
    joint_cls = getattr(build123d, joint_type)
    label = mate_label(name)
    joint_cls(
        label=label,
        to_part=part,
        **{key: value for key, value in joint_options.items() if value is not None},
    )
    return MateTarget(part=part, frame=label)


def offset_target(
    fixed: MateTarget | tuple[Any, str],
    offset: float | Sequence[float] | Any,
    *,
    label: str | None = None,
) -> MateTarget:
    fixed_target = _normalize_target(fixed)
    fixed_joint_label, fixed_joint = _joint_for_target(fixed_target)
    build123d = _import_build123d()
    location = getattr(fixed_joint, "location", None)
    if location is None:
        location = getattr(fixed_joint, "joint_location", None)
    if location is None:
        raise ValueError(f"Joint {fixed_joint_label!r} does not expose a location")
    offset_location = _offset_location(offset)
    target_location = location * offset_location
    target_label = semantic_label("mate_target", label or fixed_joint_label, "offset")
    build123d.RigidJoint(
        label=target_label,
        to_part=fixed_target.part,
        joint_location=target_location,
    )
    return MateTarget(part=fixed_target.part, frame=target_label)


def _normalize_target(value: MateTarget | tuple[Any, str]) -> MateTarget:
    if isinstance(value, MateTarget):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return MateTarget(part=value[0], frame=str(value[1]).strip())
    raise TypeError("Mate target must be MateTarget or (part, frame_name)")


def _joint_for_target(target_value: MateTarget) -> tuple[str, Any]:
    joints = getattr(target_value.part, "joints", None)
    if not isinstance(joints, Mapping):
        raise ValueError("Mate target part does not expose a build123d joints mapping")
    candidates = [target_value.frame]
    semantic = mate_label(target_value.frame)
    if semantic not in candidates:
        candidates.append(semantic)
    for candidate in candidates:
        joint = joints.get(candidate)
        if joint is not None:
            return candidate, joint
    raise KeyError(f"Part does not define mate frame {target_value.frame!r}")


def _offset_location(offset: float | Sequence[float] | Any) -> Any:
    build123d = _import_build123d()
    if hasattr(offset, "wrapped"):
        return offset
    if isinstance(offset, (int, float)):
        return build123d.Location((0.0, 0.0, float(offset)))
    if isinstance(offset, Sequence) and not isinstance(offset, (str, bytes)):
        return build123d.Location(tuple(float(value) for value in offset))
    return offset


def _normalize_label_token(value: object, *, field_name: str) -> str:
    token = str(value).strip()
    if not token:
        raise ValueError(f"Semantic label {field_name} must be non-empty")
    return "_".join(token.replace(":", "_").split())


def _import_build123d() -> Any:
    try:
        import build123d
    except ModuleNotFoundError as exc:
        raise RuntimeError("cadpy.assembly requires build123d at runtime") from exc
    return build123d
