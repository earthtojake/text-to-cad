"""The public ``snapshot`` verbs — MIRRORS, one signature per format shape.

Snapshot used to be the schema's one adapter: a hand-written parser whose
option surface a policy test pinned by declaration. That exception is retired
(user directive, 2026-08-30): every rich option is typed ``str | dict | None``
— CLI-side one string (a saved name, inline JSON, or a path) interpreted by
the loaders the verb already uses; library-side a real dict through the same
parameter — so the signature IS the surface and ``cli_from_function`` derives
the CLI exactly as it does for ``build`` and ``validate``.

Three signature shapes cover the seven doors honestly (the old shared
signature advertised STEP-only options to every door and refused them at
runtime):

- STEP: the full surface — section mode, display, kinematics, animation, focus/hide.
- mesh (stl/3mf/glb) and dxf: view/list renders of untyped geometry.
- robot (urdf/sdf): the mesh shape plus ``joint_values``.

The polymorphic ``cadgen snapshot`` binds the UNION shape (STEP surface +
``joint_values``) over every kind at once: a job packet may mix formats, and
each input is still held to its own format's rules at resolve time.

Import discipline: nothing here may pull in OCP/build123d, or the snapshot
machinery itself, at module scope. A model script imports ``cadgen.step``
before its freshness gate runs, and this module rides along.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.results import SnapshotResult

# Which input kinds each format door's snapshot accepts. ``srdf`` has no door
# of its own (an SRDF's geometry comes from the URDF beside it) but the
# polymorphic door still routes one.
DOOR_KINDS: dict[str, tuple[str, ...]] = {
    "step": ("step", "stp"),
    "stl": ("stl",),
    "3mf": ("3mf",),
    "glb": ("glb",),
    "dxf": ("dxf",),
    "urdf": ("urdf",),
    "srdf": ("srdf",),
    "sdf": ("sdf",),
}

ALL_KINDS: tuple[str, ...] = tuple(
    dict.fromkeys(kind for kinds in DOOR_KINDS.values() for kind in kinds)
)


def _run(
    door_kinds: tuple[str, ...],
    *,
    target: Path | None,
    out: Path | None,
    job: Path | None,
    mode: str,
    camera: object,
    theme: object,
    display: object = None,
    kinematics: object = None,
    animation: object = None,
    time: float | None = None,
    joint_values: object = None,
    focus: tuple[str, ...] = (),
    hide: tuple[str, ...] = (),
    width: int | None,
    height: int | None,
    size_profile: str,
    view_labels: bool,
    debug: bool,
) -> SnapshotResult:
    # Imported here rather than at module scope: `cadgen.step` is on a model
    # script's pre-gate path, and the snapshot machinery drags in the catalog,
    # selector lookup and STEP targets.
    import io

    from cadgen.snapshot_cli import SnapshotOptions, run_snapshot

    options = SnapshotOptions(
        job=str(job) if job else "",
        input=str(target) if target else "",
        output=str(out) if out else "",
        mode=mode,
        width=width,
        height=height,
        size_profile=size_profile,
        view_labels=view_labels,
        debug=debug,
    )
    # `None` is "not given" for each of these, which is not the same as the
    # default: the machinery distinguishes them through the `<name>_specified`
    # flags, and a theme passed as its own default value must still count as
    # a choice (it changes the size profile).
    if theme is not None:
        options.theme, options.theme_specified = theme, True
    if display is not None:
        options.display, options.display_specified = display, True
    if camera is not None:
        options.camera, options.camera_specified = camera, True
    if kinematics is not None:
        options.kinematics, options.kinematics_specified = kinematics, True
    # `time` is the second half of the `animation` request — the moment in the
    # clip — and means nothing without the clip it indexes.
    if time is not None and animation is None:
        raise ValueError("time requires animation: name the clip the frame is taken from")
    if animation is not None:
        options.animation, options.animation_time, options.animation_specified = animation, time, True
    if joint_values is not None:
        options.joint_values, options.joint_values_specified = joint_values, True
    if focus:
        options.focus = [str(value) for value in focus]
    if hide:
        options.hide = [str(value) for value in hide]
    if options.focus and options.hide:
        raise ValueError("focus and hide cannot be used in the same snapshot")
    # An empty non-tty stream: the machinery reads a JSON packet off stdin when
    # given neither job nor target, and a library caller has no stdin to offer.
    return run_snapshot(options, kinds=door_kinds, stdin=io.StringIO())


def step_snapshot_verb(door: str):
    """The STEP-shaped ``snapshot`` verb: the full surface."""
    kinds = DOOR_KINDS[door]

    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        camera: str | dict | None = None,
        theme: str | dict | None = None,
        display: str | dict | None = None,
        kinematics: str | dict | None = None,
        animation: str | dict | None = None,
        time: float | None = None,
        focus: tuple[str, ...] = (),
        hide: tuple[str, ...] = (),
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render TARGET and report the files written.

        An explicit OUT is written exactly there and is cleared first, so a
        failed render leaves no file at all; a directory gets a generated
        timestamped name inside it. Rendering is a read: nothing about the
        model changes, though a STEP input whose tree is missing
        builds one.

        target: the model to render — a .step/.stp document (a model script
            is refused by naming the run that writes the document).
        out: destination image path (written EXACTLY there, cleared first),
            or a directory for a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}. When given it wins: target/out are ignored, and
            a missing job file raises FileNotFoundError.
        mode: view (default), section, or list.
        camera: a preset, an "azimuth:elevation" pair, or camera JSON.
        theme: a saved theme id, theme-settings JSON, or a theme file path.
        display: a display mode name, display-settings JSON, or a file path.
        kinematics: pose values — a declared preset name or {dof: value}
            JSON, validated against the model's kinematics declaration.
        animation: one still frame of a clip the model's .anim.js declares —
            the clip name (with --time), or {"clip": name, "time": seconds}
            JSON; layered over the kinematics pose the way the viewer does.
        time: seconds into the animation clip (default 0); requires animation.
        focus: occurrence ref rendered at full opacity (repeatable); the
            rest of the assembly is ghosted in place.
        hide: occurrence ref left out of the render (repeatable).
        width: output width in pixels, overriding the size profile.
        height: output height in pixels, overriding the size profile.
        size_profile: simple, diagnostic, labeled, assembly, presentation,
            or contact-sheet.
        view_labels: burn the camera/view label into the image.
        debug: report how each input's artifact resolved.
        """
        return _run(
            kinds,
            target=target, out=out, job=job, mode=mode,
            camera=camera, theme=theme, display=display, kinematics=kinematics,
            animation=animation, time=time,
            focus=focus, hide=hide, width=width, height=height,
            size_profile=size_profile, view_labels=view_labels, debug=debug,
        )

    return snapshot


