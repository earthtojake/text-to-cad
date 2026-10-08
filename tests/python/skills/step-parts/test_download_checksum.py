"""write_download verifies the sha256 checksum before writing the file to disk.

A download whose bytes do not match the catalog's sha256 must fail loudly
*without* leaving the corrupt file behind: a stale bad file would make every
follow-up run die with "Refusing to overwrite existing file".
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests.python.support.paths import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "skills/step-parts/scripts"))
import download_step_part  # noqa: E402


def make_args(out_dir: Path, **overrides: Any) -> SimpleNamespace:
    args = SimpleNamespace(
        origin="https://api.step.parts",
        out_dir=str(out_dir),
        filename="p1.step",
        overwrite=False,
        timeout=30.0,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def make_part(**overrides: Any) -> dict[str, Any]:
    part: dict[str, Any] = {
        "id": "p1",
        "name": "Test part",
        "stepUrl": "/v1/parts/p1/step",
        "pageUrl": "https://step.parts/p1",
        "apiUrl": "https://api.step.parts/v1/parts/p1",
    }
    part.update(overrides)
    return part


class WriteDownloadChecksumTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="step-parts-checksum-")
        self.addCleanup(tmp.cleanup)
        self.out_dir = Path(tmp.name)

    def write_download(self, part: dict[str, Any], args: SimpleNamespace, data: bytes) -> dict[str, Any]:
        with mock.patch.object(download_step_part, "request", return_value=data):
            return download_step_part.write_download(part, args, True)

    def test_checksum_mismatch_raises_and_leaves_no_file(self) -> None:
        data = b"corrupt-bytes"
        part = make_part(sha256=hashlib.sha256(b"something-else").hexdigest())
        args = make_args(self.out_dir)
        target = self.out_dir / "p1.step"

        with self.assertRaisesRegex(SystemExit, "Checksum mismatch"):
            self.write_download(part, args, data)

        self.assertFalse(target.exists(), "a corrupt download must not be left on disk")

    def test_matching_checksum_writes_file(self) -> None:
        data = b"valid-step-bytes"
        part = make_part(sha256=hashlib.sha256(data).hexdigest())
        args = make_args(self.out_dir)

        result = self.write_download(part, args, data)

        target = self.out_dir / "p1.step"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), data)
        self.assertTrue(result["checksumVerified"])
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())

    def test_missing_checksum_writes_file_unverified(self) -> None:
        data = b"valid-step-bytes"
        part = make_part(sha256=None)
        args = make_args(self.out_dir)

        result = self.write_download(part, args, data)

        target = self.out_dir / "p1.step"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), data)
        self.assertFalse(result["checksumVerified"])


if __name__ == "__main__":
    unittest.main()
