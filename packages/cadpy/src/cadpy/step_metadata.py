from __future__ import annotations

import re
import posixpath
from pathlib import Path


TEXT_TO_CAD_GENERATOR = "cadpy"
TEXT_TO_CAD_GENERATOR_PROPERTY = "cadpy:generator"
TEXT_TO_CAD_ENTRY_KIND_PROPERTY = "cadpy:entryKind"
TEXT_TO_CAD_SOURCE_PATH_PROPERTY = "cadpy:sourcePath"
TEXT_TO_CAD_SOURCE_HASH_PROPERTY = "cadpy:sourceHash"
TEXT_TO_CAD_METADATA_GROUP = "cadpy metadata"
TEXT_TO_CAD_METADATA_TAIL_BYTES = 1024 * 1024
TEXT_TO_CAD_METADATA_HEAD_BYTES = 2 * 1024 * 1024


_STEP_STRING_PATTERN = r"'(?:''|[^'])*'"


def _step_escape(value: object) -> str:
    return str(value).replace("'", "''")


def _step_unescape(value: str) -> str:
    raw = value.strip()
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        raw = raw[1:-1]
    return raw.replace("''", "'")


def normalize_text_to_cad_entry_kind(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"part", "assembly"} else None


def normalize_text_to_cad_source_path(value: object) -> str | None:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        return None
    normalized = posixpath.normpath(raw)
    if normalized in {"", ".", ".."}:
        return None
    return normalized


def _max_entity_id(step_text: str) -> int:
    ids = [int(match) for match in re.findall(r"#(\d+)\s*=", step_text)]
    return max(ids, default=0)