def mesh_snapshot_verb(door: str):
    """The mesh/dxf-shaped verb: view/list renders of untyped geometry —
    no display, kinematics, section mode, or selection (nothing to act on)."""
    kinds = DOOR_KINDS[door]
    suffixes = ", ".join(f".{kind}" for kind in kinds)

    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        camera: str | dict | None = None,
        theme: str | dict | None = None,
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render TARGET and report the files written.

        An explicit OUT is written exactly there and is cleared first, so a
        failed render leaves no file at all; a directory gets a generated
        timestamped name inside it.

        target: the file to render. It accepts: {suffixes}.
        out: destination image path (written EXACTLY there, cleared first),
            or a directory for a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}. When given it wins: target/out are ignored.
        mode: view (default) or list.
        camera: a preset, an "azimuth:elevation" pair, or camera JSON.
        theme: a saved theme id, theme-settings JSON, or a theme file path.
        width: output width in pixels, overriding the size profile.
        height: output height in pixels, overriding the size profile.
        size_profile: simple, diagnostic, labeled, assembly, presentation,
            or contact-sheet.
        view_labels: burn the camera/view label into the image.
        debug: report how each input's artifact resolved.
        """
        return _run(
            kinds,
            target=target, out=out, job=job, mode=mode,
            camera=camera, theme=theme, width=width, height=height,
            size_profile=size_profile, view_labels=view_labels, debug=debug,
        )

    snapshot.__doc__ = snapshot.__doc__.replace("{suffixes}", suffixes)
    return snapshot


def robot_snapshot_verb(door: str):
    """The robot-shaped verb: the mesh shape plus joint posing."""
    kinds = DOOR_KINDS[door]
    suffixes = ", ".join(f".{kind}" for kind in kinds)

    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        joint_values: str | dict | None = None,
        camera: str | dict | None = None,
        theme: str | dict | None = None,
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render TARGET and report the files written.

        An explicit OUT is written exactly there and is cleared first, so a
        failed render leaves no file at all; a directory gets a generated
        timestamped name inside it.

        target: the robot description to render. It accepts: {suffixes}.
        out: destination image path (written EXACTLY there, cleared first),
            or a directory for a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}. When given it wins: target/out are ignored.
        mode: view (default) or list.
        joint_values: {joint: degrees} JSON posing the robot; joints not
            named stay at the rest pose.
        camera: a preset, an "azimuth:elevation" pair, or camera JSON.
        theme: a saved theme id, theme-settings JSON, or a theme file path.
        width: output width in pixels, overriding the size profile.
        height: output height in pixels, overriding the size profile.
        size_profile: simple, diagnostic, labeled, assembly, presentation,
            or contact-sheet.
        view_labels: burn the camera/view label into the image.
        debug: report how each input's artifact resolved.
        """
        return _run(
            kinds,
            target=target, out=out, job=job, mode=mode,
            joint_values=joint_values, camera=camera, theme=theme,
            width=width, height=height, size_profile=size_profile,
            view_labels=view_labels, debug=debug,
        )

    snapshot.__doc__ = snapshot.__doc__.replace("{suffixes}", suffixes)
    return snapshot


