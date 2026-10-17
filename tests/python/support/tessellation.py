"""A tiny part as cadgen stores it (``cadgen.store.parts``) -- its display mesh, one triangle
encoded by cadgen's own writer (``cadgen.store.meshes``), and its selector table -- and the
shared JavaScript reader every client decodes a mesh with."""
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

CORE = Path(__file__).resolve().parents[3] / "packages/core/src/lib/parts"


def _floats(*values: float) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _selector_table() -> bytes:
    """The smallest table ``selector_table.read_selector_table`` reads: one face, one edge and
    its two vertices, every other column empty."""
    from cadgen._internal.selector_table import (
        EDGE_COLUMNS, FACE_COLUMNS, OCCURRENCE_COLUMNS, SELECTOR_TABLE_SCHEMA_VERSION, SHAPE_COLUMNS,
        VERTEX_COLUMNS, selector_table_bytes,
    )

    def row(columns, ordinal=None, name=None):
        return [ordinal if column == "ordinal" else name if column == "name" else None for column in columns]

    return selector_table_bytes({
        "schemaVersion": SELECTOR_TABLE_SCHEMA_VERSION,
        "tables": {"occurrenceColumns": OCCURRENCE_COLUMNS, "shapeColumns": SHAPE_COLUMNS,
                   "faceColumns": FACE_COLUMNS, "edgeColumns": EDGE_COLUMNS, "vertexColumns": VERTEX_COLUMNS},
        "occurrences": [row(OCCURRENCE_COLUMNS)], "shapes": [row(SHAPE_COLUMNS, 1)],
        "faces": [row(FACE_COLUMNS, 1, "f:tile.extrude1.1")], "edges": [row(EDGE_COLUMNS, 1, "e:tile.extrude1.1")],
        "vertices": [row(VERTEX_COLUMNS, 1, "v:tile.extrude1.1"), row(VERTEX_COLUMNS, 2, "v:tile.extrude1.2")],
        "stats": {"shapeCount": 1, "faceCount": 1, "edgeCount": 1, "vertexCount": 2},
        "relations": {"faceEdgeRows": [0], "edgeFaceRows": [0], "edgeVertexRows": [0, 1], "vertexEdgeRows": [0, 0]},
    })


@lru_cache(maxsize=1)
def part_fixture() -> dict:
    """The part: ``key``, its display mesh (``glb``) and selector table (``selectors``), base64,
    and the ``record`` that names them, as ``parts.probe`` answers it once stored."""
    from cadgen.store.meshes import body_facts, encode_payload
    from cadgen.store.parts import PART_VERSION

    key = f"{'1' * 64}-v{PART_VERSION}"
    glb = encode_payload(
        part=key, positions=_floats(0, 0, 0, 2, 0, 0, 0, 3, 0), normals=_floats(0, 0, 1, 0, 0, 1, 0, 0, 1),
        indices=struct.pack("<3I", 0, 1, 2),
        face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3, "color": [0.2, 0.4, 0.6, 1.0]}],
        edges=[(1, "boundary", _floats(0, 0, 0, 2, 0, 0, 2, 3, 0))],
        bounds={"min": [0, 0, 0], "max": [2, 3, 0]},
    )
    table = _selector_table()
    facts = body_facts(glb)
    del facts["part"]
    record = {"glb": {"object": hashlib.sha256(glb).hexdigest(), **facts},
              "selectors": {"object": hashlib.sha256(table).hexdigest(), "byteLength": len(table),
                            "faceCount": 1, "edgeCount": 1, "vertexCount": 2}}
    text = lambda data: base64.b64encode(data).decode("ascii")  # noqa: E731
    return {"key": key, "glb": text(glb), "selectors": text(table), "record": record}


def store_part(fixture: dict | None = None) -> dict:
    """Store the part's two objects, then its record, in the current store (``CADGEN_CACHE_DIR``),
    as a derivation does; return the record."""
    from cadgen.store.parts import _write

    fixture = part_fixture() if fixture is None else fixture
    return _write(fixture["key"], base64.b64decode(fixture["glb"]), base64.b64decode(fixture["selectors"]))


def node() -> str:
    """The development Node that runs the client's half of the mesh contract."""
    found = shutil.which("node")
    if found is None:
        raise RuntimeError("Node is required to verify the shared mesh contract")
    return found


def js_reader(payloads: list[bytes]) -> list[list]:
    """What the shared JS reader makes of each body: ``[facts, part]`` -- what a part's record
    says of it (``testing.js partMeshFacts``) and the part it names -- or ``[None, None]``
    for a body it refuses."""
    script = """
import fs from 'node:fs';
const api = await import(process.argv[1]);
const testing = await import(process.argv[2]);
console.log(JSON.stringify(JSON.parse(fs.readFileSync(0, 'utf8')).map((body) => {
  const bytes = new Uint8Array(Buffer.from(body, 'base64'));
  const decoded = api.decodeComponentTessellation(bytes);
  return decoded ? [testing.partMeshFacts(bytes), decoded.part] : [null, null];
})));
"""
    result = subprocess.run([node(), "--input-type=module", "-e", script, (CORE / "tessellationCache.js").as_uri(),
                             (CORE / "testing.js").as_uri()],
                            input=json.dumps([base64.b64encode(payload).decode() for payload in payloads]),
                            text=True, capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)
