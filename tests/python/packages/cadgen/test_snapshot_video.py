"""`--video` renders the SPAN of a clip; these cover its refusals and its encoder.

A video is expensive in a way a still is not: minutes of frames, then an encode.
So everything that can be wrong about the request is decided before a browser
starts -- the closed key set, the fps range, the clip it needs, the container
its OUT names, and whether ffmpeg is even installed -- and each of those is a
case here.

The encoder half is covered by the ARGV rather than by running anything. A
quality preset that silently stopped reaching ffmpeg would still produce a
playable file, so a test that checks the file proves nothing; a test that holds
the command proves the mapping. Nothing here renders, encodes, or needs ffmpeg
on PATH.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_cli import SnapshotOptions, load_job_from_options  # noqa: E402
from cadgen.snapshot_core import SnapshotError, normalize_common_job  # noqa: E402
from cadgen.snapshot_video import (  # noqa: E402
    DEFAULT_VIDEO_FPS,
    DEFAULT_VIDEO_QUALITY,
    GIF_PALETTE_NAME,
    MAX_VIDEO_FPS,
    MAX_VIDEO_FRAMES,
    VIDEO_FRAME_PATTERN,
    VIDEO_QUALITIES,
    ffmpeg_video_commands,
    normalize_video_request,
    parse_video_option,
    validate_video_output,
    video_container_for_path,
)


class RequestShape(unittest.TestCase):
    """The request normalizes to one closed shape, whichever way it arrived."""

    def test_an_empty_request_is_the_documented_defaults(self):
        self.assertEqual(
            normalize_video_request({}, where="--video"),
            {
                "fps": DEFAULT_VIDEO_FPS,
                # None, not a number: the default span is what is LEFT of the
                # clip from start, and only the page can work that out.
                "seconds": None,
                "start": 0.0,
                "quality": DEFAULT_VIDEO_QUALITY,
                "loop": True,
            },
        )

    def test_every_field_survives_the_normalization(self):
        self.assertEqual(
            normalize_video_request(
                {"fps": 60, "seconds": 2.5, "start": 1, "quality": "high", "loop": False},
                where="--video",
            ),
            {"fps": 60, "seconds": 2.5, "start": 1.0, "quality": "high", "loop": False},
        )

    def test_an_unknown_key_names_the_accepted_ones(self):
        with self.assertRaises(SnapshotError) as ctx:
            normalize_video_request({"framerate": 30}, where="--video")
        message = str(ctx.exception)
        self.assertIn("framerate", message)
        for accepted in ("fps", "seconds", "start", "quality", "loop"):
            self.assertIn(accepted, message)

    def test_out_of_range_and_mistyped_values_are_refused(self):
        cases = [
            ({"fps": 0}, "fps"),
            ({"fps": MAX_VIDEO_FPS + 1}, "fps"),
            # 29.97 is a real frame rate and not one this schedules: a whole
            # number of frames per second is what the plan divides by.
            ({"fps": 29.97}, "fps"),
            ({"fps": True}, "fps"),
            ({"seconds": 0}, "seconds"),
            ({"seconds": -1}, "seconds"),
            ({"seconds": "4"}, "seconds"),
            ({"start": -0.5}, "start"),
            ({"quality": "ultra"}, "quality"),
            ({"loop": "yes"}, "loop"),
        ]
        for payload, field in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(SnapshotError) as ctx:
                    normalize_video_request(payload, where="--video")
                self.assertIn(field, str(ctx.exception))

    def test_the_scheduled_frame_count_is_bounded_not_just_the_fps(self):
        # The fps ceiling bounds one multiplicand. A caller writing milliseconds
        # for seconds reaches a six-figure schedule through the other one, and
        # every frame is a full-size PNG on disk before ffmpeg runs.
        with self.assertRaises(SnapshotError) as ctx:
            normalize_video_request({"fps": 30, "seconds": 3000}, where="--video")
        message = str(ctx.exception)
        self.assertIn("90000 frames", message)
        self.assertIn(str(MAX_VIDEO_FRAMES), message)
        at_the_ceiling = normalize_video_request(
            {"fps": 30, "seconds": MAX_VIDEO_FRAMES / 30}, where="--video"
        )
        self.assertEqual(at_the_ceiling["seconds"], MAX_VIDEO_FRAMES / 30)

    def test_a_non_object_request_says_what_the_object_is(self):
        with self.assertRaises(SnapshotError) as ctx:
            normalize_video_request("30", where="--video")
        self.assertIn("fps", str(ctx.exception))

    def test_the_flag_takes_inline_json_a_file_or_the_object_itself(self):
        expected = {"fps": 24, "seconds": None, "start": 0.0, "quality": "draft", "loop": True}
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            (cwd / "video.json").write_text(json.dumps({"fps": 24, "quality": "draft"}), encoding="utf-8")
            self.assertEqual(parse_video_option('{"fps": 24, "quality": "draft"}', cwd=cwd), expected)
            self.assertEqual(parse_video_option("video.json", cwd=cwd), expected)
            self.assertEqual(parse_video_option({"fps": 24, "quality": "draft"}, cwd=cwd), expected)
            with self.assertRaises(SnapshotError) as ctx:
                parse_video_option("missing.json", cwd=cwd)
            self.assertIn("missing.json", str(ctx.exception))


class OutputContainer(unittest.TestCase):
    """The OUT extension picks the container, and the container has its own rules."""

    def test_the_extension_is_the_container(self):
        self.assertEqual(video_container_for_path("tmp/demo.mp4"), "mp4")
        self.assertEqual(video_container_for_path("tmp/demo.GIF"), "gif")

    def test_any_other_extension_is_refused_by_name(self):
        for path in ("tmp/demo.png", "tmp/demo.webm", "tmp/demo"):
            with self.subTest(path=path):
                with self.assertRaises(SnapshotError) as ctx:
                    video_container_for_path(path)
                message = str(ctx.exception)
                self.assertIn(".mp4", message)
                self.assertIn(".gif", message)

    def test_loop_is_a_gif_setting_and_an_mp4_says_so(self):
        self.assertEqual(validate_video_output({"loop": True}, "tmp/demo.mp4"), "mp4")
        self.assertEqual(validate_video_output({"loop": False}, "tmp/demo.gif"), "gif")
        with self.assertRaises(SnapshotError) as ctx:
            validate_video_output({"loop": False}, "tmp/demo.mp4")
        self.assertIn("GIF", str(ctx.exception))


class JobRules(unittest.TestCase):
    """What a video job may declare, checked where a packet reaches it."""

    def _normalize(self, job: dict) -> dict:
        return normalize_common_job(
            job, mode="view", resolved_cwd=Path.cwd(), timestamp="20260908T000000Z"
        )

    def test_a_still_refuses_every_video_container_and_says_what_writes_one(self):
        # `--video` is one word away from the documented invocation, and the
        # still path would otherwise write base64 PNG bytes under a .mp4 name at
        # exit 0 -- a file no player opens and a success line that lies about it.
        for path in ("tmp/demo.gif", "tmp/demo.mp4", "tmp/demo.MP4"):
            with self.subTest(path=path):
                with self.assertRaises(SnapshotError) as ctx:
                    self._normalize({"input": "a.step", "outputs": [{"path": path}]})
                message = str(ctx.exception)
                self.assertIn(".png", message)
                self.assertIn("--video", message)

    def test_a_video_job_accepts_the_video_containers(self):
        video = normalize_video_request({}, where="--video")
        for path in ("tmp/demo.mp4", "tmp/demo.gif"):
            with self.subTest(path=path):
                normalized = self._normalize(
                    {"input": "a.step", "video": video, "outputs": [{"path": path}]}
                )
                self.assertTrue(str(normalized["outputs"][0]["path"]).endswith(Path(path).suffix))

    def test_a_video_renders_one_clip_to_one_file(self):
        video = normalize_video_request({}, where="--video")
        with self.assertRaises(SnapshotError) as ctx:
            self._normalize(
                {
                    "input": "a.step",
                    "video": video,
                    "outputs": [{"path": "tmp/a.mp4"}, {"path": "tmp/b.mp4"}],
                }
            )
        self.assertIn("one file", str(ctx.exception))

    def test_the_flag_reaches_the_job_as_the_normalized_request(self):
        options = SnapshotOptions(
            input="models/arm.step",
            output="tmp/demo.mp4",
            animation="demo",
            animation_specified=True,
            video='{"fps": 24}',
            video_specified=True,
        )
        job = load_job_from_options(options, stdin=io.StringIO(), cwd=Path.cwd())
        self.assertEqual(job["video"]["fps"], 24)
        self.assertEqual(job["video"]["quality"], DEFAULT_VIDEO_QUALITY)
        self.assertEqual(job["animation"], {"clip": "demo", "time": 0.0})


class DoorRules(unittest.TestCase):
    """`video` needs a clip and cannot also be a moment of one."""

    def _verb(self):
        from cadgen._internal.snapshot_door import step_snapshot_verb

        return step_snapshot_verb("step")

    def test_video_requires_animation(self):
        with self.assertRaises(ValueError) as ctx:
            self._verb()(Path("arm.step"), Path("tmp/demo.mp4"), video='{"fps": 30}')
        self.assertIn("requires animation", str(ctx.exception))

    def test_video_and_time_are_mutually_exclusive(self):
        with self.assertRaises(ValueError) as ctx:
            self._verb()(
                Path("arm.step"), Path("tmp/demo.mp4"), animation="demo", time=2.0, video="{}"
            )
        message = str(ctx.exception)
        self.assertIn("video and time", message)
        # The message has to say what to use instead, or the caller's next
        # attempt is the same command with the flags swapped.
        self.assertIn("start", message)


class PacketRules(unittest.TestCase):
    """A packet may carry `video` directly, so the door's two rules hold here too."""

    def _resolve(self, job: dict) -> str:
        from cadgen.snapshot_cli import enabled_kinds, resolve_render_job_packet

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "arm.step").write_text("ISO-10303-21;", encoding="utf-8")
            with self.assertRaises(SnapshotError) as ctx:
                resolve_render_job_packet(
                    {"input": "arm.step", "outputs": [{"path": "tmp/demo.mp4"}], **job},
                    cwd=root,
                    kinds=enabled_kinds(("step", "stp")),
                )
            return str(ctx.exception)

    def test_a_video_without_a_clip_is_refused_before_anything_is_built(self):
        message = self._resolve({"video": {"fps": 30}})
        self.assertIn("video requires animation", message)

    def test_a_video_cannot_also_name_a_moment(self):
        message = self._resolve(
            {"video": {"fps": 30}, "animation": {"clip": "demo", "time": 2.0}}
        )
        self.assertIn("span, not a moment", message)
        # It has to say what to use instead, or the next attempt is the same
        # request with the same number in the same place.
        self.assertIn("video start", message)

    def test_an_unusable_video_request_in_a_packet_is_refused_by_key(self):
        message = self._resolve({"video": {"framerate": 30}, "animation": {"clip": "demo"}})
        self.assertIn("framerate", message)

    def test_the_container_is_checked_before_the_package_is_built(self):
        # normalize_common_job holds the same rule, but it does not run until
        # after the STEP tree is compiled -- the slowest part of a snapshot. A
        # typo in a file extension is not worth minutes, and the output target
        # has already been cleared by the time the wait would start.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "arm.step").write_text("ISO-10303-21;", encoding="utf-8")
            from cadgen.snapshot_cli import enabled_kinds, resolve_render_job_packet

            with self.assertRaises(SnapshotError) as ctx:
                resolve_render_job_packet(
                    {
                        "input": "arm.step",
                        "animation": {"clip": "demo"},
                        "video": {"fps": 30},
                        "outputs": [{"path": "tmp/demo.webm"}],
                    },
                    cwd=root,
                    kinds=enabled_kinds(("step", "stp")),
                )
        message = str(ctx.exception)
        self.assertIn("demo.webm", message)
        self.assertIn(".mp4", message)


