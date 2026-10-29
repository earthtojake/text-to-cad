import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen.settings import read_section, write_section


class SettingsTest(unittest.TestCase):
    def test_each_feature_writes_only_its_own_section(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "state" / "settings.json"
        self.assertEqual(read_section("analytics", path=path), {})  # nothing kept yet
        write_section("analytics", {"choice": "off"}, path=path)
        write_section("viewer", {"layout": "list"}, path=path)  # another app, another setting
        self.assertEqual(read_section("analytics", path=path), {"choice": "off"})
        write_section("viewer", None, path=path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"analytics": {"choice": "off"}})
        path.write_text("{not json", encoding="utf-8")  # a broken file reads as no settings, and the next write mends it
        self.assertEqual(read_section("analytics", path=path), {})
        write_section("analytics", {"choice": "on"}, path=path)
        self.assertEqual(read_section("analytics", path=path), {"choice": "on"})


class StateFolderTest(unittest.TestCase):
    """The state folder's small files hold what is read of them, and every change of one holds the
    folder's one lock (``file_lock.state``): no lock file of its own, no stamp file."""

    def test_the_settings_channels_feed_and_spool_share_one_lock_and_keep_what_is_read(self) -> None:
        import os
        import time
        from unittest import mock

        from cadgen import analytics, language, updates
        from cadgen._internal import channel, telemetry_send

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        state = tmp / "state"
        state.mkdir()
        (state / "versions.json").write_text(json.dumps({"checked": 0, "feed": {"latest": "1.0.0"}, "dismissed": "1.0.0"}),
                                            encoding="utf-8")  # a field nothing reads, kept by an earlier write
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(state), "CADGEN_INSTALL_CHANNEL": "claude-github",
                                          "CADGEN_AUTO_UPDATED": "", "CADGEN_UPDATE_CHECK": "", "CI": "",
                                          "DO_NOT_TRACK": "", "CADGEN_TELEMETRY": ""}):
            language.change({"locale": "ja"})
            analytics.choose(True, by="cli")
            self.assertEqual(channel.remember(), "claude-github")
            self.assertEqual(updates.feed(get=lambda _url: {"latest": "9.9.9"}), {"latest": "9.9.9"})
            self.assertTrue(analytics.spool({"builds": [{"kind": "xbf", "via": "script", "outcome": "ok", "seconds": 1.0}]}))
            later = time.time() + analytics.FLUSH_SECONDS + 1
            started: list[Path] = []
            self.assertTrue(telemetry_send.start_if_due(now=later, spawn=started.append))
            self.assertFalse(telemetry_send.start_if_due(now=later + 1, spawn=started.append), "one sender a window")
        self.assertEqual(sorted(path.name for path in state.iterdir()),
                         ["install-channels.json", "settings.json", "settings.lock", "telemetry-spool.jsonl", "versions.json"])
        self.assertEqual(os.stat(state / "settings.lock").st_mtime, later, "the lock's time is the last sender's start")
        self.assertEqual(set(json.loads((state / "versions.json").read_text(encoding="utf-8"))), {"checked", "feed"})
        self.assertEqual(json.loads((state / "settings.json").read_text(encoding="utf-8"))["language"], {"locale": "ja"})
        self.assertEqual(channel.recorded(path=state / "install-channels.json"), "claude-github")

    def test_the_generic_channel_is_refined_by_the_hosts_handshake(self) -> None:
        # The Agent Plugins standard's mcp.json names `agent-plugins`, which Codex reads over its own
        # config: a server told it takes Codex's channel as initialize names the client, for itself and
        # for its installation's record; a process told the generic one reports that record.
        import os
        from unittest import mock

        from cadgen._internal import channel

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        state = tmp / "state"
        state.mkdir()
        record = state / "install-channels.json"
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(state), "CADGEN_INSTALL_CHANNEL": "agent-plugins"}):
            self.assertEqual(channel.channel(), "agent-plugins", "nothing written down yet")
            self.assertIsNone(channel.refine(None), "a host without a config of its own")
            self.assertEqual(os.environ["CADGEN_INSTALL_CHANNEL"], "agent-plugins")
            self.assertEqual(channel.refine("codex-github"), "codex-github")
            self.assertEqual(os.environ["CADGEN_INSTALL_CHANNEL"], "codex-github")
            self.assertEqual(channel.channel(), "codex-github")
        self.assertEqual(channel.recorded(path=record), "codex-github")
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(state), "CADGEN_INSTALL_CHANNEL": "agent-plugins"}):
            self.assertEqual(channel.channel(), "codex-github", "another process told the generic one: the record")
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(state), "CADGEN_INSTALL_CHANNEL": "claude-github"}):
            self.assertIsNone(channel.refine("codex-github"), "a channel a plugin named is never refined")
            self.assertEqual(channel.channel(), "claude-github")


if __name__ == "__main__":
    unittest.main()
