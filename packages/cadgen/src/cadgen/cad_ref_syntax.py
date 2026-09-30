from __future__ import annotations

import json
import re
from dataclasses import dataclass


# `<file>#<selectors>`, where the file half is optional. The prefix is the file's path relative
# to the root of the viewer the ref was copied from, or its absolute path, and it exists so a ref
# stays meaningful when it is pasted into a prompt that spans several files. It lives LEFT of the
# '#' on purpose: the selector grammar owns everything to the right, so a prefix can never collide
# with a label, its ':' qualifiers, or an entity's '.'.
# JSON-quoted paths mirror the JS parser, including literal filename delimiters.
QUOTED_PATH_PATTERN = r'"(?:[^"\\\r\n]|\\.)*"'
CAD_TOKEN_RE = re.compile(rf'^\s*({QUOTED_PATH_PATTERN}|[^#"\s]*)#([^\s]*)')
QUOTED_PREFIX_RE = re.compile(rf"^({QUOTED_PATH_PATTERN})#")
OCCURRENCE_SELECTOR_RE = re.compile(r"^o((?:\d+)(?:\.\d+)*)$")
OCCURRENCE_ENTITY_SELECTOR_RE = re.compile(r"^o((?:\d+)(?:\.\d+)*)\.([sfev])(\d+)$")
ENTITY_SELECTOR_RE = re.compile(r"^([sfev])(\d+)$")

