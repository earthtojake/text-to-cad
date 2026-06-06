from __future__ import annotations

import re
from dataclasses import dataclass


CAD_TOKEN_RE = re.compile(r"^\s*#([^\s]*)")
OCCURRENCE_SELECTOR_RE = re.compile(r"^o((?:\d+)(?:\.\d+)*)$")
OCCURRENCE_ENTITY_SELECTOR_RE = re.compile(r"^o((?:\d+)(?:\.\d+)*)\.([sfev])(\d+)$")
ENTITY_SELECTOR_RE = re.compile(r"^([sfev])(\d+)$")


@dataclass(frozen=True)
class ParsedSelector:
    selector_type: str
    occurrence_id: str
    ordinal: int | None
    canonical: str


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
        selector_text = str(match.group(1) or "")
        tokens.append(
            ParsedToken(
                line=line_no,
                token=match.group(0),
                cad_path="",
                selectors=tuple(normalize_selector_list(selector_text)),
            )
        )
    return tokens


def normalize_cad_path(raw_cad_path: str) -> str | None:
    normalized = str(raw_cad_path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return None
    for suffix in (".step", ".stp"):
        if normalized.lower().endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None
    return "/".join(parts)


def parse_selector(raw_selector: str, *, inherited_occurrence_id: str = "") -> ParsedSelector | None:
    selector = str(raw_selector or "").strip().replace("#", "", 1)
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
        return ParsedSelector(
            selector_type=_selector_type_for_kind(kind),
            occurrence_id="",
            ordinal=ordinal,
            canonical=f"{kind}{ordinal}",
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
    for raw_selector in str(raw_selector_list or "").split(","):
        parsed = parse_selector(raw_selector, inherited_occurrence_id=inherited_occurrence_id)
        if parsed is None:
            continue
        normalized.append(parsed.canonical)
        if parsed.occurrence_id:
            inherited_occurrence_id = parsed.occurrence_id
    return normalized


def build_cad_token(cad_path: str, selector: str = "") -> str:
    _ = cad_path
    if not selector:
        return "#"
    return f"#{selector}"