class FfmpegResolution(unittest.TestCase):
    """No encoder means no video, said BEFORE the frames rather than after."""

    def _without_ffmpeg(self):
        import os
        import unittest.mock

        from cadgen.snapshot_video import ffmpeg_binary

        with unittest.mock.patch.dict(os.environ, {"CADGEN_FFMPEG": ""}, clear=False), \
                unittest.mock.patch("shutil.which", return_value=None):
            with self.assertRaises(SnapshotError) as ctx:
                ffmpeg_binary()
        return str(ctx.exception)

    def test_a_missing_ffmpeg_names_it_and_how_to_install_it(self):
        message = self._without_ffmpeg()
        self.assertIn("ffmpeg", message)
        self.assertIn("brew install ffmpeg", message)
        self.assertIn("CADGEN_FFMPEG", message)

    def test_the_override_reaches_the_worker_that_actually_encodes(self):
        # `cadgen step snapshot` is served by the warm daemon, and a worker
        # inherits the environment of whatever shell started it. Without this
        # forwarding, CADGEN_FFMPEG was read in a process that does no encoding
        # and ignored in the one that does.
        import os
        import unittest.mock

        from cadgen.daemon.client import forwarded_env

        with unittest.mock.patch.dict(os.environ, {"CADGEN_FFMPEG": "/opt/ffmpeg"}, clear=False):
            self.assertEqual(forwarded_env().get("CADGEN_FFMPEG"), "/opt/ffmpeg")

    def test_the_callers_own_path_is_what_is_searched_for_ffmpeg(self):
        # The lookup has to happen in the CLIENT: the worker's PATH belongs to
        # whichever process first spawned the daemon, so an installed ffmpeg was
        # reported as missing and installing one afterwards never helped.
        import os
        import unittest.mock

        from cadgen.daemon import client

        client._ffmpeg_on_path = None
        try:
            with unittest.mock.patch.dict(os.environ, clear=False) as environ:
                environ.pop("CADGEN_FFMPEG", None)
                with unittest.mock.patch(
                    "shutil.which", return_value="/opt/homebrew/bin/ffmpeg"
                ) as which:
                    self.assertEqual(
                        client.forwarded_env().get("CADGEN_FFMPEG"), "/opt/homebrew/bin/ffmpeg"
                    )
                which.assert_called_once_with("ffmpeg")
        finally:
            client._ffmpeg_on_path = None

    def test_a_bad_override_names_the_path_it_was_given(self):
        import os
        import unittest.mock

        from cadgen.snapshot_video import ffmpeg_binary

        with unittest.mock.patch.dict(
            os.environ, {"CADGEN_FFMPEG": "/nope/ffmpeg"}, clear=False
        ), unittest.mock.patch("shutil.which", return_value=None):
            with self.assertRaises(SnapshotError) as ctx:
                ffmpeg_binary()
        self.assertIn("/nope/ffmpeg", str(ctx.exception))


