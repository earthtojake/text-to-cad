"""The engine keeping this computer up to date (`cadgen/_internal/auto_update.py`): the receipt's
release behind the feed's, the release staged by uvx, then its `cadgen setup` run for the receipt's
apps with the receipt's PATH, and the notice saying where that stands; the update the person starts from the card
(`run_now`), and the successor a superseded engine starts while pages watch it (`successor`).

uvx is a fake on a PATH of the test's own, which logs its arguments and environment, says a release
or a failure for `--version`, and as `cadgen setup` writes the new release into the receipt. The state
folder, the home and the port are the test's; the feed is handed in. Nothing reaches the network,
the developer's state folder or their uvx."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen import updates  # noqa: E402
from cadgen._internal import auto_update  # noqa: E402
from cadgen._internal.launch import LAUNCHER  # noqa: E402
from cadgen.cli import setup  # noqa: E402

PORT = 3311
FEED = {"latest": "0.9.0"}
UNSATISFIABLE = ("  × No solution found when resolving tool dependencies:\n"
                 "  ╰─▶ Because cadgen==0.9.0 was not found in the package registry, we can conclude that "
                 "cadgen==0.9.0 cannot be used.\n")

# The fake uvx: logs its arguments, PATH and PYTHONPATH, one JSON object a line; `--version` says the
# release it was asked for (or FAKE_UVX_STAGE's words, exit 1); `setup` waits for FAKE_UVX_GO when
# it is set, then writes its release into the receipt, as a setup does.
FAKE = textwrap.dedent("""\
    import json, os, sys, time
    args = sys.argv[1:]
    with open(os.environ["FAKE_UVX_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"args": args, "path": os.environ.get("PATH", ""),
                              "pythonpath": os.environ.get("PYTHONPATH")}) + "\\n")
    release = args[args.index("--from") + 1].split("==")[1]
    if args[-1] == "--version":
        if os.environ.get("FAKE_UVX_STAGE"):
            sys.stdout.buffer.write(os.environ["FAKE_UVX_STAGE"].encode("utf-8"))
            sys.exit(1)
        sys.stdout.buffer.write(("Installed 42 packages in 1.20s\\ncadgen " + release + "\\n").encode("utf-8"))
    elif "server" in args:
        pass
    elif "setup" in args:
        go, deadline = os.environ.get("FAKE_UVX_GO"), time.monotonic() + 60
        while go and not os.path.exists(go) and time.monotonic() < deadline:
            time.sleep(0.02)
        path = os.path.join(os.environ["CADGEN_STATE_DIR"], "install-receipt.json")
        with open(path, encoding="utf-8") as kept:
            receipt = json.load(kept)
        receipt["release"] = release
        with open(path, "w", encoding="utf-8", newline="\\n") as kept:
            json.dump(receipt, kept)
        sys.stdout.buffer.write(b"Claude Code: update text-to-cad\\ntext-to-cad now updates itself: ...\\n")
