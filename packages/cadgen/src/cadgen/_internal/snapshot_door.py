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

- STEP: the full surface — section mode and its plane, display, kinematics, animation, focus/hide.
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

import contextvars
import functools
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


# Direct calls need the same omitted-versus-explicit distinction the generated
# CLI preserves. The wrapper retains the public function's inspectable
# signature through ``functools.wraps``; ContextVar keeps concurrent calls
# independent.
_EXPLICIT_SNAPSHOT_OPTIONS: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "cadgen_explicit_snapshot_options", default=frozenset()
)


def _track_explicit_options(function):
    @functools.wraps(function)
    def tracked(*args, **kwargs):
        token = _EXPLICIT_SNAPSHOT_OPTIONS.set(frozenset(kwargs))
        try:
            return function(*args, **kwargs)
        finally:
            _EXPLICIT_SNAPSHOT_OPTIONS.reset(token)

    return tracked


def _run(
    door_kinds: tuple[str, ...],
    *,
    target: Path | None,
    out: Path | None,
    job: Path | None,
    mode: str,
    camera: object,
    display: object = None,
    kinematics: object = None,
    animation: object = None,
    time: float | None = None,
    video: object = None,
    section: object = None,
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
    options.mode_specified = "mode" in _EXPLICIT_SNAPSHOT_OPTIONS.get()
    # `None` is every optional's documented default, so passing it explicitly is
    # the same as leaving it out: `snapshot(display=None)` renders the default
    # display. The generated CLI never passes one (an absent flag is an absent
    # keyword), so this is the library caller's rule.
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
    # `video` is the other half of the same request: the SPAN of the clip rather
    # than one moment of it. It needs the clip for the same reason `time` does,
    # and it cannot be combined with `time` — one frame or a sequence, never
    # both, and silently honouring one of them would answer the wrong question.
    if video is not None and animation is None:
        raise ValueError("video requires animation: name the clip the sequence renders")
    if video is not None and time is not None:
        raise ValueError(
            "video and time cannot be used together: time freezes one frame, video renders "
            "the span — use video start/seconds to say where the sequence begins"
        )
    if animation is not None:
        options.animation, options.animation_time, options.animation_specified = animation, time, True
    if video is not None:
        options.video, options.video_specified = video, True
    if section is not None:
        options.section, options.section_specified = section, True
    if joint_values is not None:
        options.joint_values, options.joint_values_specified = joint_values, True
    options.focus = _refs(focus, "focus")
    options.hide = _refs(hide, "hide")
    options.focus_specified, options.hide_specified = bool(options.focus), bool(options.hide)
    if options.focus and options.hide and job is None:
        raise ValueError("focus and hide cannot be used in the same snapshot")
    return run_snapshot(options, kinds=door_kinds)


def _refs(value: object, name: str) -> list[str] | None:
    """``focus``/``hide`` as a list of refs: a sequence of strings, never one string.

    ``focus="#o1.2"`` is the natural slip from the CLI's repeatable flag, and a
    string IS a sequence — of characters, each of which used to be looked up as
    a ref of its own.
    """
    if isinstance(value, (str, bytes)):
        raise ValueError(
            f"{name} takes a sequence of occurrence refs, not one string: "
            f"pass {name}=({value!r},)"
        )
    refs = [str(ref) for ref in (value or ())]
    return refs or None


def step_snapshot_verb(door: str):
    """The STEP-shaped ``snapshot`` verb: the full surface."""
    kinds = DOOR_KINDS[door]

    @_track_explicit_options
    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        section: str | dict | None = None,
        camera: str | dict | None = None,
        display: str | dict | None = None,
        kinematics: str | dict | None = None,
        animation: str | dict | None = None,
        time: float | None = None,
        video: str | dict | None = None,
        focus: tuple[str, ...] = (),
        hide: tuple[str, ...] = (),
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render TARGET and report the files written.

        An explicit OUT is written exactly there. A refused request leaves an
        existing OUT untouched; once the request is accepted OUT is cleared, so
        a failed build or render leaves no file at all. A directory gets a
        generated timestamped name inside it. Rendering is a read: nothing
        about the model changes, though a STEP input whose tree is missing
        builds one.

        target: the model to render — a .step/.stp document (a model script
            is refused by naming the run that writes the document).
        out: destination path, written EXACTLY there — .png (section mode
            also writes .svg, --video writes .mp4/.gif) — or a directory for
            a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}. When given it wins: target/out are ignored, and
            the other flags override every job in it.
        mode: view (default), section, or list.
        section: where --mode section cuts, as PLANE[:OFFSET] — the plane is
            XY, XZ or YZ (default XY) and the offset moves it along its normal
            in model units (default 0): XZ:12.5 cuts at Y=12.5. In a job,
            {"plane": "XZ", "offset": 12.5}.
        camera: a preset (front, back, left, right, top, bottom, iso), an
            "azimuth:elevation" pair, or camera JSON;
            orthographicHalfHeight preserves an orthographic view's scale.
            Projection and focalLength (20..200 mm) belong in display.camera.
        display: a preset name, grouped display JSON, or JSON file path. Presets
            are solid (default), render, xray, hidden-line and wireframe.
            Omitted groups inherit the preset; group objects imply enabled unless
            explicitly false. appearance is light (default) or dark.
        kinematics: pose values — a declared preset name or {dof: value}
            JSON, validated against the model's kinematics declaration;
            available in every display mode.
        animation: one still frame of a clip embedded in the document sidecar —
            the clip name (with --time),
            or {"clip": name, "time": seconds} JSON. It is layered over the
            kinematics pose.
        time: seconds into the animation clip (default 0); requires animation.
        video: render the clip as a VIDEO instead of one frame, into the .mp4 or
            .gif OUT names — {"fps": 30, "seconds": <what is left of the clip>,
            "start": 0, "quality": "review", "loop": true} JSON or a path to it;
            requires animation, excludes time, and needs ffmpeg on PATH.
        focus: occurrence ref rendered at full opacity (repeatable); the rest
            of the assembly is ghosted in place.
        hide: occurrence ref left out (repeatable).
        width: output width in pixels (1..8192), overriding the size profile;
            with --job it sizes every output in the packet.
        height: output height in pixels (1..8192), overriding the size profile.
        size_profile: simple (1200x900), simple-square (1024x1024), diagnostic
            (1600x1200, the default), labeled (1600x1200), assembly (1800x1200),
            assembly-large (1920x1440), presentation (2400x1600),
            presentation-large (2800x1800), or contact-sheet (2400x1600).
        view_labels: burn the camera/view label into the image.
        debug: report artifact resolution and measured browser stages in the
            result's debug field (read it with --json).
        """
        return _run(
            kinds,
            target=target, out=out, job=job, mode=mode,
            camera=camera, display=display, kinematics=kinematics,
            animation=animation, time=time, video=video, section=section,
            focus=focus, hide=hide, width=width, height=height,
            size_profile=size_profile, view_labels=view_labels, debug=debug,
        )

    return snapshot


def mesh_snapshot_verb(door: str):
    """The mesh/dxf-shaped verb: view/list renders of untyped geometry —
    no kinematics, section mode, or selection (nothing to act on)."""
    kinds = DOOR_KINDS[door]
    suffixes = ", ".join(f".{kind}" for kind in kinds)

    @_track_explicit_options
    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        camera: str | dict | None = None,
        display: str | dict | None = None,
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render TARGET and report the files written.

        An explicit OUT is written exactly there. A refused request leaves an
        existing OUT untouched; once the request is accepted OUT is cleared, so
        a failed render leaves no file at all. A directory gets a generated
        timestamped name inside it.

        target: the file to render. It accepts: {suffixes}.
        out: destination .png path, written EXACTLY there, or a directory
            for a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}. When given it wins: target/out are ignored, and
            the other flags override every job in it.
        mode: view (default) or list.
        camera: a preset (front, back, left, right, top, bottom, iso), an
            "azimuth:elevation" pair, or camera JSON;
            orthographicHalfHeight preserves an orthographic view's scale.
            Projection and focalLength (20..200 mm) belong in display.camera.
        display: solid (default) or render, grouped display JSON, or a JSON file
            path. Omitted groups inherit the preset; appearance defaults to
            light. Projection belongs in display.camera. edges, clip, exploded,
            the xray, hidden-line and wireframe modes and the hidden/off surface
            styles describe a STEP model and are refused here.
        width: output width in pixels (1..8192), overriding the size profile;
            with --job it sizes every output in the packet.
        height: output height in pixels (1..8192), overriding the size profile.
        size_profile: simple (1200x900), simple-square (1024x1024), diagnostic
            (1600x1200, the default), labeled (1600x1200), assembly (1800x1200),
            assembly-large (1920x1440), presentation (2400x1600),
            presentation-large (2800x1800), or contact-sheet (2400x1600).
        view_labels: burn the camera/view label into the image.
        debug: report artifact resolution and measured browser stages in the
            result's debug field (read it with --json).
        """
        return _run(
            kinds,
            target=target, out=out, job=job, mode=mode,
            camera=camera, display=display, width=width, height=height,
            size_profile=size_profile, view_labels=view_labels, debug=debug,
        )

    snapshot.__doc__ = snapshot.__doc__.replace("{suffixes}", suffixes)
    return snapshot


