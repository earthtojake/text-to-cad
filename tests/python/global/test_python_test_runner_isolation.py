from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.daemon_cleanup import retire_owned_daemon

add_repo_path("packages/cadgen/src")

spec = importlib.util.spec_from_file_location("isolated_unittest_runner", REPO_ROOT / "scripts/test/unittest_files.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PythonTestRunnerIsolation(unittest.TestCase):
    def test_modules_own_distinct_stores_auth_state_and_endpoints_then_retire_them(self):
        builds, cleanups = [], []

        def run(argv, *, env, **kwargs):
            if argv[1].endswith("daemon_cleanup.py"):
                self.assertEqual(argv[2], env["CADGEN_DAEMON_SOCKET"])
                self.assertTrue(Path(env["CADGEN_DAEMON_STATE_DIR"]).is_dir())
                self.assertTrue(Path(env["CADGEN_CACHE_DIR"]).is_dir())
                cleanups.append(dict(env))
            else:
                builds.append(dict(env))
                Path(env["CADGEN_DAEMON_STATE_DIR"], "test.key").write_text("test key", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "ok", "")

        ambient = {"CADGEN_DAEMON_STATE_DIR": "developer-state", "CADGEN_DAEMON_SOCKET": "developer-socket"}
        with mock.patch.dict(os.environ, ambient), mock.patch.object(runner.subprocess, "run", side_effect=run):
            for name in ("first.py", "second.py"):
                runner._run_one_file(name, str(REPO_ROOT), False)
            self.assertEqual(os.environ["CADGEN_DAEMON_SOCKET"], "developer-socket")
            self.assertEqual(os.environ["CADGEN_DAEMON_STATE_DIR"], "developer-state")
        for key in ("CADGEN_CACHE_DIR", "CADGEN_DAEMON_STATE_DIR", "CADGEN_DAEMON_SOCKET"):
            self.assertNotEqual(builds[0][key], builds[1][key])
            self.assertEqual([env[key] for env in builds], [env[key] for env in cleanups])
        for env in builds:
            self.assertNotEqual(env["CADGEN_DAEMON_SOCKET"], "developer-socket")
            self.assertFalse(Path(env["CADGEN_CACHE_DIR"]).exists())
            self.assertFalse(Path(env["CADGEN_DAEMON_STATE_DIR"]).exists())

    def test_failed_child_still_retires_only_its_own_endpoint(self):
        calls = []

        def run(argv, *, env, **kwargs):
            calls.append((argv, dict(env)))
            if argv[1].endswith("daemon_cleanup.py"):
                return subprocess.CompletedProcess(argv, 0, "", "")
            Path(env["CADGEN_DAEMON_STATE_DIR"], "test.key").write_text("test key", encoding="utf-8")
            raise OSError("test child could not run")

        with mock.patch.object(runner.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(OSError, "test child could not run"):
                runner._run_one_file("failed.py", str(REPO_ROOT), False)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0][2], calls[0][1]["CADGEN_DAEMON_SOCKET"])
        self.assertFalse(Path(calls[0][1]["CADGEN_DAEMON_STATE_DIR"]).exists())

    def test_cleanup_uses_authenticated_retirement_without_spawning_or_retrying(self):
        from cadgen.daemon import client

        channel = mock.Mock()
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": "owned"}), \
                mock.patch.object(client, "_connect", return_value=channel) as connect, \
                mock.patch.object(client, "_send_json", return_value=True) as send, \
                mock.patch.object(client, "_recv_json", return_value={"restart": True}), \
                mock.patch.object(client, "_connect_or_spawn", side_effect=AssertionError("must never spawn")):
            retire_owned_daemon("owned")
            connect.assert_called_once_with("owned")
            send.assert_called_once_with(channel, {"token": "test-owned-daemon-retirement"})
            channel.close.assert_called_once()
            with self.assertRaisesRegex(ValueError, "explicit test-owned address"):
                retire_owned_daemon("developer")
            self.assertEqual(connect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
