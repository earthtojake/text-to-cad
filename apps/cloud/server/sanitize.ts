// What a hosted build shows runs none of the model's code.
//
// A STEP's sidecar may carry an `animation` section: a JavaScript module the viewer imports on the
// page's own origin (`sourceSidecar.animation` in a catalog row, the same section in the sidecar
// file). On this server that origin also serves the account pages, so a build link would run its
// author's script as whoever opened it. Until model scripts run in an isolated frame, every export
// loses them at ingest. It happens here, in the server, and not in the sandbox: whatever the
// sandbox's own steps did after the model ran is the model's to tamper with.
import { createHash } from 'node:crypto';

const SIDECAR = /\.(step|stp)\.json$/i;
// Catalog fields that name or digest a model script. `renderModuleUrl` is one the client still
// rebases (core's origin.js) though nothing reads it; a script URL is never served either way.
const SCRIPT_KEYS = new Set(['animationHash', 'renderModuleUrl']);

const sha256Hex = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

/** Remove every model script from one recorded JSON answer, in place. Answers whether it changed. */
export function stripScriptsFromJson(value: unknown): boolean {
  let changed = false;
  const visit = (node: unknown) => {
    if (Array.isArray(node)) { node.forEach(visit); return; }
    if (!isRecord(node)) return;
    for (const key of Object.keys(node)) {
      if (SCRIPT_KEYS.has(key)) { delete node[key]; changed = true; continue; }
      if (key === 'sourceSidecar' && isRecord(node[key]) && 'animation' in (node[key] as Record<string, unknown>)) {
        delete (node[key] as Record<string, unknown>).animation;
        changed = true;
      }
      visit(node[key]);
    }
  };
  visit(value);
  return changed;
}

/**
 * Strip model scripts from a parsed export (its routes are edited in place). A sidecar file served
 * through `/__cad/asset` is rewritten without its `animation` section and stored as a new object; a
 * sidecar that is not JSON is dropped from the routes rather than served. `objects` holds the
 * export's bytes by SHA-256; the answer lists the objects this added.
 */
export function stripModelScripts(index: Record<string, any>, objects: Map<string, Uint8Array>): { added: [string, Uint8Array][] } {
  const added: [string, Uint8Array][] = [];
  for (const answer of Object.values((index.routes?.['/__cad/catalog'] ?? {}) as Record<string, unknown>)) stripScriptsFromJson(answer);
  const assets = (index.routes?.['/__cad/asset'] ?? {}) as Record<string, any>;
  for (const [key, entry] of Object.entries(assets)) {
    if (!SIDECAR.test(key)) continue;
    const bytes = typeof entry?.object === 'string' ? objects.get(entry.object) : undefined;
    let sidecar: unknown;
    try {
      sidecar = bytes ? JSON.parse(new TextDecoder().decode(bytes)) : undefined;
    } catch {
      sidecar = undefined;
    }
    if (!isRecord(sidecar)) { delete assets[key]; continue; }
    if (!('animation' in sidecar)) continue;
    delete sidecar.animation;
    const rewritten = new TextEncoder().encode(JSON.stringify(sidecar));
    const sha = sha256Hex(rewritten);
    objects.set(sha, rewritten);
    added.push([sha, rewritten]);
    assets[key] = { ...entry, object: sha, bytes: rewritten.byteLength };
  }
  return { added };
}
