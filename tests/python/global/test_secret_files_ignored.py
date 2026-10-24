"""No environment file, key or certificate is committed by accident: the repository's ignore rules
keep them out of `git add`, in the root and in the deployed API's folder (its Vercel link pulls the
PostHog keys into one), while an example file that only names the variables stays addable. And none
is tracked now."""

from __future__ import annotations

import re
import subprocess
import unittest

from tests.python.support.paths import REPO_ROOT

SECRET = re.compile(r"(?:^|/)\.env(?:\..+)?$|\.pem$|\.key$")


def ignored(*paths: str) -> set[str]:
    found = subprocess.run(["git", "check-ignore", "--no-index", "--", *paths], cwd=REPO_ROOT,
                           capture_output=True, text=True, check=False)
    return set(found.stdout.split())


class SecretFilesIgnoredTest(unittest.TestCase):
    def test_environment_files_keys_and_certificates_are_ignored_everywhere(self) -> None:
        secrets = [".env", ".env.local", "apps/api/.env", "apps/api/.env.production.local",
                   "apps/web/.env.development", "packages/cadgen/signing.key", "deploy/server.pem"]
        self.assertEqual(ignored(*secrets), set(secrets))

    def test_an_example_that_names_the_variables_stays_addable(self) -> None:
        self.assertEqual(ignored(".env.example", "apps/api/.env.example", "apps/web/.env.example"), set())

    def test_no_secret_file_is_tracked(self) -> None:
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        found = [path for path in tracked.stdout.splitlines() if SECRET.search(path) and not path.endswith(".env.example")]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
