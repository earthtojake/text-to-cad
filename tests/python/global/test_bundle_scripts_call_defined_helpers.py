"""Every helper a bundle script calls must actually exist.

`bundle-sdf.sh` called `check_vendored_python_package`, which was never defined anywhere.
Bash only resolves a function name when the line runs, so nothing caught it: the call sits
behind a `MODE = check` branch that the development symlink layout skips entirely, and the one
layout that reaches it -- the production tree on main -- turned the resulting exit
127 into `|| stale=1`. The check reported the vendored copy as stale forever, for a reason that
had nothing to do with the copy, and the skills' vendored cadgen went unverified instead.

A typo in a shell function name is invisible until the branch runs, so check it statically.
"""

from __future__ import annotations

import re
import unittest

from tests.python.support.paths import repo_path


BUNDLE_DIR = repo_path("scripts", "bundle")

# The helper families the bundle scripts share. A call to something matching these prefixes is
# expected to resolve to a definition, in the script itself or in a lib/ file it sources.
HELPER_CALL_RE = re.compile(
    r"^\s*((?:check|vendor|build|ensure|require|sync)_[a-z0-9_]+)\b",
    re.MULTILINE,
)
DEFINITION_RE = re.compile(r"^\s*([a-z0-9_]+)\s*\(\)\s*\{", re.MULTILINE)


def _shell_scripts() -> list:
    return sorted(BUNDLE_DIR.rglob("*.sh"))


def _defined_names() -> set[str]:
    """Every function defined anywhere under scripts/bundle/.

    Deliberately repo-wide rather than per-file: the scripts source their libraries through
    `$SCRIPT_DIR` paths that are awkward to resolve statically, and a name defined nowhere is
    the failure worth catching. A name defined in the wrong library still runs.
    """
    defined: set[str] = set()
    for script in _shell_scripts():
        defined.update(DEFINITION_RE.findall(script.read_text(encoding="utf-8")))
    return defined


class BundleHelperCallsResolveTest(unittest.TestCase):
    def test_scripts_exist_to_check(self) -> None:
        scripts = _shell_scripts()
        self.assertTrue(scripts, "expected shell scripts under scripts/bundle/")
        self.assertTrue(
            any(script.name == "cadgen-runtime.sh" for script in scripts),
            "expected scripts/bundle/cadgen-runtime.sh, the packaged-runtime bundler",
        )

    def test_every_helper_call_resolves_to_a_definition(self) -> None:
        defined = _defined_names()
        missing: list[str] = []
        for script in _shell_scripts():
            text = script.read_text(encoding="utf-8")
            for name in HELPER_CALL_RE.findall(text):
                if name not in defined:
                    relative = script.relative_to(repo_path())
                    missing.append(f"{relative}: {name}")
        self.assertEqual(
            [],
            sorted(set(missing)),
            "bundle scripts call helper functions that are defined nowhere under "
            "scripts/bundle/; bash only fails on these when the branch runs",
        )

    def test_the_known_typo_stays_gone(self) -> None:
        # The specific name that shipped broken, pinned so it cannot come back by copy-paste.
        # Compared as a list of filenames rather than with assertNotIn on the text, so a
        # failure names the scripts instead of dumping every one of them.
        offenders = [
            script.name
            for script in _shell_scripts()
            if "check_vendored_python_package" in script.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            [],
            offenders,
            "these scripts call the undefined helper again; use check_python_runtime",
        )


if __name__ == "__main__":
    unittest.main()
