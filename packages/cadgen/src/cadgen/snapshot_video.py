"""The video half of a snapshot: the request, the frames on disk, and the encode.

``--animation CLIP --time SECONDS`` freezes one moment of a clip. ``--video``
renders the SPAN instead: the same prepared model, posed once per frame, and the
frames handed to ffmpeg. Everything above the frames is unchanged -- same theme,
same display settings, same camera, same size profile -- so a video is a still
that kept going.

Two things live here and nowhere else. The first is the request's shape: a
closed key set (``fps``, ``seconds``, ``start``, ``quality``, ``loop``) whose
values are checked before a browser starts, because the alternative is learning
that ``fps: 0`` is nonsense after three minutes of rendering. The second is
ffmpeg. It is an EXTERNAL BINARY, not a Python dependency -- nothing in the
wheel encodes video -- so it is resolved (``CADGEN_FFMPEG``, else ``PATH``) and
its absence reported BEFORE the first frame is drawn, naming the binary and how
to install it.

The commands are built by :func:`ffmpeg_video_commands` and run by
:func:`encode_video`, deliberately apart: the argv is what a test can hold, and
a quality preset that silently stops reaching the encoder is exactly the kind of
drift a test should catch without a video card.
"""

from __future__ import annotations

import contextlib
import math
import os
import shutil
import subprocess
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen.snapshot_core import SnapshotError, is_plain_object, load_json_text

# The request's closed vocabulary. Width and height are NOT here: a video is
# sized by --width/--height/--size-profile like every other render, and a second
# spelling of the same setting is a second thing to keep in agreement.
VIDEO_REQUEST_KEYS = frozenset({"fps", "seconds", "start", "quality", "loop"})
VIDEO_QUALITIES = ("draft", "review", "high")
DEFAULT_VIDEO_FPS = 30
DEFAULT_VIDEO_QUALITY = "review"
MIN_VIDEO_FPS = 1
# 120 fps is past any review need.
MAX_VIDEO_FPS = 120
# The ceiling that actually bounds the work, because the schedule is fps TIMES
# seconds: an fps bound alone still lets `{"fps": 30, "seconds": 3000}` -- a
# caller writing milliseconds -- schedule 90,000 frames, each rendered, carried
# base64 across the driver pipe, and written full-size into a temp directory
# before ffmpeg sees one of them. 7200 frames is four minutes of review at 30
# fps and tens of gigabytes of frames at the default size. The page enforces
# the same ceiling (framePlan FRAME_PLAN_MAX_FRAMES), because it is where the
# clip-duration default for `seconds` is resolved.
MAX_VIDEO_FRAMES = 7200

# The OUT extension picks the container -- there is no `format` key, because the
# path already said it and two spellings can disagree.
VIDEO_CONTAINERS = {".mp4": "mp4", ".gif": "gif"}

# Zero-padded so the shell-free image2 sequence reads in order; six digits is
# 27 minutes at the 120 fps ceiling.
VIDEO_FRAME_PATTERN = "frame_%06d.png"

# yuv420p subsamples chroma 2x2, so an odd width or height is rejected by the
# encoder outright. Cropping the odd row/column keeps every remaining pixel
# exactly as rendered; scaling to an even size would resample the whole frame to
# hide one line. A no-op on the even sizes every size profile produces.
VIDEO_EVEN_DIMENSION_FILTER = "crop=trunc(iw/2)*2:trunc(ih/2)*2"

# H.264 is the everywhere-playable pair with -pix_fmt yuv420p. Quality is one
# word at the CLI and a (crf, preset) pair here: lower crf is better and bigger,
# a slower preset spends more CPU for the same crf.
MP4_QUALITY_SETTINGS = {
    "draft": {"crf": "30", "preset": "veryfast"},
    "review": {"crf": "23", "preset": "medium"},
    "high": {"crf": "16", "preset": "slow"},
}

# GIF has no colour beyond a 256-entry palette, so quality is the palette and the
# dithering that fakes what the palette cannot hold. `stats_mode=diff` weights
# the palette toward the pixels that MOVE, which is the whole subject of a
# mechanism clip and the one setting worth its cost at the top end.
#
# A GIF also stores its per-frame delay in HUNDREDTHS of a second, so the rate a
# player shows is the nearest 1/100 s to the requested one (30 fps plays as
# 33.3, 12 as 12.5). The frames themselves are still rendered at the fps asked
# for; an exact rate wants .mp4.
GIF_QUALITY_SETTINGS = {
    "draft": {"max_colors": "64", "dither": "bayer", "stats_mode": ""},
    "review": {"max_colors": "128", "dither": "sierra2_4a", "stats_mode": ""},
    "high": {"max_colors": "256", "dither": "sierra2_4a", "stats_mode": "diff"},
}

GIF_PALETTE_NAME = "palette.png"