def robot_snapshot_verb(door: str):
    """The robot-shaped verb: the mesh shape plus joint posing."""
    kinds = DOOR_KINDS[door]
    suffixes = ", ".join(f".{kind}" for kind in kinds)

    @_track_explicit_options
    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        joint_values: str | dict | None = None,
        camera: str | dict | None = None,
        display: str | dict | None = None,
        width: int | None = None,
        height: int | None = None,
        size_profile: str = "",
        view_labels: bool = False,
        debug: bool = False,
    ) -> SnapshotResult:
        """Render TARGET and report the files written.

        An explicit OUT is written exactly there. A refused request leaves an
        existing OUT untouched; once the request is accepted OUT is cleared, so
        a failed render leaves no file at all. A directory gets a generated
        timestamped name inside it.

        target: the robot description to render. It accepts: {suffixes}.
        out: destination .png path, written EXACTLY there, or a directory
            for a generated timestamped name.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}. When given it wins: target/out are ignored, and
            the other flags override every job in it.
        mode: view (default) or list.
        joint_values: {joint: degrees} JSON posing the robot; joints not
            named stay at the rest pose.
        camera: a preset (front, back, left, right, top, bottom, iso), an
            "azimuth:elevation" pair, or camera JSON;
            orthographicHalfHeight preserves an orthographic view's scale.
            Projection and focalLength (20..200 mm) belong in display.camera.
        display: solid (default) or render, grouped display JSON, or a JSON file
            path. Omitted groups inherit the preset; appearance defaults to
            light. Projection belongs in display.camera. edges, clip, exploded,
            the xray, hidden-line and wireframe modes and the hidden/off surface
            styles describe a STEP model and are refused here.
        width: output width in pixels (1..8192), overriding the size profile;
            with --job it sizes every output in the packet.
        height: output height in pixels (1..8192), overriding the size profile.
        size_profile: simple (1200x900), simple-square (1024x1024), diagnostic
            (1600x1200, the default), labeled (1600x1200), assembly (1800x1200),
            assembly-large (1920x1440), presentation (2400x1600),
            presentation-large (2800x1800), or contact-sheet (2400x1600).
        view_labels: burn the camera/view label into the image.
        debug: report artifact resolution and measured browser stages in the
            result's debug field (read it with --json).
        """
        return _run(
            kinds,
            target=target, out=out, job=job, mode=mode,
            joint_values=joint_values, camera=camera, display=display,
            width=width, height=height, size_profile=size_profile,
            view_labels=view_labels, debug=debug,
        )

    snapshot.__doc__ = snapshot.__doc__.replace("{suffixes}", suffixes)
    return snapshot


