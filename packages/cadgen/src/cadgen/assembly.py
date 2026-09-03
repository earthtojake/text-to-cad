from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class MateTarget:
    """A named native build123d joint on a part-like shape."""

    part: Any
    frame: str



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


class AssemblyHelper:
    """Small semantic wrapper around native build123d joints and compounds.

    Generated CAD scripts should express named part-local frames and source
    relationships here; this helper realizes those relationships with native
    build123d Joint objects and returns a labeled Compound assembly.
    """

    def __init__(self, name: str) -> None:
        self.label = label_text(name)
        self.children: list[Any] = []

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
    ) -> None:
        """Place ``moving`` against ``fixed`` through their named joints.

        A positioning tool: the placement lands in the geometry and nothing
        else is recorded. ``relation`` and ``label`` name the intent in source
        for the reader; persisted motion semantics are ``@step(kinematics=)``.
        """
        del relation, label
        fixed_target = _normalize_target(fixed)
        moving_target = _normalize_target(moving)
        _, fixed_joint = _joint_for_target(fixed_target)
        _, moving_joint = _joint_for_target(moving_target)
        options = {key: value for key, value in connect_options.items() if value is not None}
        fixed_joint.connect_to(moving_joint, **options)

    def face_to_face(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        offset: float | Sequence[float] | Any | None = None,
        label: str | None = None,
    ) -> None:
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
    ) -> None:
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
    ) -> None:
        return self.connect(fixed, moving, relation="revolute", label=label, angle=angle)

    def linear(
        self,
        fixed: MateTarget | tuple[Any, str],
        moving: MateTarget | tuple[Any, str],
        *,
        position: float | None = None,
        label: str | None = None,
    ) -> None:
        return self.connect(fixed, moving, relation="linear", label=label, position=position)

    def compound(self, children: Sequence[Any] | None = None, *, label: str | None = None) -> Any:
        build123d = _import_build123d()
        compound = build123d.Compound(
            label=label or self.label,
            children=list(children if children is not None else self.children),
        )
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
        raise RuntimeError("cadgen.assembly requires build123d at runtime") from exc
    return build123d
