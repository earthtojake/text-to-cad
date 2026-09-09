// Node-side store for the shared component-tessellation cache: the
// <cache root>/meshes/<key>.tess directory consumed by bin/mesh-export.mjs
// and served to the snapshot page by cadgen's snapshot host (which reads the
// same directory from Python — the path and naming here are a cross-language
// contract). Best-effort by design: read/write failures are misses, writes
// are atomic (tmp + rename), CADGEN_MESH_CACHE=0 disables everything.
//
// Keep this file the only fs-touching half; the codec and key scheme live in
// tessellationCache.js, which stays browser-pure.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function tessellationCacheEnabled(env = process.env) {
  return env.CADGEN_MESH_CACHE !== "0";
}

// ONE resolution rule for the user-level cadgen cache root, mirrored from the
// Python authority (cadgen/_internal/cache_paths.py — sync-tested by
// tests/python/global/test_cache_root_sync.py): CADGEN_CACHE_DIR override,
// else the platform cache convention (XDG_CACHE_HOME on POSIX, LOCALAPPDATA
// on Windows — the latter untested in CI, keep it trivially auditable), else
// ~/.cache/cadgen.
export function cadgenCacheRootDir(env = process.env) {
  const override = (env.CADGEN_CACHE_DIR || "").trim();
  if (override) return override;
  if (process.platform === "win32") {
    const localAppData = (env.LOCALAPPDATA || "").trim();
    if (localAppData) return path.join(localAppData, "cadgen");
  } else {
    const xdgCacheHome = (env.XDG_CACHE_HOME || "").trim();
    if (xdgCacheHome) return path.join(xdgCacheHome, "cadgen");
  }
  return path.join(os.homedir(), ".cache", "cadgen");
}

export function tessellationCacheDir() {
  return path.join(cadgenCacheRootDir(), "meshes");
}

export function readCachedTessellationBytes(key) {
  if (!tessellationCacheEnabled()) return null;
  try {
    const buffer = fs.readFileSync(path.join(tessellationCacheDir(), `${key}.tess`));
    return new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  } catch {
    return null;
  }
}

export function writeCachedTessellationBytes(key, bytes) {
  if (!tessellationCacheEnabled()) return;
  try {
    const dir = tessellationCacheDir();
    fs.mkdirSync(dir, { recursive: true });
    const target = path.join(dir, `${key}.tess`);
    const temp = `${target}.${process.pid}.tmp`;
    fs.writeFileSync(temp, bytes);
    fs.renameSync(temp, target);
  } catch {
    // Best-effort: a full disk or a permissions problem must not fail callers.
  }
}