def polymorphic_snapshot_verb():
    """The union shape over every kind: `cadgen snapshot` routes by suffix,
    and a job packet may mix formats — each input is still held to its own
    format's rules at resolve time."""

    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        camera: str | dict | None = None,
        theme: str | dict | None = None,
        display: str | dict | None = None,
        kinematics: str | dict | None = None,
        animation: str | dict | None = None,
        time: float | None = None,
        joint_values: str | dict | None = None,
        focus: tuple[str, ...] = (),
        hide: tuple[str, ...] = (),
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render any supported input, routed by suffix.

        target: the file to render — STEP/STP, model script, STL/3MF/GLB,
            DXF, or a robot description (URDF/SRDF/SDF).
        out: destination image path (written EXACTLY there, cleared first),
            or a directory for a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}; jobs may mix formats. When given it wins.
        mode: view (default), section (STEP only), or list.
        camera: a preset, an "azimuth:elevation" pair, or camera JSON.
        theme: a saved theme id, theme-settings JSON, or a theme file path.
        display: display settings (STEP inputs only).
        kinematics: pose values for a STEP model's kinematics — a preset
            name or {dof: value} JSON.
        animation: one still frame of a STEP model's clip — the clip name
            (with --time), or {"clip": name, "time": seconds} JSON.
        time: seconds into the animation clip (default 0); requires animation.
        joint_values: {joint: degrees} JSON posing a robot description.
        focus: occurrence ref rendered at full opacity (STEP only).
        hide: occurrence ref left out of the render (STEP only).
        width: output width in pixels, overriding the size profile.
        height: output height in pixels, overriding the size profile.
        size_profile: simple, diagnostic, labeled, assembly, presentation,
            or contact-sheet.
        view_labels: burn the camera/view label into the image.
        debug: report how each input's artifact resolved.
        """
        return _run(
            ALL_KINDS,
            target=target, out=out, job=job, mode=mode,
            camera=camera, theme=theme, display=display, kinematics=kinematics,
            animation=animation, time=time,
            joint_values=joint_values, focus=focus, hide=hide,
            width=width, height=height, size_profile=size_profile,
            view_labels=view_labels, debug=debug,
        )

    return snapshot

