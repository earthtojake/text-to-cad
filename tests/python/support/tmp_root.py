from __future__ import annotations

import tempfile
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

TMP_ROOT = REPO_ROOT / "tmp"
CAD_TEST_TMP_ROOT = TMP_ROOT / "cad-skill-tests"


def temporary_directory(*, prefix: str) -> tempfile.TemporaryDirectory[str]:
    """A test temp directory whose cleanup waits out the Windows sharing violation.

    Every directory a test writes into is exposed to the runner's real-time
    scanner, and some are exposed to a subprocess whose handles outlive the kill
    that ended it. Both hold ``WinError 32`` for a moment, and neither is the
    test's own bug. ``RetryingTemporaryDirectory`` is plain ``cleanup()`` off
    Windows and still fails loudly on a genuinely leaked handle, so this is the
    ladder rather than an exemption -- see the class below."""
    CAD_TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return RetryingTemporaryDirectory(prefix=prefix, dir=CAD_TEST_TMP_ROOT)


def named_tmp_root(name: str) -> Path:
    tmp_root = TMP_ROOT / name
    tmp_root.mkdir(parents=True, exist_ok=True)
    return tmp_root


# ERROR_SHARING_VIOLATION -- the same error cadgen's atomic rename retries
# (``cadgen._internal.atomic_replace``), for the same reason: the handle is
# not ours. Kept as a literal here because the support package must not
# import cadgen to clean up a directory.
WINDOWS_SHARING_VIOLATION = 32
# Widened after the 750 ms ladder lost once more on the runner (2026-09-02):
# the scanner's hold on a just-read file can outlast a second. ~6 s total.
CLEANUP_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2)


class RetryingTemporaryDirectory(tempfile.TemporaryDirectory[str]):
    """A ``TemporaryDirectory`` whose cleanup retries the one Windows error worth retrying.

    On the Windows CI runner a file this process has written and closed can
    still be open in ANOTHER process for a moment -- the real-time scanner
    inspects every fresh file, and each read reopens it for another look.
    Deleting it in that window fails with ``WinError 32`` ("used by another
    process"), which is exactly how ``test_srdf_findings`` flaked twice: its
    first test writes ``robot.urdf`` once, reads it forty-odd times across
    twenty subtests, and unlinks it in tearDown milliseconds after the last
    read. The handle is never Python's -- the runner's own 3.12 closes an
    early-exited ``iterparse`` promptly, and the leak was reproduced as absent
    on that exact interpreter -- so the cleanup waits it out.

    Deliberately narrow, mirroring the atomic rename: only ``WinError 32``
    retries (eight attempts over about six seconds, then the error propagates), the
    attribute does not exist off Windows so this is plain ``cleanup()`` on
    POSIX, and nothing is ignored -- a directory that cannot be removed in that
    window still fails the test loudly, as a real leaked handle should.
    """

    def cleanup(self) -> None:
        import gc
        import time

        for delay in (*CLEANUP_RETRY_DELAYS_SECONDS, None):
            try:
                super().cleanup()
                return
            except OSError as error:
                if getattr(error, "winerror", None) != WINDOWS_SHARING_VIOLATION or delay is None:
                    raise
                # A handle kept alive only by a reference cycle is released here,
                # so an in-process holder cannot masquerade as the scanner.
                gc.collect()
                time.sleep(delay)
