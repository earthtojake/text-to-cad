"""The path half of a native board reference."""
import json
import os
import re

QUOTED_PATH_PATTERN = r'"(?:[^"\\\r\n]|\\.)*"'
QUOTED_PREFIX_RE = re.compile(rf"^({QUOTED_PATH_PATTERN})#")

def _path_segments(path: str) -> list[str]:
    return [part for part in str(path or "").replace("\\", "/").split("/") if part]


def path_has_suffix(path: str, suffix: str) -> bool:
    """Does ``suffix`` name ``path``? Segment-aligned, never a substring match.

    ``plate.stl`` names ``a/b/plate.stl``; ``late.stl`` names nothing.
    """
    path_segments = _path_segments(path)
    suffix_segments = _path_segments(suffix)
    if not suffix_segments or len(suffix_segments) > len(path_segments):
        return False
    return path_segments[len(path_segments) - len(suffix_segments) :] == suffix_segments


def ref_prefix_names(prefix: str, document_path: str) -> bool:
    """Whether a ref's file prefix names ``document_path``, read as a path.

    ``~`` expands and links resolve, so any spelling of the same file names it. An absolute
    prefix names the document only if it is that file. A relative one is read from the working
    directory: if it names a file from there, that file has to be the document. If it names
    nothing from there, it can still be the end of the document's path, segment by segment, so a
    path under the viewer's root names its file wherever the command runs.
    """
    prefix = str(prefix or "").strip()
    document = str(document_path or "").strip()
    if not prefix or not document:
        return False
    candidate = os.path.expanduser(prefix)
    try:
        return os.path.samefile(candidate, document)
    except (OSError, ValueError):
        pass
    if os.path.isabs(candidate):
        # Neither path is a file here (a document named but not on disk): compare them as paths.
        return os.path.normcase(os.path.realpath(candidate)) == os.path.normcase(os.path.realpath(document))
    return path_has_suffix(document, prefix)


def split_cad_ref(text: str) -> tuple[str, str]:
    """One ref as ``(file prefix, selector text)``; the prefix is ``""`` when it has none.

    A prefix naming a path with a space, a quote, a ``#`` or a backslash -- any absolute Windows
    path -- is JSON-quoted (:func:`build_cad_token`), so it is decoded here rather than cut at its
    first ``#``.
    """
    stripped = str(text or "").strip()
    quoted = QUOTED_PREFIX_RE.match(stripped)
    if quoted:
        try:
            return json.loads(quoted.group(1)), stripped[quoted.end() :]
        except ValueError:
            pass
    prefix, hash_mark, selectors = stripped.partition("#")
    return (prefix.strip(), selectors) if hash_mark else ("", stripped)
