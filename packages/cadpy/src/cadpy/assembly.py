from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


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
    fixed_endpoint: Mapping[str, Any] = field(default_factory=dict)
    moving_endpoint: Mapping[str, Any] = field(default_factory=dict)


def label_text(name: str, *details: object) -> str:
    """Build a compact STEP-friendly label such as m3_standoff:front_left."""

    tokens = [_normalize_label_token(name, field_name="name")]
    tokens.extend(_normalize_label_token(detail, field_name="detail") for detail in details)
    return ":".join(tokens)


def label_shape(
    shape: Any,
    name: str,
    *details: object,
    color: Any | None = None,
) -> Any:
    """Assign native build123d label/color metadata and return the shape."""

    shape.label = label_text(name, *details)
    if color is not None:
        shape.color = color
    return shape


def mate_label(name: str) -> str:
    """Return the native joint label used for named mate frames."""

    return label_text(name)


def target(part: Any, frame: str) -> MateTarget:
    return MateTarget(part=part, frame=label_text(frame))


def assembly_mate_payload(relations: Sequence[MateRelation]) -> list[dict[str, Any]]:
    """Return JSON-safe source mate metadata for STEP topology artifacts."""

    payload: list[dict[str, Any]] = []
    for index, relation in enumerate(relations, start=1):
        fallback_label = f"mate_{index}"
        label = str(relation.label or fallback_label).strip() or fallback_label
        mate_id = f"m{index}"
        relation_type = str(relation.relation or "mate").strip() or "mate"
        fixed = str(relation.fixed or "fixed").strip() or "fixed"
        moving = str(relation.moving or "moving").strip() or "moving"
        payload.append(
            {
                "id": mate_id,
                "label": mate_id,
                "sourceLabel": label,
                "type": relation_type,
                "relation": relation_type,
                "fixed": fixed,
                "moving": moving,
                "parameters": _json_safe(relation.parameters),
            }
        )
        fixed_endpoint = _json_safe(relation.fixed_endpoint)
        moving_endpoint = _json_safe(relation.moving_endpoint)
        if fixed_endpoint:
            payload[-1]["fixedEndpoint"] = fixed_endpoint
        if moving_endpoint:
            payload[-1]["movingEndpoint"] = moving_endpoint
    return payload


class AssemblyHelper:
    """Small semantic wrapper around native build123d joints and compounds.

    Generated CAD scripts should express named part-local frames and source
    relationships here; this helper realizes those relationships with native
    build123d Joint objects and returns a labeled Compound assembly.
    """

    def __init__(self, name: str) -> None:
        self.label = label_text(name)
        self.children: list[Any] = []
        self.relations: list[MateRelation] = []

    def add(
        self,
        shape: Any,
        name: str,
        *details: object,
        color: Any | None = None,
    ) -> Any:
        label_shape(shape, name, *details, color=color)
        self.children.append(shape)
        return shape

    def add_module(self, name: str, children: Sequence[Any], *details: object, color: Any | None = None) -> Any:
        module = self.compound(children, label=label_text(name, *details))
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
        return label_shape(shape, name, *details, color=color)

    def datum(
        self,
        shape: Any,
        name: str,
        *details: object,
        color: Any | None = None,
    ) -> Any:
        return label_shape(shape, name, *details, color=color)

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
            label=label_text(label) if label is not None else label_text(relation, fixed_joint_label, moving_joint_label),
            relation=relation,
            fixed=fixed_joint_label,
            moving=moving_joint_label,
            parameters=options,
            fixed_endpoint=_mate_endpoint_payload(fixed_target, fixed_joint_label, fixed_joint),
            moving_endpoint=_mate_endpoint_payload(moving_target, moving_joint_label, moving_joint),
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
        compound = build123d.Compound(
            label=label or self.label,
            children=list(children if children is not None else self.children),
        )
        if children is None:
            assembly_mates = assembly_mate_payload(self.relations)
            if assembly_mates:
                compound.assembly_mates = assembly_mates
        return compound

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
    target_label = label_text(label or fixed_joint_label, "offset")
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
        return MateTarget(part=value[0], frame=label_text(value[1]))
    raise TypeError("Mate target must be MateTarget or (part, frame_name)")


def _joint_for_target(target_value: MateTarget) -> tuple[str, Any]:
    joints = getattr(target_value.part, "joints", None)
    if not isinstance(joints, Mapping):
        raise ValueError("Mate target part does not expose a build123d joints mapping")
    joint = joints.get(target_value.frame)
    if joint is not None:
        return target_value.frame, joint
    raise KeyError(f"Part does not define mate frame {target_value.frame!r}")


def _mate_endpoint_payload(target_value: MateTarget, frame: str, joint: Any) -> dict[str, Any]:
    endpoint: dict[str, Any] = {
        "part": _part_label(target_value.part),
        "frame": frame,
    }
    location = getattr(joint, "location", None)
    if location is None:
        location = getattr(joint, "joint_location", None)
    location_payload = _location_payload(location)
    if location_payload:
        endpoint.update(location_payload)
    return endpoint


def _part_label(part: Any) -> str:
    label = str(getattr(part, "label", "") or "").strip()
    if label:
        return label
    return type(part).__name__


def _location_payload(location: Any) -> dict[str, Any]:
    if location is None:
        return {}
    payload: dict[str, Any] = {}
    position = _vector_payload(getattr(location, "position", None))
    orientation = _vector_payload(getattr(location, "orientation", None))
    if position is not None:
        payload["position"] = position
    if orientation is not None:
        payload["orientation"] = orientation
    axes: dict[str, list[float]] = {}
    for axis_name, payload_key in (("x_axis", "x"), ("y_axis", "y"), ("z_axis", "z")):
        axis = getattr(location, axis_name, None)
        direction = _vector_payload(getattr(axis, "direction", None))
        if direction is not None:
            axes[payload_key] = direction
    if axes:
        payload["axes"] = axes
    return payload


def _vector_payload(value: Any) -> list[float] | None:
    if value is None:
        return None
    components: list[Any] = []
    for attr in ("X", "Y", "Z"):
        if hasattr(value, attr):
            components.append(getattr(value, attr))
    if len(components) != 3:
        for attr in ("x", "y", "z"):
            if hasattr(value, attr):
                components.append(getattr(value, attr))
        if len(components) > 3:
            components = components[-3:]
    if len(components) != 3:
        try:
            components = list(value)
        except TypeError:
            return None
    if len(components) < 3:
        return None
    try:
        return [float(components[0]), float(components[1]), float(components[2])]
    except (TypeError, ValueError):
        return None


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


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(child) for child in value]
    return str(value)


def _import_build123d() -> Any:
    try:
        import build123d
    except ModuleNotFoundError as exc:
        raise RuntimeError("cadpy.assembly requires build123d at runtime") from exc
    return build123d
