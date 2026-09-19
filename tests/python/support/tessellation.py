"""Tiny TESS v4 fixture encoded by the shared JavaScript implementation."""
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess

CODEC = Path(__file__).resolve().parents[3] / "packages/core/src/lib/surf/tessellationCache.js"

@lru_cache(maxsize=1)
def tessellation_fixture():
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node is required to verify the shared TESS contract")
    script = """
import { createHash } from 'node:crypto';
const api = await import(process.argv[1]);
const component = {
  positions: new Float32Array([0,0,0, 2,0,0, 0,3,0]),
  normals: new Float32Array([0,0,1, 0,0,1, 0,0,1]),
  faceOrds: new Float32Array([1,1,1]), indices: new Uint32Array([0,1,2]),
  sideOrds: new Uint32Array([1,2,3]), faceRanges: [{ord:1,indexStart:0,indexCount:3}],
  bounds: {min:[0,0,0],max:[2,3,0]}, scale: Math.sqrt(13),
  edges: [{ord:1,visibilityClass:'boundary',polyline:new Float32Array([0,0,0, 2,0,0, 2,3,0])}],
};
const D='1'.repeat(64), O='a'.repeat(64), Q={chordTolerance:0.0015,angleTolerance:0.005};
const key=api.tessellationCacheKey(D,Q);
const encode=(shape, output=O)=>api.encodeComponentTessellation(shape,{
  surfaceInput:D,surfaceObject:output,tessellation:Q,partColor:[.2,.3,.4,1],edgeClasses:[[1,'boundary']],
});
const bytes=encode(component);
const changed=encode({...component,scale:component.scale+1});
console.log(JSON.stringify({key,bytes:Buffer.from(bytes).toString('base64'),
  changed:Buffer.from(changed).toString('base64'),
  changedSurface:Buffer.from(encode(component,'b'.repeat(64))).toString('base64'),
  facts:{schemaVersion:1,object:createHash('sha256').update(bytes).digest('hex'),...api.tessellationPayloadFacts(bytes)},
}));
"""
    result = subprocess.run([node, "--input-type=module", "-e", script, CODEC.as_uri()], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)
