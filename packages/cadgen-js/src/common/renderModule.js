// The render module beside a document: `<name>.step.js`.
//
// A STEP document may carry, beside it and its `.step.json` sidecar, ONE
// JavaScript module the renderer loads by name — `part.step` -> `part.step.js`.
// It is authored and committed, never generated, and no build reads it: what
// it describes is render-only behaviour, so an edit is a reload in the viewer
// and never a rebuild. Today its one export is `clips` (choreography — see the
// cad skill's kinematics reference for the clip contract); future render-only
// exports live in the same file, and an export this loader does not know is an
// ERROR, never silently ignored.
//
// Kinematics is the other half and stays entirely apart (kinematicsModule.js
// reads the sidecar's typed mates): the two meet only in the effect records.
//
// This is the one loader every client uses — the viewer, the snapshot page
// (headlessRenderEntry.js) and the docs hero — so what the file may do is
// decided in one place. The module is fetched as text and imported through a
// Blob URL: the page realm, no relative imports, no source-tree access.

import { normalizeAnimationClips, evaluateAnimationClip } from "./animationRuntime.js";

// Every export the renderer understands. Extending the render module means
// adding a name here and a consumer for it — nothing else.
export const RENDER_MODULE_EXPORTS = Object.freeze(["clips"]);

// `part.step` -> `part.step.js`, for the URL forms clients hold: a plain path
// or URL (`.../STEP/part.step`, `/hero/part.step`) and the viewer's asset route
// (`/__cad/asset?file=STEP%2Fpart.step`), whose LAST path segment is "asset"
// and whose document lives in the `file` query parameter.
export function renderModuleUrlForDocument(documentUrl) {
  const text = String(documentUrl || "").trim();
  if (!text) {
    return "";
  }
  const [beforeHash, hash = ""] = text.split("#");
  const query = /([?&]file=)([^&]+)/.exec(beforeHash);
  if (query) {
    const encoded = query[2];
    const rewritten = beforeHash.replace(query[0], `${query[1]}${encoded}${encodeURIComponent(".js")}`);
    return hash ? `${rewritten}#${hash}` : rewritten;
  }
  const [pathPart, search = ""] = beforeHash.split("?");
  const withJs = `${pathPart}.js`;
  return `${withJs}${search ? `?${search}` : ""}${hash ? `#${hash}` : ""}`;
}

// The module's own filename out of its URL, for messages.
export function renderModuleName(url) {
  const text = String(url || "").split("#")[0];
  const query = /[?&]file=([^&]+)/.exec(text);
  const target = query ? decodeURIComponent(query[1]) : text.split("?")[0];
  return target.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "render module";
}

// Fetch the module's text. A 404 is not an error: a document without a render
// module is the common case, and the answer is `null`.
export async function fetchRenderModuleSource(url) {
  const target = String(url || "").trim();
  if (!target) {
    return null;
  }
  const response = await fetch(target, { cache: "no-store" });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`${renderModuleName(target)}: HTTP ${response.status}`);
  }
  return await response.text();
}

// Base64 of the module text, for a `data:` module URL — the same way in the
// browser and in Node, so the snapshot page, the viewer and the tests import
// through one path.
function base64Utf8(text) {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(text, "utf8").toString("base64");
  }
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

// Import module TEXT as an ES module in the page realm: no relative imports,
// no source-tree access. Syntax and top-level runtime errors surface with the
// module's name in front.
export async function importRenderModule(moduleSource, { name = "render module" } = {}) {
  const text = String(moduleSource || "");
  const url = `data:text/javascript;base64,${base64Utf8(text)}`;
  try {
    return await import(/* webpackIgnore: true */ /* @vite-ignore */ url);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`${name}: ${reason}`);
  }
}

// The module namespace -> what the renderer consumes. Unknown exports are an
// error naming them and the vocabulary, so a typo (`clip`, `animations`) or a
// contract this build does not know fails loudly instead of animating nothing.
export function compileRenderModule(moduleNamespace, { name = "render module" } = {}) {
  const exported = Object.keys(moduleNamespace || {}).filter((key) => key !== "default");
  const unknown = exported.filter((key) => !RENDER_MODULE_EXPORTS.includes(key));
  if (unknown.length) {
    throw new Error(
      `${name}: unknown export${unknown.length === 1 ? "" : "s"} ${unknown.join(", ")} — `
      + `the renderer understands: ${RENDER_MODULE_EXPORTS.join(", ")}`
    );
  }
  if ("default" in (moduleNamespace || {})) {
    throw new Error(`${name}: a default export is not a render-module export — use named exports (${RENDER_MODULE_EXPORTS.join(", ")})`);
  }
  const clips = normalizeAnimationClips(moduleNamespace?.clips);
  return { clips };
}

/** Load the render module beside a document. Resolves to `null` when the
 * document has none (404), to `{ clips }` when it does; throws on HTTP
 * failures, syntax errors and unknown exports. */
export async function loadRenderModule(url) {
  const source = await fetchRenderModuleSource(url);
  if (source === null) {
    return null;
  }
  const name = renderModuleName(url);
  const namespace = await importRenderModule(source, { name });
  return compileRenderModule(namespace, { name });
}

// Validate loaded clips against the compiled tree: each clip's update(t, m) is
// evaluated once at t = 0 against the model's parts, so an unresolved target
// (a label the tree does not carry, an occurrence id that is not there) is
// reported at LOAD, in the Status tab, rather than the first time playback
// reaches that frame. Returns one `{ clip, error }` per failing clip.
export function validateRenderModuleClips(THREE, meshData, clips) {
  const problems = [];
  for (const clip of Object.values(clips || {})) {
    try {
      evaluateAnimationClip(THREE, meshData, clip, 0);
    } catch (error) {
      problems.push({
        clip: clip.id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
  return problems;
}
