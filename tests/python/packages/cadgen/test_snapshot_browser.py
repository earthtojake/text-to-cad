"""The snapshot browser installs itself: snapshot_core.launch_with_browser.

Playwright is a dependency of every cadgen install, but its browser is a download of its own.
The first snapshot fetches it rather than failing with "run playwright install"; a Linux host
missing the browser's libraries gets them (or the exact command). Stubbed here: the real
download is ~100 MB, and the installed-wheel test is where a real browser runs.
"""

from __future__ import annotations

import asyncio
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import snapshot_core  # noqa: E402

MISSING = "BrowserType.launch: Executable doesn't exist at /cache/chromium_headless_shell-1243/chrome-headless-shell"
LIBRARIES = "BrowserType.launch: Host system is missing dependencies to run browsers."


def launcher(*failures: str):
    """A launch that raises each failure in turn, then returns a browser."""
    remaining = list(failures)

    async def launch():
        if remaining:
            raise RuntimeError(remaining.pop(0))
        return "browser"

    return launch


class SnapshotBrowserTests(unittest.TestCase):
    def run_launch(self, *failures: str) -> tuple[object, list[str]]:
        fixed: list[str] = []
        browser = asyncio.run(snapshot_core.launch_with_browser(launcher(*failures), fixed.append))
        return browser, fixed

    def test_a_missing_browser_is_installed_then_launched(self) -> None:
        self.assertEqual(self.run_launch(MISSING), ("browser", ["browser"]))

    def test_a_host_missing_libraries_gets_them_after_the_browser(self) -> None:
        self.assertEqual(self.run_launch(MISSING, LIBRARIES), ("browser", ["browser", "libraries"]))

    def test_any_other_failure_is_the_jobs_own_and_is_raised(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "target closed"):
            self.run_launch("target closed")

    def test_each_problem_is_fixed_once(self) -> None:
        # Still missing after its install: the install's own error is the one to read, not a loop.
        with self.assertRaisesRegex(RuntimeError, "Executable doesn't exist"):
            self.run_launch(MISSING, MISSING)


if __name__ == "__main__":
    unittest.main()
