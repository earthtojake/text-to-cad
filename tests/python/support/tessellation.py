"""Tiny stored-mesh (GLB) fixture, encoded by cadgen's own writer (``cadgen.store.meshes``),
and the shared JavaScript reader every client decodes it with."""
import base64
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess

CODEC = Path(__file__).resolve().parents[3] / "packages/core/src/lib/surf/tessellationCache.js"


def _floats(*values: float) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


@lru_cache(maxsize=1)
def tessellation_fixture():
    from cadgen.store.meshes import encode_payload, payload_record, tessellation_key

    surface_input, chord, angle = "1" * 64, 0.0015, 0.005
    key = tessellation_key(surface_input, chord, angle)

    def encode(scale: float = math.sqrt(13), surface_object: str = "a" * 64) -> bytes:
        return encode_payload(
            surface_input=surface_input, surface_object=surface_object, chord=chord, angle=angle,
            positions=_floats(0, 0, 0, 2, 0, 0, 0, 3, 0), normals=_floats(0, 0, 1, 0, 0, 1, 0, 0, 1),
            indices=struct.pack("<3I", 0, 1, 2),
            face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3, "color": [0.2, 0.4, 0.6, 1.0]}],
            edges=[(1, "boundary", _floats(0, 0, 0, 2, 0, 0, 2, 3, 0))],
            bounds={"min": [0, 0, 0], "max": [2, 3, 0]}, scale=scale, part_color=[0.2, 0.3, 0.4, 1],
        )

    payload = encode()
    text = lambda data: base64.b64encode(data).decode("ascii")  # noqa: E731
    return {
        "key": key,
        "bytes": text(payload),
        "changed": text(encode(scale=math.sqrt(13) + 1)),
        "changedSurface": text(encode(surface_object="b" * 64)),
        "facts": payload_record(key, payload),
    }


def js_reader(payloads: list[bytes]) -> list[list]:
    """What the shared JS reader makes of each body: ``[facts, decodes]`` (facts None for a refusal)."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node is required to verify the shared mesh contract")
    script = """
import fs from 'node:fs';
const api = await import(process.argv[1]);
console.log(JSON.stringify(JSON.parse(fs.readFileSync(0, 'utf8')).map((body) => {
  const bytes = new Uint8Array(Buffer.from(body, 'base64'));
  return [api.tessellationPayloadFacts(bytes), api.decodeComponentTessellation(bytes) !== null];
})));
"""
    result = subprocess.run([node, "--input-type=module", "-e", script, CODEC.as_uri()],
                            input=json.dumps([base64.b64encode(payload).decode() for payload in payloads]),
                            text=True, capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)