# A build123d part label used in place of an occurrence id. Deliberately narrow: it must not
# start with a digit, and it excludes "." because that is the entity separator. Real labels in
# the repo are alphanumerics plus "_" and ":" (mounting_eye:lower, piston_rod:chrome), so this
# covers them while leaving the numeric grammar's territory untouched. Widening later is
# backwards compatible; narrowing would not be.
LABEL_PATTERN = r"[A-Za-z_][A-Za-z0-9_:]*"
LABEL_SELECTOR_RE = re.compile(rf"^({LABEL_PATTERN})$")
LABEL_ENTITY_SELECTOR_RE = re.compile(rf"^({LABEL_PATTERN})\.([sfev])(\d+)$")
# Mates are not part of the structured grammar -- consumers handle them -- and "m1" would
# otherwise be swallowed by LABEL_SELECTOR_RE.
MATE_SELECTOR_RE = re.compile(r"^m\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedSelector:
    selector_type: str
    occurrence_id: str
    ordinal: int | None
    canonical: str
    # Set when the occurrence was named by label rather than by numeric id. Resolution against
    # a loaded artifact turns this into an occurrence_id; the parser cannot, because it has no
    # index to look in.
    label: str = ""


@dataclass(frozen=True)
class ParsedToken:
    line: int
    token: str
    cad_path: str
    selectors: tuple[str, ...]


def _selector_type_for_kind(kind: str) -> str:
    if kind == "s":
        return "shape"
    if kind == "f":
        return "face"
    if kind == "e":
        return "edge"
    return "vertex"


def parse_cad_tokens(text: str) -> list[ParsedToken]:
    tokens: list[ParsedToken] = []
    for line_no, line in enumerate(text.splitlines() or [text], start=1):
        match = CAD_TOKEN_RE.match(line)
        if match is None:
            continue
        # The prefix is kept RAW: a resolver matches it as a segment-aligned suffix of the
        # document's own path (`path_has_suffix`), so normalizing it here -- dropping its
        # extension, say -- would break that contract.
        cad_path = str(match.group(1) or "")
        if cad_path.startswith('"'):
            try:
                cad_path = json.loads(cad_path)
            except ValueError:
                continue
        selector_text = str(match.group(2) or "")
        tokens.append(
            ParsedToken(
                line=line_no,
                token=match.group(0),
                cad_path=cad_path,
                selectors=tuple(normalize_selector_list(selector_text)),
            )
        )
    return tokens


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


def ensure_ref_file_matches(file_prefix: str, document_path: str, *, source_label: str = "ref") -> None:
    """Reject a ref whose file prefix names a file this command is not looking at.

    Copied refs may carry a file prefix (``STEP/plate.step#o1.2``) so they stay meaningful in a
    prompt spanning several files: the file's path relative to the viewer's root, or its absolute
    path. Either is a segment-aligned suffix of ``document_path``, the absolute path of the file
    the command was given. A CLI only ever inspects that file, so a prefix naming a DIFFERENT file
    has to be an error: silently ignoring it would inspect the wrong file and report a confident
    answer about geometry the user never asked about.

    CLIs do not resolve prefixes to paths -- the agent does that, then passes the file and the
    ref separately. See ``skills/cad/references/inspection-and-validation.md``.
    """
    prefix = str(file_prefix or "").strip()
    document = str(document_path or "").strip()
    if not prefix or not document or path_has_suffix(document, prefix):
        return
    raise ValueError(
        f"{source_label} names file {prefix!r} but this command targets {document!r}; "
        f"pass the file as the entry argument and the '#...' part as the ref"
    )


def normalize_cad_path(raw_cad_path: str) -> str | None:
    normalized = str(raw_cad_path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return None
    # Strip generator/model suffixes first so a model script target (plain
    # `<name>.py` in library-first, `<name>.step.py` historically) normalizes to
    # the same logical cad path as its `<name>.step` artifact.
    for suffix in (".step.py", ".stp.py", ".step", ".stp", ".py"):
        if normalized.lower().endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None
    return "/".join(parts)


def parse_selector(
    raw_selector: str,
    *,
    inherited_occurrence_id: str = "",
    inherited_label: str = "",
) -> ParsedSelector | None:
    # Only a LEADING "#" is the token marker. str.replace() takes the first "#"
    # anywhere, splicing "o1#f2" into the label "o1f2"; the JS parser strips /^#/
    # and leaves the rest opaque, and the two are one language.
    selector = str(raw_selector or "").strip()
    if selector.startswith("#"):
        selector = selector[1:]
    if not selector:
        return None

    occurrence_entity_match = OCCURRENCE_ENTITY_SELECTOR_RE.match(selector)
    if occurrence_entity_match:
        occurrence_id = f"o{occurrence_entity_match.group(1)}"
        kind = str(occurrence_entity_match.group(2))
        ordinal = int(occurrence_entity_match.group(3))
        return ParsedSelector(
            selector_type=_selector_type_for_kind(kind),
            occurrence_id=occurrence_id,
            ordinal=ordinal,
            canonical=f"{occurrence_id}.{kind}{ordinal}",
        )

    occurrence_match = OCCURRENCE_SELECTOR_RE.match(selector)
    if occurrence_match:
        occurrence_id = f"o{occurrence_match.group(1)}"
        return ParsedSelector(
            selector_type="occurrence",
            occurrence_id=occurrence_id,
            ordinal=None,
            canonical=occurrence_id,
        )

    entity_match = ENTITY_SELECTOR_RE.match(selector)
    if entity_match:
        kind = str(entity_match.group(1))
        ordinal = int(entity_match.group(2))
        if inherited_occurrence_id:
            return ParsedSelector(
                selector_type=_selector_type_for_kind(kind),
                occurrence_id=inherited_occurrence_id,
                ordinal=ordinal,
                canonical=f"{inherited_occurrence_id}.{kind}{ordinal}",
            )
        # An inherited label carries forward exactly like an inherited occurrence id, so
        # "#eye_shank.f45,f46" names two faces on the same part.
        if inherited_label:
            return ParsedSelector(
                selector_type=_selector_type_for_kind(kind),
                occurrence_id="",
                ordinal=ordinal,
                canonical=f"{inherited_label}.{kind}{ordinal}",
                label=inherited_label,
            )
        return ParsedSelector(
            selector_type=_selector_type_for_kind(kind),
            occurrence_id="",
            ordinal=ordinal,
            canonical=f"{kind}{ordinal}",
        )

    # Label forms are tried only after every numeric form has had its chance, so an existing
    # ref can never change meaning. Mates are excluded explicitly: they look like labels.
    if not MATE_SELECTOR_RE.match(selector):
        label_entity_match = LABEL_ENTITY_SELECTOR_RE.match(selector)
        if label_entity_match:
            label = str(label_entity_match.group(1))
            kind = str(label_entity_match.group(2))
            ordinal = int(label_entity_match.group(3))
            return ParsedSelector(
                selector_type=_selector_type_for_kind(kind),
                occurrence_id="",
                ordinal=ordinal,
                canonical=f"{label}.{kind}{ordinal}",
                label=label,
            )

        label_match = LABEL_SELECTOR_RE.match(selector)
        if label_match:
            label = str(label_match.group(1))
            return ParsedSelector(
                selector_type="label",
                occurrence_id="",
                ordinal=None,
                canonical=label,
                label=label,
            )

    return ParsedSelector(
        selector_type="opaque",
        occurrence_id="",
        ordinal=None,
        canonical=selector,
    )


def normalize_selector_list(raw_selector_list: str) -> list[str]:
    normalized: list[str] = []
    inherited_occurrence_id = ""
    inherited_label = ""
    for raw_selector in str(raw_selector_list or "").split(","):
        parsed = parse_selector(
            raw_selector,
            inherited_occurrence_id=inherited_occurrence_id,
            inherited_label=inherited_label,
        )
        if parsed is None:
            continue
        normalized.append(parsed.canonical)
        # Whichever naming scheme the selector used becomes the context for the bare entity
        # selectors that follow it, and clears the other one.
        if parsed.occurrence_id:
            inherited_occurrence_id = parsed.occurrence_id
            inherited_label = ""
        elif parsed.label:
            inherited_label = parsed.label
            inherited_occurrence_id = ""
    return normalized


def build_cad_token(cad_path: str, selector: str = "") -> str:
    """Assemble `<file>#<selectors>`; the file half is omitted when empty.

    `<prefix>#` with no selectors is meaningful -- it names a whole file.
    """
    prefix = str(cad_path or "").strip()
    if re.search(r'[\s#"\\]', prefix):
        prefix = json.dumps(prefix, ensure_ascii=False)
    return f"{prefix}#{selector or ''}"
