"""Translation between a Viewer URL's path and a filesystem path.

A page URL's PATH is the absolute directory it opens, exactly as in a file://
URL. On POSIX the two forms are identical -- `/Users/me/models` is already the
filesystem path -- so this module is a no-op there. On Windows they differ: an
absolute path carries a drive (`D:\\models`) while a URL path must begin with
`/`, so the wire form is `/D:/models`. The client reads that straight off
`location.pathname` and hands it back as `?dir=`.

That leading slash is URL syntax, NOT part of the path, and every stdlib path
call reads it as one:

    os.path.abspath("/D:/models")        -> "C:\\D:\\models"   (slash = current drive's root)
    os.path.join(dist_root, "D:/models") -> "D:\\models"       (drive-absolute arg drops the base)

Both silently produce a path the user never asked for -- the second one made
every Windows directory request look like a traversal escape and return 403
(issue #211). Neither is caught by an ubuntu-only CI, which is why the seam
lives in one module with both directions named.
"""

from __future__ import annotations

import os

# Bound once so tests can swap in `ntpath` and exercise the Windows branches on a
# POSIX host. `splitdrive` is what makes these helpers platform-correct without an
# `os.name` check: on POSIX it never reports a drive, so every transform below
# degrades to the identity.
_PATH = os.path


def filesystem_path_from_url_path(value: str) -> str:
    """The filesystem path a Viewer URL path names.

    Drops the URL's leading separator when a drive letter follows it, so
    `/D:/models` resolves as `D:\\models` rather than `C:\\D:\\models`. A POSIX
    path is returned unchanged -- its leading slash IS part of the path.
    """
    text = str(value or "")
    if text[:1] in ("/", "\\") and _PATH.splitdrive(text[1:])[0]:
        return text[1:]
    return text


def url_path_from_filesystem_path(file_path: str) -> str:
    """The URL path that opens a directory: the inverse of the above.

    `D:\\models` becomes `/D:/models`; a POSIX path is already its own URL path.
    Returns "" for an empty input, which names no directory (the backend reads
    that as its cwd).

    Only the PLATFORM's separator is rewritten, so a backslash stays a literal
    filename character on POSIX, where it legally is one.
    """
    text = str(file_path or "").replace(_PATH.sep, "/")
    if not text:
        return ""
    return text if text.startswith("/") else "/" + text


def url_path_as_relative(value: str) -> str:
    """A URL path reduced to a RELATIVE path, safe to join onto a base directory.

    Strips leading separators and any drive so `os.path.join(base, ...)` cannot
    silently discard `base`. Traversal segments are deliberately preserved: the
    caller still has to run its own containment check, and this must not be
    mistaken for one.
    """
    stripped = str(value or "").lstrip("/\\")
    return _PATH.splitdrive(stripped)[1].lstrip("/\\")