class _NotATty(io.StringIO):
    pass


class _ATty(io.StringIO):
    def isatty(self) -> bool:
        return True


class Narration(unittest.TestCase):
    """A render measured in thousands of frames says where it is."""

    def _logger(self, stream, *, verbose: bool = False):
        from cadgen.cli_logging import CliLogger

        return CliLogger("snapshot", verbose=verbose, stream=stream)

    def test_a_non_tty_gets_lines_because_the_progress_bar_paints_nothing(self):
        # `cadgen step snapshot` runs in a daemon worker whose stderr is a frame
        # relay, and InlineProgressLine disables itself on a non-tty. Without
        # these lines a ten-minute video render is completely silent.
        from cadgen.snapshot_cli import snapshot_narrator

        stream = _NotATty()
        narrate = snapshot_narrator(self._logger(stream))
        self.assertIsNotNone(narrate)
        narrate("video: 1800 frames at 30 fps")
        self.assertIn("1800 frames", stream.getvalue())

    def test_a_terminal_gets_none_because_the_bar_is_already_painting(self):
        from cadgen.snapshot_cli import snapshot_narrator

        self.assertIsNone(snapshot_narrator(self._logger(_ATty())))
        # --verbose stands the bar down for the logger, so the lines are what
        # the caller asked for.
        self.assertIsNotNone(snapshot_narrator(self._logger(_ATty(), verbose=True)))