def polymorphic_snapshot_verb():
    """The union shape over every kind: `cadgen snapshot` routes by suffix,
    and a job packet may mix formats — each input is still held to its own
    format's rules at resolve time."""

    @_track_explicit_options
    def snapshot(
        target: Path | None = None,
        out: Path | None = None,
        *,
        job: Path | None = None,
        mode: str = "view",
        section: str | dict | None = None,
        camera: str | dict | None = None,
        display: str | dict | None = None,
        kinematics: str | dict | None = None,
        animation: str | dict | None = None,
        time: float | None = None,
        video: str | dict | None = None,
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

        target: the document to render — STEP/STP, STL/3MF/GLB, DXF, or a
            robot description (URDF/SRDF/SDF). Run model scripts first, then
            snapshot the document they write.
        out: destination path, written EXACTLY there — .png (a STEP section
            also writes .svg, a STEP --video writes .mp4/.gif) — or a directory
            for a generated timestamped name. A refused request leaves an
            existing OUT untouched; an accepted one clears it first.
        job: a render-job JSON file — one job, an array of them, or
            {"jobs": [...]}; jobs may mix formats. When given it wins, and the
            other flags override every job in it.
        mode: view (default), section (STEP only), or list.
        section: where a STEP --mode section cuts, as PLANE[:OFFSET] — XY, XZ
            or YZ, offset along the plane's normal in model units: XZ:12.5.
        camera: a preset (front, back, left, right, top, bottom, iso), an
            "azimuth:elevation" pair, or camera JSON;
            orthographicHalfHeight preserves an orthographic view's scale.
            Projection and focalLength (20..200 mm) belong in display.camera.
        display: solid (default), render, xray, hidden-line or wireframe, grouped
            display JSON, or a JSON file path. appearance defaults to light.
            Omitted groups inherit the preset. edges, clip, exploded, the xray,
            hidden-line and wireframe modes and the hidden/off surface styles
            describe a STEP model; every other input takes solid or render.
        kinematics: pose values for a STEP model's kinematics — a preset
            name or {dof: value} JSON; available in every display mode.
        animation: one still frame of a STEP model's clip — the clip name
            (with --time), or {"clip": name, "time": seconds} JSON.
        time: seconds into the animation clip (default 0); requires animation.
        video: render a STEP model's clip as a VIDEO into a .mp4/.gif OUT —
            {"fps": 30, "seconds": <what is left of the clip>, "start": 0,
            "quality": "review", "loop": true} JSON or a path to it; requires
            animation, excludes time, and needs ffmpeg on PATH.
        joint_values: {joint: degrees} JSON posing a robot (URDF/SRDF/SDF
            only); available in every display mode.
        focus: occurrence ref rendered at full opacity (STEP only,
            repeatable); the rest of the assembly is ghosted in place.
        hide: occurrence ref left out (STEP only, repeatable).
        width: output width in pixels (1..8192), overriding the size profile;
            with --job it sizes every output in the packet.
        height: output height in pixels (1..8192), overriding the size profile.
        size_profile: simple (1200x900), simple-square (1024x1024), diagnostic
            (1600x1200, the default), labeled (1600x1200), assembly (1800x1200),
            assembly-large (1920x1440), presentation (2400x1600),
            presentation-large (2800x1800), or contact-sheet (2400x1600).
        view_labels: burn the camera/view label into the image.
        debug: report artifact resolution and measured browser stages in the
            result's debug field (read it with --json).
        """
        return _run(
            ALL_KINDS,
            target=target, out=out, job=job, mode=mode,
            camera=camera, display=display, kinematics=kinematics,
            animation=animation, time=time, video=video, section=section,
            joint_values=joint_values, focus=focus, hide=hide,
            width=width, height=height, size_profile=size_profile,
            view_labels=view_labels, debug=debug,
        )

    return snapshot