def normalize_video_request(value: object, *, where: str) -> dict[str, object]:
    """The job's ``video`` field, validated: ``{fps, seconds, start, quality, loop}``.

    Both spellings land here -- the flag's JSON and a job packet's field -- so
    one validator holds the shape. ``seconds`` stays ``None`` when the caller
    named none: the default is what is LEFT of the clip from ``start``, which
    only the page can work out (the choreography is JavaScript, and so is the
    duration and the loop flag it declares), so the page resolves it and reports
    the frame count back. Everything the page resolves is bounded there too --
    the frame ceiling below can only be applied here to a span the caller named.
    """
    if not is_plain_object(value):
        raise SnapshotError(
            f"{where} must be a {{fps, seconds, start, quality, loop}} object; "
            f"supported keys: {', '.join(sorted(VIDEO_REQUEST_KEYS))}"
        )
    unknown = sorted(set(value) - VIDEO_REQUEST_KEYS)
    if unknown:
        raise SnapshotError(
            f"{where} has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(VIDEO_REQUEST_KEYS))}"
        )

    raw_fps = value.get("fps", DEFAULT_VIDEO_FPS)
    if isinstance(raw_fps, bool) or not isinstance(raw_fps, int):
        raise SnapshotError(
            f"{where} fps must be a whole number of frames per second "
            f"({MIN_VIDEO_FPS}..{MAX_VIDEO_FPS}), got {raw_fps!r}"
        )
    if not MIN_VIDEO_FPS <= raw_fps <= MAX_VIDEO_FPS:
        raise SnapshotError(f"{where} fps must be {MIN_VIDEO_FPS}..{MAX_VIDEO_FPS}, got {raw_fps}")

    raw_seconds = value.get("seconds")
    seconds: float | None = None
    if raw_seconds is not None:
        seconds = _finite_number(raw_seconds, where=where, field="seconds")
        if seconds <= 0:
            raise SnapshotError(f"{where} seconds must be greater than 0, got {raw_seconds!r}")
        frames = round(seconds * raw_fps)
        if frames > MAX_VIDEO_FRAMES:
            raise SnapshotError(
                f"{where} {seconds:g}s at {raw_fps} fps schedules {frames} frames, past the "
                f"{MAX_VIDEO_FRAMES}-frame ceiling (every frame is a full-size PNG on disk "
                "before ffmpeg runs)"
            )

    raw_start = value.get("start", 0)
    start = _finite_number(raw_start, where=where, field="start")
    if start < 0:
        raise SnapshotError(f"{where} start must be seconds >= 0, got {raw_start!r}")

    quality = str(value.get("quality", DEFAULT_VIDEO_QUALITY) or DEFAULT_VIDEO_QUALITY).strip().lower()
    if quality not in VIDEO_QUALITIES:
        raise SnapshotError(
            f"{where} quality must be one of: {', '.join(VIDEO_QUALITIES)}; got {value.get('quality')!r}"
        )

    raw_loop = value.get("loop", True)
    if not isinstance(raw_loop, bool):
        raise SnapshotError(f"{where} loop must be true or false, got {raw_loop!r}")

    return {
        "fps": raw_fps,
        "seconds": seconds,
        "start": start,
        "quality": quality,
        "loop": raw_loop,
    }


