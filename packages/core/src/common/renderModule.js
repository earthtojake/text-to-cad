// Embedded source-animation compiler. A schema-v9 STEP sidecar may carry one
// self-contained JavaScript module in `animation.source`. Clients import that
// text in their own realm; there is no adjacent `.step.js` discovery or fetch.

import { normalizeAnimationClips, evaluateAnimationClip } from "./animationRuntime.js";
import { loadTubeDeformation } from "./tubeDeformationChunk.js";
import { normalizeSourceAnimation } from "./sourceSidecar.js";

export const ANIMATION_MODULE_EXPORTS = Object.freeze(["clips"]);

function base64Utf8(text) {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(text, "utf8").toString("base64");
  }
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export async function importAnimationModule(moduleSource, { name = "embedded animation" } = {}) {
  const text = String(moduleSource || "");
  // Browser hosts permit these document-owned modules with script-src blob:;
  // they need not allow arbitrary data: scripts or unsafe-eval. Node's ESM
  // loader does not support blob: URLs, so retain data: for that environment.
  const browserModule = typeof window !== "undefined";
  const url = browserModule
    ? URL.createObjectURL(new Blob([text], { type: "text/javascript" }))
    : `data:text/javascript;base64,${base64Utf8(text)}`;
  try {
    return await import(/* webpackIgnore: true */ /* @vite-ignore */ url);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`${name}: ${reason.replaceAll(url, "embedded animation module")}`);
  } finally {
    // Import has evaluated the self-contained module; its namespace and clip
    // functions remain usable without retaining the source's Blob storage.
    if (browserModule) URL.revokeObjectURL(url);
  }
}

export function compileAnimationModule(moduleNamespace, { name = "embedded animation" } = {}) {
  const exported = Object.keys(moduleNamespace || {}).filter((key) => key !== "default");
  const unknown = exported.filter((key) => !ANIMATION_MODULE_EXPORTS.includes(key));
  if (unknown.length) {
    throw new Error(
      `${name}: unknown export${unknown.length === 1 ? "" : "s"} ${unknown.join(", ")} — `
      + `the renderer understands: ${ANIMATION_MODULE_EXPORTS.join(", ")}`
    );
  }
  if ("default" in (moduleNamespace || {})) {
    throw new Error(
      `${name}: a default export is not an animation-module export — use named exports `
      + `(${ANIMATION_MODULE_EXPORTS.join(", ")})`
    );
  }
  return { clips: normalizeAnimationClips(moduleNamespace?.clips) };
}

export async function compileAnimationSource(moduleSource, options = {}) {
  options.signal?.throwIfAborted();
  // Declaring an animation is what makes `deformTube` reachable, so the tube
  // runtime is fetched here, once, before any clip exists to evaluate. A
  // document with no animation never reaches this line and never pays for it.
  const [namespace] = await Promise.all([
    importAnimationModule(moduleSource, options),
    loadTubeDeformation()
  ]);
  options.signal?.throwIfAborted();
  return compileAnimationModule(namespace, options);
}

/** Compile a validated or raw schema-v9 sidecar's embedded animation.
 * Returns null when the document declares no animation. */
export async function loadSourceAnimation(sidecar, { name = "embedded animation", signal } = {}) {
  const animation = normalizeSourceAnimation(sidecar?.animation);
  return animation ? compileAnimationSource(animation.source, { name, signal }) : null;
}

// Validate loaded clips against the compiled tree at load time. Each failing
// clip is returned independently so clients can report all unresolved targets.
export function validateAnimationClips(THREE, meshData, clips) {
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