class VideoRender(unittest.TestCase):
    """The frame loop, against a page that answers but draws nothing."""

    def _render(self, stream):
        import asyncio
        import base64
        import unittest.mock

        from cadgen.snapshot_cli import snapshot_narrator
        from cadgen.snapshot_core import BatchSnapshotRenderer

        frame_png = "data:image/png;base64," + base64.b64encode(b"png").decode("ascii")

        class Page:
            def __init__(self):
                self.frames_asked = []

            async def set_viewport_size(self, size):
                return None

            async def evaluate(self, script, arg=None):
                if "__snapshotRenderSequence(" in script:
                    return {"ok": True, "frames": 3, "fps": 30, "seconds": 0.1, "start": 0.0}
                if "__snapshotRenderSequenceFrame" in script:
                    self.frames_asked.append(arg)
                    return {
                        "ok": True,
                        "index": arg,
                        "dataUrl": frame_png,
                        "width": 800,
                        "height": 600,
                        # The name the page RESOLVED, which is what a still reports.
                        "camera": "iso",
                    }
                return {"ok": True, "warnings": []}

        renderer = BatchSnapshotRenderer(Path("."))
        renderer.started = True
        renderer.page = Page()
        job = {
            "input": "arm.step",
            "animation": {"clip": "demo", "time": 0.0},
            "video": normalize_video_request({}, where="--video"),
            # An explicit-position camera: the request is an OBJECT, so echoing
            # it would put a Python repr in a machine-readable field.
            "outputs": [
                {"path": "tmp/demo.mp4", "camera": {"position": [10, 10, 10]},
                 "width": 800, "height": 600}
            ],
        }
        encoded = {}

        def fake_encode(frames_dir, **kwargs):
            encoded["frames"] = sorted(p.name for p in Path(frames_dir).iterdir())
            encoded.update(kwargs)

        with unittest.mock.patch("cadgen.snapshot_video.encode_video", fake_encode):
            result = asyncio.run(
                renderer.render_video(
                    job, narrate=snapshot_narrator(_logger_for(stream))
                )
            )
        return result, encoded, renderer.page.frames_asked

    def test_every_frame_is_written_once_and_the_encoder_gets_them_all(self):
        result, encoded, asked = self._render(_NotATty())
        self.assertEqual(asked, [0, 1, 2])
        self.assertEqual(
            encoded["frames"], ["frame_000000.png", "frame_000001.png", "frame_000002.png"]
        )
        self.assertEqual(encoded["container"], "mp4")
        self.assertEqual(encoded["fps"], 30)

    def test_the_result_reports_the_camera_the_page_resolved(self):
        result, _, _ = self._render(_NotATty())
        output = result["outputs"][0]
        self.assertEqual(output["camera"], "iso")
        self.assertEqual(output["video"], {"frames": 3, "fps": 30, "seconds": 0.1, "start": 0.0})
        self.assertEqual(output["mimeType"], "video/mp4")

    def test_the_frame_total_is_disclosed_before_the_first_frame(self):
        # The one number that says how long this will run. Without it a typo'd
        # span and a deliberate one look identical from outside.
        stream = _NotATty()
        self._render(stream)
        narration = stream.getvalue()
        self.assertIn("3 frames at 30 fps", narration)
        self.assertLess(narration.index("3 frames at 30 fps"), narration.index("encoding"))