""")


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = temporary_directory(prefix="auto-update-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.state, self.bin, self.empty, home = (self.root / name for name in ("state", "bin", "empty", "home"))
        for folder in (self.state, self.bin, self.empty, home):
            folder.mkdir()
        script = self.bin / "fake_uvx.py"
        script.write_text(FAKE, encoding="utf-8", newline="\n")
        if os.name == "nt":
            (self.bin / "uvx.bat").write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8", newline="")
        else:
            uvx = self.bin / "uvx"
            uvx.write_text(f"#!{sys.executable}\n" + FAKE, encoding="utf-8", newline="\n")
            uvx.chmod(0o755)
        self.log = self.root / "uvx.log"
        # The process's own PATH finds no uvx: the receipt's does, as it found the apps' commands.
        for patch in (mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.state), "CADGEN_PORT": str(PORT),
                                                   "CADGEN_INSTALL_CHANNEL": "claude-github", "CADGEN_AUTO_UPDATED": "",
                                                   "CI": "", "CADGEN_UPDATE_CHECK": "", "PATH": str(self.empty),
                                                   "HOME": str(home), "USERPROFILE": str(home),
                                                   "PYTHONPATH": str(self.root / "the-engine-s-cadgen"),
                                                   "FAKE_UVX_LOG": str(self.log), "FAKE_UVX_STAGE": "",
                                                   "FAKE_UVX_GO": ""}),
                      mock.patch.object(cadgen, "__version__", "0.8.1"),
                      mock.patch("cadgen._internal.channel._source_tree", return_value=False)):
            patch.start()
            self.addCleanup(patch.stop)
        self.asked: list[str] = []

    def get(self, url: str) -> dict:
        self.asked.append(url)
        return FEED

    def receipt(self, release: str = "0.8.1", port: int = PORT, **fields) -> None:
        kept = {"schema": setup.SCHEMA, "release": release, "port": port, "actions": [], "path": str(self.bin), **fields}
        (self.state / setup.RECEIPT).write_text(json.dumps(kept), encoding="utf-8", newline="\n")

    def read_today(self, feed: dict = FEED) -> None:
        (self.state / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": feed}), encoding="utf-8")

    def calls(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def auto(self) -> dict | None:
        found = updates.notice()
        return found and found.get("auto")


class SelfUpdate(Fixture):
    def test_without_a_receipt_nothing_runs_and_the_notice_is_as_ever(self) -> None:
        self.read_today()
        self.assertFalse(auto_update.wanted())
        self.assertIsNone(auto_update.run_once(get=self.get))
        self.assertEqual((self.asked, self.calls()), ([], []))
        self.assertNotIn("auto", updates.notice())
        self.assertEqual(updates.notice()["text"], "A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)")

    def test_a_newer_release_is_staged_then_its_setup_runs_for_the_receipt_s_apps_and_path(self) -> None:
        self.receipt(only=["claude", "codex"])
        self.read_today()
        self.assertEqual(self.auto(), {"state": "pending", "release": "0.9.0"})
        self.assertEqual(updates.notice()["text"], "A new version v0.9.0 of text-to-cad is available (currently on "
                                                   "v0.8.1); it installs itself within the hour.")
        self.assertIsNone(updates.line(updates.notice()), "pending asks nothing of an agent")
        go = self.root / "go"
        applying, seen, done = threading.Event(), {}, {}
        apply = auto_update._apply

        def watched(*args):  # the attempt says applying as the setup starts: the notice says installing
            seen["auto"], seen["line"] = self.auto(), updates.line(updates.notice())
            applying.set()
            return apply(*args)

        with mock.patch.dict(os.environ, {"FAKE_UVX_GO": str(go)}), mock.patch.object(auto_update, "_apply", watched):
            thread = threading.Thread(target=lambda: done.setdefault("result", auto_update.run_once(get=self.get)))
            thread.start()
            self.assertTrue(applying.wait(120), self.calls())
            go.write_text("", encoding="utf-8")
            thread.join(120)
        self.assertEqual(seen, {"auto": {"state": "updating", "release": "0.9.0", "stage": "installing"},
                                "line": None})
        self.assertEqual(done["result"], "done")
        stage, apply_ = self.calls()
        self.assertEqual(stage["args"], [*LAUNCHER[1:-1], "--refresh-package", "cadgen", "--from", "cadgen==0.9.0",
                                         "cadgen", "--version"])
        self.assertEqual(apply_["args"], [*LAUNCHER[1:], "cadgen==0.9.0", "cadgen", "setup", "--only", "claude,codex"])
        self.assertEqual(apply_["path"].split(os.pathsep)[:2], [str(self.bin), str(self.empty)])
        self.assertIsNone(apply_["pythonpath"], "the engine's own cadgen is never handed to the new release")
        self.assertEqual(auto_update.attempt()["stage"], "done")
        self.assertIsNone(updates.notice(), "installed: nothing to tell anyone, the next session runs it")
        self.assertRegex(auto_update.describe(), r"^installed v0\.9\.0 by itself .*; new sessions run it; ")
        # Caught up: nothing more to do, then or tomorrow.
        self.assertIsNone(auto_update.run_once(get=self.get, now=time.time() + auto_update.RETRY_SECONDS + 1))
        self.assertEqual(len(self.calls()), 2)

    def test_a_release_that_cannot_be_staged_fails_runs_no_setup_and_is_tried_again_the_next_day(self) -> None:
        self.receipt()
        with mock.patch.dict(os.environ, {"FAKE_UVX_STAGE": UNSATISFIABLE}):
            self.assertEqual(auto_update.run_once(get=self.get), "failed")
            self.assertIsNone(auto_update.run_once(get=self.get))
            self.assertEqual([call["args"][-1] for call in self.calls()], ["--version"])
            error = ("Because cadgen==0.9.0 was not found in the package registry, we can conclude that "
                     "cadgen==0.9.0 cannot be used.")
            self.assertEqual((auto_update.attempt()["stage"], auto_update.attempt()["error"]), ("failed", error))
            found = updates.notice()
            self.assertEqual(found["auto"], {"state": "failed", "release": "0.9.0", "error": error})
            self.assertEqual(found["text"], f"text-to-cad v0.9.0 could not install itself ({error}).")
            self.assertEqual(updates.line(found), f"text-to-cad v0.9.0 could not install itself ({error}). Update with "
                                                  f"this command: `{updates.command()}`, or install manually "
                                                  "(https://www.texttocad.dev/install).")
            self.assertIn(f"update with `{updates.command()}`", auto_update.describe())
            # An hour later the feed is read again, but the release waits out its day.
            self.assertIsNone(auto_update.run_once(get=self.get, now=time.time() + updates.CHECK_SECONDS + 1))
            self.assertEqual(auto_update.run_once(get=self.get, now=time.time() + auto_update.RETRY_SECONDS + 1), "failed")
        self.assertEqual([call["args"][-1] for call in self.calls()], ["--version", "--version"])

    def test_the_person_s_update_tries_a_failed_release_again_at_once_reading_a_stale_feed_afresh(self) -> None:
        self.receipt()
        with mock.patch.dict(os.environ, {"FAKE_UVX_STAGE": UNSATISFIABLE}):
            self.assertEqual(auto_update.run_once(get=self.get), "failed")
        self.assertIsNone(auto_update.run_once(get=self.get), "the hourly check waits out the day")
        self.assertEqual(len(self.asked), 1, "the feed read this minute is not read again")
        later = time.time() + 2 * auto_update.FRESH_SECONDS
        self.assertEqual(auto_update.run_once(get=self.get, now=later, force=True), "done")
        self.assertEqual(len(self.asked), 2, "a minute old: read afresh")
        self.assertEqual([call["args"][-1] for call in self.calls()], ["--version", "--version", "setup"])

    def test_run_now_starts_one_update_and_reports_a_second_as_under_way(self) -> None:
        self.receipt()
        self.read_today()
        go, staged = self.root / "go", threading.Event()
        stage = auto_update._stage

        def staging(*args):
            staged.set()
            return stage(*args)

        with mock.patch.dict(os.environ, {"FAKE_UVX_GO": str(go)}), mock.patch.object(auto_update, "_stage", staging), \
                mock.patch.object(updates, "_get", self.get):
            self.assertEqual(auto_update.run_now(PORT), {"started": True})
            self.assertTrue(staged.wait(60))
            self.assertEqual(auto_update.run_now(PORT), {"started": False, "reason": auto_update.UNDER_WAY})
            go.write_text("", encoding="utf-8")
            auto_update._now.join(120)
        self.assertEqual(auto_update.attempt()["stage"], "done")
        # Where the engine does not update the computer, the doctor's words say why.
        self.assertEqual(auto_update.run_now(PORT + 1), {"started": False, "reason": auto_update.describe(PORT + 1)})
        self.assertTrue(auto_update.run_now(PORT + 1)["reason"].startswith(f"off on port {PORT + 1}"))

    def test_nothing_runs_when_switched_off_or_in_ci(self) -> None:
        self.receipt()
        self.read_today()
        for values in ({"CADGEN_UPDATE_CHECK": "0"}, {"CI": "true"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values):
                self.assertEqual((auto_update.wanted(), auto_update.run_once(get=self.get), auto_update.start(PORT)),
                                 (False, None, None))
                self.assertIsNone(updates.notice())
        self.assertEqual((self.asked, self.calls()), ([], []))

    def test_only_the_engine_on_the_receipt_s_port_updates_whoever_started_it(self) -> None:
        self.receipt(port=PORT + 1)
        self.read_today()
        self.assertIsNone(auto_update.run_once(PORT, get=self.get))
        self.assertEqual((self.asked, self.calls()), ([], []))
        self.assertNotIn("auto", updates.notice())
        # A store's plugin started this engine: it still keeps the install command's copies current.
        self.receipt()
        with mock.patch.dict(os.environ, {"CADGEN_AUTO_UPDATED": "1"}):
            self.assertTrue(auto_update.wanted())

    def test_a_long_setup_keeps_saying_it_is_under_way(self) -> None:
        self.receipt()
        self.read_today()
        go, done = self.root / "go", {}
        with mock.patch.dict(os.environ, {"FAKE_UVX_GO": str(go)}), \
                mock.patch.object(auto_update, "HEARTBEAT_SECONDS", 0.02), mock.patch.object(auto_update, "STALE_SECONDS", 0.5):
            thread = threading.Thread(target=lambda: done.setdefault("result", auto_update.run_once(get=self.get)))
            thread.start()
            # The heartbeat renews ``at`` while the setup runs: awaited, never slept for.
            deadline, seen = time.monotonic() + 60, set()
            while len(seen) < 3 and time.monotonic() < deadline:
                kept = auto_update.attempt()
                if kept.get("stage") == "applying":
                    seen.add(kept["at"])
            self.assertEqual(len(seen), 3, auto_update.attempt())
            self.assertEqual(self.auto(), {"state": "updating", "release": "0.9.0", "stage": "installing"})
            self.assertTrue(auto_update.describe().startswith("installing v0.9.0 (installing, since "))
            go.write_text("", encoding="utf-8")
            thread.join(120)
        self.assertEqual(done["result"], "done")

    def test_an_attempt_left_applying_for_an_hour_while_the_receipt_is_behind_has_failed(self) -> None:
        self.receipt()
        self.read_today()
        then = time.time() - 2 * auto_update.STALE_SECONDS
        auto_update._keep({"release": "0.9.0", "started": then, "at": then, "stage": "applying"})
        self.assertEqual(self.auto(), {"state": "failed", "release": "0.9.0", "error": auto_update.STOPPED})
        self.assertIsNone(auto_update.run_once(get=self.get))  # attempted today: tomorrow, at the earliest
        self.assertEqual(self.calls(), [])
        # The setup it ran retired the engine and finished: the receipt says so, and the attempt is done.
        self.receipt("0.9.0")
        self.assertIsNone(self.auto(), "installed: the notice goes quiet")
        self.assertIsNone(auto_update.run_once(get=self.get))
        self.assertEqual(auto_update.attempt()["stage"], "done")


class TheNotice(Fixture):
    """What the notice says once a release has installed itself: nothing, wherever it shows, since the
    next session runs it and the engine steps aside for it; the doctor still says it is in."""

    def test_an_installed_release_says_nothing_and_the_doctor_says_new_sessions_run_it(self) -> None:
        self.receipt("0.9.0")
        self.read_today()
        self.assertEqual(auto_update.status(latest="0.9.0"), {"state": "updated", "release": "0.9.0"})
        self.assertIsNone(updates.notice())
        self.assertRegex(auto_update.describe(), r"^installed v0\.9\.0; new sessions run it; last checked ")

    def test_an_update_under_way_names_its_stage(self) -> None:
        self.receipt()
        self.read_today()
        now = time.time()
        for stage, said in (("staging", "downloading"), ("applying", "installing")):
            auto_update._keep({"release": "0.9.0", "started": now, "at": now, "stage": stage})
            self.assertEqual(self.auto(), {"state": "updating", "release": "0.9.0", "stage": said})


class Successor(Fixture):
    """The engine a superseded one starts in its place while pages watch it (the daemon's SUCCESSOR):
    the current release's `cadgen server` on the port, from its registered installation, else through
    uvx at the receipt's release, told to run as it is."""

    def setUp(self) -> None:
        super().setUp()
        self.started: list[tuple[list[str], dict]] = []
        patch = mock.patch.object(auto_update.subprocess, "Popen",
                                  lambda argv, **kwargs: self.started.append((argv, kwargs)))
        patch.start()
        self.addCleanup(patch.stop)

    def register(self, version: str) -> str:
        prefix = self.root / f"env-{version}"
        (prefix / "bin").mkdir(parents=True)
        python, console = prefix / "bin" / "python", prefix / "bin" / "cadgen"
        for made in (python, console):
            made.write_text("", encoding="utf-8")
        folder = self.state / "installations"
        folder.mkdir(exist_ok=True)
        record = {"version": version, "python": str(python), "cadgen": str(console), "prefix": str(prefix),
                  "registered": "2026-10-29T10:00:00+0000"}
        (folder / f"{version}.json").write_text(json.dumps(record), encoding="utf-8")
        return str(console)

    def test_the_registered_installation_of_the_receipt_s_release_serves_the_port(self) -> None:
        self.receipt("0.9.0")
        self.register("0.8.1")
        console = self.register("0.9.0")
        self.assertIsNone(auto_update.successor(PORT))
        [(argv, kwargs)] = self.started
        self.assertEqual(argv, [console, "server", "--port", str(PORT)])
        self.assertEqual(kwargs["env"]["PATH"].split(os.pathsep)[:2], [str(self.bin), str(self.empty)])
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertIn("server --port", (self.state / auto_update.LOG_FILE).read_text(encoding="utf-8"))

    def test_with_no_installation_registered_uvx_runs_the_release(self) -> None:
        self.receipt("0.9.0")
        self.assertIsNone(auto_update.successor(PORT))
        [(argv, _kwargs)] = self.started
        self.assertEqual(argv[1:], [*LAUNCHER[1:], "cadgen==0.9.0", "cadgen", "server", "--port", str(PORT)])

    def test_nothing_starts_without_a_newer_release_or_anything_to_run_it(self) -> None:
        for name in ("UV_INSTALL_DIR", "XDG_BIN_HOME"):  # where else uv's installer may put uvx
            patch = mock.patch.dict(os.environ, {name: ""})
            patch.start()
            self.addCleanup(patch.stop)
        self.receipt("0.8.1")
        self.assertEqual(auto_update.successor(PORT), "no release newer than v0.8.1 is installed")
        self.receipt("0.9.0", path=str(self.empty))
        self.assertEqual(auto_update.successor(PORT),
                         "no installation of 0.9.0 is registered: run the install command")
        self.assertEqual(self.started, [])


class TheTick(unittest.TestCase):
    def test_a_check_waits_out_the_grace_then_comes_once_an_hour(self) -> None:
        began, hour, grace = 1000.0, updates.CHECK_SECONDS, auto_update.GRACE_SECONDS
        self.assertEqual(hour, 3600)
        self.assertEqual(auto_update.due_in(began, None, began), grace)
        self.assertEqual(auto_update.due_in(began, None, began + grace), 0)
        self.assertEqual(auto_update.due_in(began, began + grace, began + grace + 10), hour - 10)
        self.assertEqual(auto_update.due_in(began, began + grace, began + grace + hour), 0)
        self.assertEqual(auto_update.due_in(began, began + grace, began), 0)  # a clock set back: due

    def test_the_thread_sleeps_a_minute_at_most_and_a_failed_check_never_ends_it(self) -> None:
        now, checks, slept = [5000.0], [], []

        class Stop(BaseException):
            pass

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds
            if len(checks) == 2:
                raise Stop

        def check(port: int) -> None:
            checks.append((port, now[0]))
            raise RuntimeError("the feed answered nonsense")

        with mock.patch.object(auto_update, "run_once", check), self.assertLogs("cadgen.auto_update", "ERROR"), \
                self.assertRaises(Stop):
            auto_update._tick(PORT, clock=lambda: now[0], sleep=sleep)
        self.assertEqual(checks, [(PORT, 5000.0 + auto_update.GRACE_SECONDS),
                                  (PORT, 5000.0 + auto_update.GRACE_SECONDS + updates.CHECK_SECONDS)])
        self.assertLessEqual(max(slept), auto_update.SLICE_SECONDS)


if __name__ == "__main__":
    unittest.main()
