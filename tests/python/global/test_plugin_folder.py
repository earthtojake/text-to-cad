"""The plugin folder the server writes and points every agent app at (cad_server/_internal/plugin.py),
written here from this checkout's plugin -- the repository root's manifests and skills/, which the
server's wheel carries (scripts/bundle/cadgen-runtime.sh's plugin stage) -- by the module read by its
path: it imports nothing of the packages, so this runs with nothing installed.

What the folder holds is checked in temporary folders. Each host's own validator reads it where that
host's command is installed (`claude plugin validate`, `gemini extensions validate`), and Claude Code
and Gemini CLI, run in a home of their own (`env -i`: HOME, CLAUDE_CONFIG_DIR and GEMINI_CLI_HOME in
a temporary folder), are pointed at it as `cad setup` points them (cad_server/_internal/providers.py),
read a regenerated folder in place, and let it go again. Without the command, that host's part is
skipped. Codex and Cursor keep copies of the folder: their commands are the providers suite's, in dry
run (tests/python/packages/texttocad_server/test_providers.py).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

INTERNAL = REPO_ROOT / "packages" / "texttocad-server" / "src" / "cad_server" / "_internal"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


plugin = _load("plugin_folder_plugin", INTERNAL / "plugin.py")
providers = _load("plugin_folder_providers", INTERNAL / "providers.py")
launch = _load("plugin_folder_launch", INTERNAL / "launch.py")
plugin_branch = _load("plugin_folder_plugin_branch", REPO_ROOT / "scripts" / "release" / "plugin_branch.py")
wheel_contents = _load("plugin_folder_wheel_contents", REPO_ROOT / "scripts" / "release" / "wheel_contents.py")

VERSION = "9.9.9"
# The file each host's CAD server line is in, and the channel the installer always told it.
CHANNELS = {"claude.mcp.json": "claude-github", "codex.mcp.json": "codex-github", "cursor.mcp.json": "cursor-github",
            "gemini-extension.json": "gemini-github", "mcp.json": "agent-plugins"}


def _files(folder: Path) -> dict[str, Path]:
    return {path.relative_to(folder).as_posix(): path for path in folder.rglob("*")
            if path.is_file() or path.is_symlink()}


class ThePluginFolder(unittest.TestCase):
    def setUp(self) -> None:
        scratch = temporary_directory(prefix="plugin-folder-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.folder = self.root / "state" / "plugin"

    def test_its_files_are_the_install_branch_s_and_the_bundle_s(self) -> None:
        self.assertEqual(set(plugin.FILES), set(plugin_branch.COPIES["latest"].files),
                         "the folder is the `latest` branch's plugin, less its README")
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("no bash to ask the bundle")
        listed = subprocess.run([bash, str(REPO_ROOT / "scripts/bundle/cadgen-runtime.sh"), "--print-plugin-files"],
                                capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(listed, list(plugin.FILES), "the bundle copies the files the folder is written from")
        self.assertEqual((plugin.MARKETPLACE, plugin.PLUGIN_ID), (providers.MARKETPLACE, providers.PLUGIN_ID))

    def test_it_is_this_release_s_plugin_with_each_host_s_server_line_and_the_skills_as_they_are(self) -> None:
        done = plugin.write(self.folder, origin=REPO_ROOT, version=VERSION)
        self.assertTrue(done["created"])
        files = _files(self.folder)
        skills = wheel_contents.skill_files(REPO_ROOT)
        self.assertEqual(set(files), {*plugin.FILES, *skills})
        self.assertNotIn(".mcp.json", files, "Claude Code would read a root .mcp.json in place of claude.mcp.json")
        self.assertFalse([name for name, path in files.items() if path.is_symlink()], "real files: Codex drops a symlink")
        for name in skills:
            with self.subTest(skill=name):
                self.assertEqual(files[name].read_bytes(), (REPO_ROOT / name).read_bytes())
                if os.name != "nt":
                    self.assertEqual(files[name].stat().st_mode & stat.S_IXUSR, (REPO_ROOT / name).stat().st_mode & stat.S_IXUSR)
        for name in plugin.MANIFESTS:
            self.assertEqual(json.loads(files[name].read_text(encoding="utf-8"))["version"], VERSION, name)
        catalog = json.loads(files[plugin.CATALOG].read_text(encoding="utf-8"))
        self.assertEqual((catalog["name"], catalog["version"]), (plugin.MARKETPLACE, VERSION))
        self.assertEqual([(entry["name"], entry["source"], entry["version"]) for entry in catalog["plugins"]],
                         [(plugin.NAME, "./", VERSION)])
        line = [*launch.LAUNCHER[1:], f"{launch.SHIM}=={VERSION}", launch.SHIM_COMMAND]
        for name, channel in CHANNELS.items():
            with self.subTest(config=name):
                root = json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))["mcpServers"]
                servers = json.loads(files[name].read_text(encoding="utf-8"))["mcpServers"]
                self.assertEqual(list(servers), ["cad"])
                self.assertEqual((servers["cad"]["command"], servers["cad"]["args"], servers["cad"]["env"]),
                                 (launch.LAUNCHER[0], line, {"CAD_INSTALL_CHANNEL": channel}))
                # The rest of each host's entry is the repository's (Codex's startup timeout, the standard's type).
                self.assertEqual({key: value for key, value in servers["cad"].items() if key not in ("args", "env")},
                                 {key: value for key, value in root["cad"].items() if key not in ("args", "env")})
        for name in plugin.FILES:
            if name not in plugin.MANIFESTS and name not in CHANNELS and name != plugin.CATALOG:
                self.assertEqual(files[name].read_bytes(), (REPO_ROOT / name).read_bytes(), name)

    def test_the_skills_hold_nothing_a_wheel_would_leave_out(self) -> None:
        # The server's wheel takes skills/ by a glob, which takes no hidden file or folder; bytecode never ships.
        left = [name for name in wheel_contents.skill_files(REPO_ROOT)
                if any(part.startswith(".") for part in name.split("/")) or name.endswith(".pyc")]
        self.assertEqual(left, [])

    def test_it_is_written_again_in_place(self) -> None:
        plugin.write(self.folder, origin=REPO_ROOT, version=VERSION)
        stale = self.folder / "skills" / "retired" / "SKILL.md"
        stale.parent.mkdir()
        stale.write_text("---\nname: retired\n---\n", encoding="utf-8")
        skill = self.folder / "skills" / "cad" / "SKILL.md"
        if os.name != "nt":
            skill.unlink()
            skill.symlink_to(REPO_ROOT / "skills" / "cad" / "SKILL.md")
        folder, kept = self.folder.stat().st_ino, (self.folder / "LICENSE").stat().st_ino
        done = plugin.write(self.folder, origin=REPO_ROOT, version="9.9.10")
        self.assertEqual(self.folder.stat().st_ino, folder, "the same folder, never one put in its place")
        self.assertEqual((self.folder / "LICENSE").stat().st_ino, kept, "a file that did not change is not written")
        self.assertIn("skills/retired/SKILL.md", done["removed"])
        self.assertFalse(stale.parent.exists())
        self.assertFalse(skill.is_symlink())
        self.assertEqual(skill.read_bytes(), (REPO_ROOT / "skills" / "cad" / "SKILL.md").read_bytes())
        self.assertIn(plugin.MANIFEST, done["changed"])
        self.assertEqual(json.loads((self.folder / plugin.MANIFEST).read_text(encoding="utf-8"))["version"], "9.9.10")
        self.assertEqual(plugin.pending(self.folder, origin=REPO_ROOT, version="9.9.10")["changed"], [])
        self.assertEqual([path.name for path in self.folder.rglob("*.tmp")], [])


def _command(name: str) -> str | None:
    found = shutil.which(name)
    return os.path.abspath(found) if found else None


class EachHostTakesIt(unittest.TestCase):
    """The hosts' own commands, in a home of their own; a host whose command is not here is skipped."""

    def setUp(self) -> None:
        scratch = temporary_directory(prefix="plugin-hosts-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        (self.home / ".gemini").mkdir()
        self.folder = self.root / "state" / "plugin"
        plugin.write(self.folder, origin=REPO_ROOT, version=VERSION)
        commands = [found for found in map(_command, ("claude", "gemini", "node")) if found]
        path = os.pathsep.join([*dict.fromkeys(str(Path(found).parent) for found in commands), "/usr/bin", "/bin"])
        # `env -i`: nothing of the developer's environment, config or apps reaches the hosts.
        self.environ = {"PATH": path, "HOME": str(self.home), "USERPROFILE": str(self.home),
                        "CLAUDE_CONFIG_DIR": str(self.home / ".claude"), "GEMINI_CLI_HOME": str(self.home),
                        "TMPDIR": str(self.root), "TERM": "dumb", "NO_COLOR": "1", "DISABLE_AUTOUPDATER": "1",
                        **{key: os.environ[key] for key in ("SYSTEMROOT", "USER", "LOGNAME") if key in os.environ}}
        self.machine = providers.Machine(self.home, self.environ, bundled={})

    def run_host(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(list(argv), env=self.environ, cwd=self.root, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=300)

    def test_each_host_s_validator_takes_it(self) -> None:
        validators = {"claude": ["plugin", "validate"], "gemini": ["extensions", "validate"]}
        if not any(map(_command, validators)):
            self.skipTest("neither claude nor gemini is installed")
        for host, argv in validators.items():
            command = _command(host)
            if command is None:
                continue
            with self.subTest(host=host):
                done = self.run_host(command, *argv, str(self.folder))
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def point(self, host: str) -> None:
        """``cad setup``'s plan for ``host`` alone, applied."""
        apps = providers.detect(self.machine, [host], folder=self.folder)
        steps = providers.plan(apps, release=VERSION, folder=self.folder, machine=self.machine, only=[host])
        self.assertEqual([step.action for step in steps], ["install"])
        for step in steps:
            ok, records = providers.apply(step, self.machine)
            self.assertTrue(ok, records)

    def ours(self, host: str):
        return providers.detect(self.machine, [host], folder=self.folder)[host].ours()

    def take_out(self, host: str, receipt: dict) -> None:
        undo = providers.uninstall_plan(providers.detect(self.machine, [host], folder=self.folder), receipt,
                                        machine=self.machine, folder=self.folder)
        for step in undo:
            ok, records = providers.apply(step, self.machine)
            self.assertTrue(ok, records)
        self.assertIsNone(self.ours(host))

    def test_claude_code_reads_it_in_place(self) -> None:
        claude = _command("claude")
        if claude is None:
            self.skipTest("claude is not installed")
        self.point("claude")
        listed = json.loads(self.run_host(claude, "plugin", "list", "--json").stdout)
        self.assertEqual([(entry["id"], Path(entry["readFromFolder"]).resolve()) for entry in listed],
                         [(plugin.PLUGIN_ID, self.folder.resolve())])
        # A new release's folder is what the next session reads; its cached copy follows by `plugin update`.
        plugin.write(self.folder, origin=REPO_ROOT, version="9.9.10")
        ours = self.ours("claude")
        self.assertEqual((ours.version, ours.recorded, ours.via), ("9.9.10", VERSION, "in place"))
        refresh = providers.refresh_plan(providers.detect(self.machine, ["claude"], folder=self.folder),
                                         release="9.9.10", folder=self.folder, machine=self.machine)
        self.assertEqual([argv[1:] for step in refresh for argv in step.commands],
                         [["plugin", "update", plugin.PLUGIN_ID]])
        for step in refresh:
            self.assertTrue(providers.apply(step, self.machine)[0])
        self.assertEqual(self.ours("claude").recorded, "9.9.10")
        self.take_out("claude", {"actions": [{"app": "claude", "action": "install", "kind": "command", "ok": True,
                                              "command": [claude, "plugin", "marketplace", "add", str(self.folder)]}]})
        self.assertNotIn(plugin.MARKETPLACE, providers.detect(self.machine, ["claude"], folder=self.folder)["claude"].marketplaces)

    def test_gemini_cli_links_it_and_reads_it_in_place(self) -> None:
        gemini = _command("gemini")
        if gemini is None:
            self.skipTest("gemini is not installed")
        self.point("gemini")
        self.assertEqual(self.ours("gemini").via, "linked")
        plugin.write(self.folder, origin=REPO_ROOT, version="9.9.10")
        self.assertEqual(self.ours("gemini").version, "9.9.10")
        self.assertEqual(providers.refresh_plan(providers.detect(self.machine, ["gemini"], folder=self.folder),
                                                release="9.9.10", folder=self.folder, machine=self.machine), [])
        self.take_out("gemini", {"actions": [{"app": "gemini", "action": "install", "kind": "command", "ok": True,
                                              "command": [gemini, "extensions", "link", str(self.folder)]}]})


if __name__ == "__main__":
    unittest.main()