def _finite_number(value: object, *, where: str, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SnapshotError(f"{where} {field} must be a number of seconds, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise SnapshotError(f"{where} {field} must be a finite number of seconds, got {value!r}")
    return number


def parse_video_option(raw_video: object, *, cwd: Path) -> dict[str, object]:
    """``--video`` in job form. Inline JSON, a path to a JSON file, or -- from a
    ``snapshot(video={...})`` call -- the object itself, exactly as ``--display``
    and ``--camera`` take their three spellings."""
    if is_plain_object(raw_video):
        return normalize_video_request(raw_video, where="--video")
    video = str(raw_video or "").strip()
    if not video:
        raise SnapshotError(
            "--video requires a JSON object or a JSON file path: "
            f"{{{', '.join(sorted(VIDEO_REQUEST_KEYS))}}}"
        )
    if video.startswith("{"):
        return normalize_video_request(load_json_text(video, "--video"), where="--video")

    video_path = Path(video).expanduser()
    if not video_path.is_absolute():
        video_path = cwd / video_path
    if not video_path.exists():
        raise SnapshotError(f"Video JSON file does not exist: {video}")
    return normalize_video_request(
        load_json_text(video_path.read_text(encoding="utf-8"), str(video_path)),
        where=str(video_path),
    )


def video_container_for_path(output_path: str) -> str:
    """``mp4`` or ``gif`` -- the container the OUT extension picks.

    Refused by name rather than guessed: an encode into a container the suffix
    does not name writes a file every downstream reader mis-handles.
    """
    suffix = Path(str(output_path or "")).suffix.lower()
    container = VIDEO_CONTAINERS.get(suffix)
    if container is None:
        supported = ", ".join(sorted(VIDEO_CONTAINERS))
        raise SnapshotError(
            f"a video output must be named {supported}; got {output_path or '(no path)'}"
        )
    return container


def validate_video_output(video: dict[str, object], output_path: str) -> str:
    """The container this request will encode into, with the container's own
    rules applied. ``loop`` is a GIF concept: an mp4 carries no loop count, so a
    job that sets one is refused rather than encoded with the flag dropped."""
    container = video_container_for_path(output_path)
    if container == "mp4" and video.get("loop") is not True:
        raise SnapshotError(
            "video loop is a GIF setting: an .mp4 carries no loop count "
            "(name a .gif output, or drop loop and let the player decide)"
        )
    return container


def ffmpeg_binary() -> str:
    """The ffmpeg this run will encode with.

    Resolved BEFORE the first frame is rendered. Encoding is the last step of a
    job whose first steps can take minutes, and discovering there is no encoder
    at the end of that is the one failure this check exists to prevent.
    """
    override = str(os.environ.get("CADGEN_FFMPEG") or "").strip()
    if override:
        resolved = shutil.which(override) or (override if Path(override).is_file() else "")
        if not resolved:
            raise SnapshotError(
                f"CADGEN_FFMPEG names an ffmpeg that is not there: {override}"
            )
        return resolved
    found = shutil.which("ffmpeg")
    if not found:
        raise SnapshotError(
            "cadgen renders video frames itself and encodes them with ffmpeg, which is not "
            "installed. Install it (macOS: brew install ffmpeg; Debian/Ubuntu: apt install "
            "ffmpeg; Windows: winget install ffmpeg) or point CADGEN_FFMPEG at one, then "
            "retry. Without --video the same command still writes a PNG still."
        )
    return found


def ffmpeg_video_commands(
    binary: str,
    *,
    frames_dir: Path,
    output_path: Path,
    fps: int,
    container: str,
    quality: str,
    loop: bool,
) -> list[list[str]]:
    """The ffmpeg invocation(s) this encode runs, in order.

    One command for mp4; two for GIF, because a decent GIF needs a palette
    built from the frames before the frames can be mapped onto it. Built apart
    from :func:`encode_video` so the argv is testable without an encoder.
    """
    frames = str(frames_dir / VIDEO_FRAME_PATTERN)
    if container == "mp4":
        settings = MP4_QUALITY_SETTINGS[quality]
        return [
            [
                binary, "-y", "-nostdin", "-loglevel", "error",
                "-framerate", str(fps), "-i", frames,
                "-vf", VIDEO_EVEN_DIMENSION_FILTER,
                "-c:v", "libx264",
                "-preset", settings["preset"],
                "-crf", settings["crf"],
                # Chroma subsampling every player, browser and QuickTime accepts.
                "-pix_fmt", "yuv420p",
                # The container is named, not inferred: the file being written is
                # a temp name (the atomic rename below), so its suffix says .tmp.
                "-f", "mp4",
                str(output_path),
            ]
        ]
    settings = GIF_QUALITY_SETTINGS[quality]
    palette = frames_dir / GIF_PALETTE_NAME
    palettegen = f"palettegen=max_colors={settings['max_colors']}"
    if settings["stats_mode"]:
        palettegen = f"{palettegen}:stats_mode={settings['stats_mode']}"
    return [
        [
            binary, "-y", "-nostdin", "-loglevel", "error",
            "-framerate", str(fps), "-i", frames,
            "-vf", f"{VIDEO_EVEN_DIMENSION_FILTER},{palettegen}",
            str(palette),
        ],
        [
            binary, "-y", "-nostdin", "-loglevel", "error",
            "-framerate", str(fps), "-i", frames,
            "-i", str(palette),
            "-lavfi", f"{VIDEO_EVEN_DIMENSION_FILTER}[c];[c][1:v]paletteuse=dither={settings['dither']}",
            # The GIF muxer's loop count: 0 repeats forever, -1 plays once.
            "-loop", "0" if loop else "-1",
            "-f", "gif",
            str(output_path),
        ],
    ]


def encode_video(
    frames_dir: Path,
    *,
    output_path: Path,
    fps: int,
    container: str,
    quality: str,
    loop: bool,
    binary: str | None = None,
) -> None:
    """Encode the frames in ``frames_dir`` to ``output_path``, atomically.

    ffmpeg writes to a temp name in the TARGET's own directory and the finished
    file is renamed over it, the same temp-plus-rename contract every still
    goes through (write_output_payload). A rename across filesystems is not
    atomic, which is why the temp cannot live beside the frames: an encode that
    dies half way must leave nothing at the name the caller is about to read.
    """
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f"{target.name}{temp_suffix()}")
    commands = ffmpeg_video_commands(
        binary or ffmpeg_binary(),
        frames_dir=Path(frames_dir),
        output_path=staged,
        fps=fps,
        container=container,
        quality=quality,
        loop=loop,
    )
    try:
        for command in commands:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0:
                # ffmpeg says what it could not do on stderr and says it LAST; the
                # head is banner and stream description nobody needs.
                detail = "\n".join((completed.stderr or "").strip().splitlines()[-8:])
                raise SnapshotError(
                    f"ffmpeg could not encode the {container} (exit {completed.returncode}): "
                    f"{detail or 'no error output'}"
                )
        replace_atomic(staged, target)
    finally:
        # Suppressed for the reason write_bytes_atomic suppresses it: on Windows
        # the handle that blocks a rename blocks the delete too, and letting that
        # escape here would mask the failure the caller needs to see.
        with contextlib.suppress(OSError):
            staged.unlink(missing_ok=True)
