// Vite's `server.fs.allow` roots for the dev server.
//
// Vite checks a module id AFTER resolving it, so ids arrive as real paths. The
// develop layout reaches cadjs through the `viewer/packages/cadjs` symlink, so
// allowing only the symlink path leaves the real path outside the list and Vite
// refuses to serve anything it resolves through it -- notably
// `packages/cadjs/src/lib/render/glbMeshWorker.js`, whose loader falls back to
// main-thread GLB decoding, so the only symptom is a dev-server log line.
//
// Listing both the symlink path and its real path keeps the allow list correct
// in the symlinked develop layout and in a flat checkout, where the two are the
// same path and dedupe to one entry.

export function resolveServerFsAllow(paths, { realpath } = {}) {
  const allow = [];
  const add = (value) => {
    const entry = String(value || "").trim();
    if (entry && !allow.includes(entry)) {
      allow.push(entry);
    }
  };
  for (const candidate of Array.isArray(paths) ? paths : []) {
    if (!candidate) {
      continue;
    }
    add(candidate);
    if (typeof realpath !== "function") {
      continue;
    }
    try {
      add(realpath(candidate));
    } catch {
      // A root that does not exist yet is still worth allowing by its literal
      // path; there is simply no real path to add for it.
    }
  }
  return allow;
}