def _root_product_definition_ref(step_text: str) -> str | None:
    shape_definition_match = re.search(
        r"#\d+\s*=\s*SHAPE_DEFINITION_REPRESENTATION\s*\(\s*(#\d+)\s*,\s*#\d+\s*\)\s*;",
        step_text,
        re.IGNORECASE | re.DOTALL,
    )
    if shape_definition_match:
        shape_definition_ref = re.escape(shape_definition_match.group(1).lstrip("#"))
        product_shape_match = re.search(
            rf"#{shape_definition_ref}\s*=\s*PRODUCT_DEFINITION_SHAPE\s*\(.*?,\s*(#\d+)\s*\)\s*;",
            step_text,
            re.IGNORECASE | re.DOTALL,
        )
        if product_shape_match:
            return product_shape_match.group(1)
    match = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\s*\(", step_text, re.IGNORECASE)
    return f"#{match.group(1)}" if match else None


def _shape_representation_context_ref(step_text: str) -> str | None:
    match = re.search(
        r"#\d+\s*=\s*(?:ADVANCED_BREP_SHAPE_REPRESENTATION|SHAPE_REPRESENTATION)\s*\(.*?,\s*#(\d+)\s*\)\s*;",
        step_text,
        re.IGNORECASE | re.DOTALL,
    )
    return f"#{match.group(1)}" if match else None


def _metadata_entities(
    *,
    first_id: int,
    product_definition_ref: str,
    representation_context_ref: str,
    properties: list[tuple[str, str]],
) -> list[str]:
    next_id = first_id
    entities: list[str] = []
    for property_name, property_value in properties:
        item_id = next_id
        repr_id = next_id + 1
        prop_id = next_id + 2
        link_id = next_id + 3
        next_id += 4
        property_name_escaped = _step_escape(property_name)
        property_value_escaped = _step_escape(property_value)
        metadata_group_escaped = _step_escape(TEXT_TO_CAD_METADATA_GROUP)
        entities.extend(
            [
                (
                    f"#{item_id}=DESCRIPTIVE_REPRESENTATION_ITEM("
                    f"'{property_name_escaped}','{property_value_escaped}');"
                ),
                (
                    f"#{repr_id}=REPRESENTATION("
                    f"'{property_name_escaped}',(#{item_id}),{representation_context_ref});"
                ),
                (
                    f"#{prop_id}=PROPERTY_DEFINITION("
                    f"'{metadata_group_escaped}','{property_name_escaped}',{product_definition_ref});"
                ),
                f"#{link_id}=PROPERTY_DEFINITION_REPRESENTATION(#{prop_id},#{repr_id});",
            ]
        )
    return entities


def inject_text_to_cad_step_metadata(
    step_path: Path,
    *,
    entry_kind: str,
    generator: str = TEXT_TO_CAD_GENERATOR,
    source_path: str | None = None,
    source_hash: str | None = None,
) -> None:
    normalized_entry_kind = normalize_text_to_cad_entry_kind(entry_kind)
    if normalized_entry_kind is None:
        raise ValueError(f"Unsupported cadpy STEP entry kind: {entry_kind!r}")
    normalized_source_path = normalize_text_to_cad_source_path(source_path)
    if source_path and normalized_source_path is None:
        raise ValueError(f"Unsupported cadpy STEP source path: {source_path!r}")

    step_path = step_path.expanduser().resolve()
    if _try_inject_text_to_cad_step_metadata_tail(
        step_path,
        entry_kind=normalized_entry_kind,
        generator=generator,
        source_path=normalized_source_path,
        source_hash=source_hash,
    ):
        return

    step_text = step_path.read_text(encoding="utf-8")
    product_definition_ref = _root_product_definition_ref(step_text)
    representation_context_ref = _shape_representation_context_ref(step_text)
    data_end = list(re.finditer(r"ENDSEC\s*;", step_text, re.IGNORECASE))
    if not product_definition_ref or not representation_context_ref or not data_end:
        raise RuntimeError(f"Could not locate STEP product metadata insertion point in {step_path}")

    properties = [
        (TEXT_TO_CAD_GENERATOR_PROPERTY, generator),
        (TEXT_TO_CAD_ENTRY_KIND_PROPERTY, normalized_entry_kind),
    ]
    if normalized_source_path:
        properties.append((TEXT_TO_CAD_SOURCE_PATH_PROPERTY, normalized_source_path))
    if source_hash:
        properties.append((TEXT_TO_CAD_SOURCE_HASH_PROPERTY, source_hash))

    entities = _metadata_entities(
        first_id=_max_entity_id(step_text) + 1,
        product_definition_ref=product_definition_ref,
        representation_context_ref=representation_context_ref,
        properties=properties,
    )
    insertion = "\n" + "\n".join(entities) + "\n"
    insert_at = data_end[-1].start()
    step_path.write_text(step_text[:insert_at] + insertion + step_text[insert_at:], encoding="utf-8")


def _read_step_head_text(step_path: Path, *, head_bytes: int = TEXT_TO_CAD_METADATA_HEAD_BYTES) -> str:
    with step_path.expanduser().resolve().open("rb") as handle:
        payload = handle.read(max(1, int(head_bytes)))
    return payload.decode("utf-8", errors="ignore")


def _try_inject_text_to_cad_step_metadata_tail(
    step_path: Path,
    *,
    entry_kind: str,
    generator: str,
    source_path: str | None,
    source_hash: str | None,
) -> bool:
    tail_payload, offset, is_full_file = _read_step_tail_payload(step_path)
    try:
        tail_text = tail_payload.decode("utf-8")
    except UnicodeDecodeError:
        return False
    data_end = list(re.finditer(r"ENDSEC\s*;", tail_text, re.IGNORECASE))
    if not data_end:
        return False

    header_text = tail_text if is_full_file else _read_step_head_text(step_path)
    product_definition_ref = _root_product_definition_ref(header_text)
    representation_context_ref = _shape_representation_context_ref(header_text)
    max_entity_id = _max_entity_id(tail_text)
    if not product_definition_ref or not representation_context_ref or max_entity_id <= 0:
        return False

    properties = [
        (TEXT_TO_CAD_GENERATOR_PROPERTY, generator),
        (TEXT_TO_CAD_ENTRY_KIND_PROPERTY, entry_kind),
    ]
    if source_path:
        properties.append((TEXT_TO_CAD_SOURCE_PATH_PROPERTY, source_path))
    if source_hash:
        properties.append((TEXT_TO_CAD_SOURCE_HASH_PROPERTY, source_hash))
    entities = _metadata_entities(
        first_id=max_entity_id + 1,
        product_definition_ref=product_definition_ref,
        representation_context_ref=representation_context_ref,
        properties=properties,
    )
    insertion = "\n" + "\n".join(entities) + "\n"
    insert_local = data_end[-1].start()
    encoded_tail = (tail_text[:insert_local] + insertion + tail_text[insert_local:]).encode("utf-8")
    with step_path.open("r+b") as handle:
        handle.seek(offset)
        handle.write(encoded_tail)
        handle.truncate()
    return True


def _read_step_tail_payload(
    step_path: Path,
    *,
    tail_bytes: int = TEXT_TO_CAD_METADATA_TAIL_BYTES,
) -> tuple[bytes, int, bool]:
    resolved = step_path.expanduser().resolve()
    size = resolved.stat().st_size
    offset = max(0, size - max(1, int(tail_bytes)))
    with resolved.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read()
    return payload, offset, offset == 0


def read_text_to_cad_step_metadata_text(step_text: str) -> dict[str, str]:
    descriptive_items: dict[str, tuple[str, str]] = {}
    for match in re.finditer(
        rf"#(\d+)\s*=\s*DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*({_STEP_STRING_PATTERN})\s*,\s*({_STEP_STRING_PATTERN})\s*\)\s*;",
        step_text,
        re.IGNORECASE | re.DOTALL,
    ):
        descriptive_items[f"#{match.group(1)}"] = (_step_unescape(match.group(2)), _step_unescape(match.group(3)))

    representations: dict[str, tuple[str, list[str]]] = {}
    for match in re.finditer(
        rf"#(\d+)\s*=\s*REPRESENTATION\s*\(\s*({_STEP_STRING_PATTERN})\s*,\s*\(([^)]*)\)\s*,\s*#\d+\s*\)\s*;",
        step_text,
        re.IGNORECASE | re.DOTALL,
    ):
        item_refs = re.findall(r"#\d+", match.group(3))
        representations[f"#{match.group(1)}"] = (_step_unescape(match.group(2)), item_refs)

    property_definitions: dict[str, str] = {}
    for match in re.finditer(
        rf"#(\d+)\s*=\s*PROPERTY_DEFINITION\s*\(\s*({_STEP_STRING_PATTERN})\s*,\s*({_STEP_STRING_PATTERN})\s*,\s*#[0-9]+\s*\)\s*;",
        step_text,
        re.IGNORECASE | re.DOTALL,
    ):
        property_name = _step_unescape(match.group(3))
        if property_name in {
            TEXT_TO_CAD_GENERATOR_PROPERTY,
            TEXT_TO_CAD_ENTRY_KIND_PROPERTY,
            TEXT_TO_CAD_SOURCE_PATH_PROPERTY,
            TEXT_TO_CAD_SOURCE_HASH_PROPERTY,
            "cadpy:entry_kind",
        }:
            property_definitions[f"#{match.group(1)}"] = property_name

    metadata: dict[str, str] = {}
    for match in re.finditer(
        r"#\d+\s*=\s*PROPERTY_DEFINITION_REPRESENTATION\s*\(\s*(#\d+)\s*,\s*(#\d+)\s*\)\s*;",
        step_text,
        re.IGNORECASE | re.DOTALL,
    ):
        property_name = property_definitions.get(match.group(1))
        representation = representations.get(match.group(2))
        if not property_name or not representation:
            continue
        _, item_refs = representation
        value = ""
        for item_ref in item_refs:
            item = descriptive_items.get(item_ref)
            if item is not None:
                value = item[1]
                break
        if property_name == TEXT_TO_CAD_GENERATOR_PROPERTY:
            metadata["generator"] = value
        elif property_name in {TEXT_TO_CAD_ENTRY_KIND_PROPERTY, "cadpy:entry_kind"}:
            normalized_entry_kind = normalize_text_to_cad_entry_kind(value)
            if normalized_entry_kind is not None:
                metadata["entryKind"] = normalized_entry_kind
        elif property_name == TEXT_TO_CAD_SOURCE_PATH_PROPERTY:
            normalized_source_path = normalize_text_to_cad_source_path(value)
            if normalized_source_path is not None:
                metadata["sourcePath"] = normalized_source_path
        elif property_name == TEXT_TO_CAD_SOURCE_HASH_PROPERTY:
            metadata["sourceHash"] = value
    return metadata


def _read_step_tail_text(step_path: Path, *, tail_bytes: int = TEXT_TO_CAD_METADATA_TAIL_BYTES) -> tuple[str, bool]:
    payload, _offset, is_full_file = _read_step_tail_payload(step_path, tail_bytes=tail_bytes)
    return payload.decode("utf-8", errors="ignore"), is_full_file


def read_text_to_cad_step_metadata(step_path: Path) -> dict[str, str]:
    tail_text, is_full_file = _read_step_tail_text(step_path)
    if (
        TEXT_TO_CAD_GENERATOR_PROPERTY not in tail_text
        and TEXT_TO_CAD_ENTRY_KIND_PROPERTY not in tail_text
        and TEXT_TO_CAD_SOURCE_PATH_PROPERTY not in tail_text
        and TEXT_TO_CAD_SOURCE_HASH_PROPERTY not in tail_text
    ):
        return {}
    metadata = read_text_to_cad_step_metadata_text(tail_text)
    if metadata or is_full_file:
        return metadata
    return read_text_to_cad_step_metadata_text(step_path.read_text(encoding="utf-8"))