def _logger_for(stream):
    from cadgen.cli_logging import CliLogger

    return CliLogger("snapshot", verbose=False, stream=stream)


class FfmpegCommand(unittest.TestCase):
    """The argv, per quality and container. Nothing here runs ffmpeg."""

    def _commands(self, container: str, quality: str, *, loop: bool = True):
        return ffmpeg_video_commands(
            "/opt/ffmpeg",
            frames_dir=Path("/frames"),
            output_path=Path("/out/demo.tmp"),
            fps=30,
            container=container,
            quality=quality,
            loop=loop,
        )

    def test_every_quality_is_a_real_encoder_setting_in_both_containers(self):
        for quality in VIDEO_QUALITIES:
            for container in ("mp4", "gif"):
                with self.subTest(quality=quality, container=container):
                    commands = self._commands(container, quality)
                    self.assertTrue(all(command[0] == "/opt/ffmpeg" for command in commands))
                    for command in commands:
                        self.assertIn(str(Path("/frames") / VIDEO_FRAME_PATTERN), command)

    def test_mp4_is_h264_yuv420p_at_the_quality_the_word_names(self):
        expected = {"draft": ("30", "veryfast"), "review": ("23", "medium"), "high": ("16", "slow")}
        for quality, (crf, preset) in expected.items():
            with self.subTest(quality=quality):
                (command,) = self._commands("mp4", quality)
                self.assertEqual(command[command.index("-crf") + 1], crf)
                self.assertEqual(command[command.index("-preset") + 1], preset)
                self.assertEqual(command[command.index("-c:v") + 1], "libx264")
                # Without this a perfectly valid H.264 file will not play in
                # Safari, QuickTime, or most hardware decoders.
                self.assertEqual(command[command.index("-pix_fmt") + 1], "yuv420p")

    def test_an_odd_frame_size_is_cropped_even_rather_than_failing_the_encode(self):
        # yuv420p rejects an odd width or height outright, and the frames are
        # whatever the size profile rendered.
        for container in ("mp4", "gif"):
            with self.subTest(container=container):
                for command in self._commands(container, "review"):
                    filters = " ".join(command)
                    self.assertIn("crop=trunc(iw/2)*2:trunc(ih/2)*2", filters)

    def test_gif_is_two_passes_over_a_palette_built_from_the_frames(self):
        expected = {
            "draft": ("max_colors=64", "dither=bayer"),
            "review": ("max_colors=128", "dither=sierra2_4a"),
            "high": ("max_colors=256:stats_mode=diff", "dither=sierra2_4a"),
        }
        for quality, (palettegen, dither) in expected.items():
            with self.subTest(quality=quality):
                generate, use = self._commands("gif", quality)
                palette = str(Path("/frames") / GIF_PALETTE_NAME)
                self.assertIn(palettegen, " ".join(generate))
                self.assertEqual(generate[-1], palette)
                self.assertIn(palette, use)
                self.assertIn(dither, " ".join(use))

    def test_loop_maps_to_the_gif_muxers_loop_count(self):
        _, looping = self._commands("gif", "review", loop=True)
        _, once = self._commands("gif", "review", loop=False)
        self.assertEqual(looping[looping.index("-loop") + 1], "0")
        self.assertEqual(once[once.index("-loop") + 1], "-1")

    def test_the_container_is_named_because_the_target_is_a_temp_file(self):
        # The encode writes `<out><temp suffix>` and the finished file is
        # renamed over the target, so ffmpeg cannot infer the format from the
        # suffix it is handed.
        for container in ("mp4", "gif"):
            with self.subTest(container=container):
                command = self._commands(container, "review")[-1]
                self.assertEqual(command[command.index("-f") + 1], container)


if __name__ == "__main__":
    unittest.main()
