// Embedded source-animation compiler. A schema-v9 STEP sidecar may carry one
// self-contained JavaScript module in `animation.source`. Clients import that
// text in their own realm; there is no adjacent `.step.js` discovery or fetch.

import { normalizeAnimationClips, evaluateAnimationClip } from "./animationRuntime.js";
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
  const url = `data:text/javascript;base64,${base64Utf8(text)}`;
  try {
    return await import(/* webpackIgnore: true */ /* @vite-ignore */ url);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`${name}: ${reason}`);
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
  const namespace = await importAnimationModule(moduleSource, options);
  return compileAnimationModule(namespace, options);
}

/** Compile a validated or raw schema-v9 sidecar's embedded animation.
 * Returns null when the document declares no animation. */
export async function loadSourceAnimation(sidecar, { name = "embedded animation" } = {}) {
  const animation = normalizeSourceAnimation(sidecar?.animation);
  return animation ? compileAnimationSource(animation.source, { name }) : null;
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
