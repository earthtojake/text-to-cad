from __future__ import annotations

import re
from pathlib import Path


TEXT_TO_CAD_METADATA_PREFIX = "cadpy:"
TEXT_TO_CAD_SOURCE_PATH_KEY = "sourcePath"
TEXT_TO_CAD_SOURCE_HASH_KEY = "sourceHash"


def text_to_cad_identity_metadata(
    *,
    source_path: str,
    source_hash: str,
) -> dict[str, str]:
    return {
        TEXT_TO_CAD_SOURCE_PATH_KEY: source_path,
        TEXT_TO_CAD_SOURCE_HASH_KEY: source_hash,
    }


def write_dxf_text_to_cad_metadata(dxf_path: Path, metadata: dict[str, str]) -> None:
    path = dxf_path.expanduser().resolve()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = 0
    while start + 1 < len(lines) and lines[start].strip() == "999":
        value = lines[start + 1].strip()
        if not value.startswith(TEXT_TO_CAD_METADATA_PREFIX):
            break
        start += 2
    body = "".join(lines[start:])
    prefix = "".join(
        f"999\n{TEXT_TO_CAD_METADATA_PREFIX}{key}={value}\n"
        for key, value in metadata.items()
        if str(value or "").strip()
    )
    path.write_text(prefix + body, encoding="utf-8")


def read_dxf_text_to_cad_metadata(dxf_path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    try:
        lines = dxf_path.expanduser().resolve().read_text(encoding="utf-8").splitlines()
    except OSError:
        return metadata
    index = 0
    while index + 1 < len(lines):
        if lines[index].strip() != "999":
            index += 1
            continue
        value = lines[index + 1].strip()
        index += 2
        if not value.startswith(TEXT_TO_CAD_METADATA_PREFIX):
            continue
        key_value = value[len(TEXT_TO_CAD_METADATA_PREFIX):]
        key, separator, raw_value = key_value.partition("=")
        if separator and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key):
            metadata[key] = raw_value.strip()
    return metadata
