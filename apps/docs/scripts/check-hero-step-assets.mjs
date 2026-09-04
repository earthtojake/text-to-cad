// The CI gate for the hero showcase assets: the committed render package and
// sidecar under public/hero/ must still satisfy the contracts the hero page
// consumes through cadgen-js — the .surf container format the client
// tessellates, a kinematics section that compiles into a step-module
// definition, and copied animation clip text. A cadgen schema bump that
// regenerates these formats fails here instead of silently breaking the
// production render. Refresh with scripts/sync-hero-step-assets.mjs.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SURF_MAGIC, SURF_VERSION } from "../../../packages/cadgen-js/src/lib/surf/container.js";
import { stepModuleFromKinematics } from "../../../packages/cadgen-js/src/common/kinematicsModule.js";

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const heroPackageDir = path.join(docsRoot, "public/hero/planetary");
const heroSidecarPath = path.join(docsRoot, "public/hero/planetary_gear_assembly.step.json");

const descriptor = JSON.parse(
  fs.readFileSync(path.join(heroPackageDir, "assembly.json"), "utf8"),
);
const components = Object.entries(descriptor.components || {});
assert.ok(components.length > 0, "Hero render package descriptor lists no components");

for (const [cid, entry] of components) {
  const surfPath = path.join(heroPackageDir, String(entry?.surf || ""));
  assert.ok(entry?.surf && fs.existsSync(surfPath), `Hero component ${cid} is missing its .surf`);
  const header = fs.readFileSync(surfPath).subarray(0, 8);
  assert.equal(header.readUInt32LE(0), SURF_MAGIC, `${surfPath} is not a SURF container`);
  assert.equal(
    header.readUInt32LE(4),
    SURF_VERSION,
    `${surfPath} is SURF v${header.readUInt32LE(4)}; cadgen-js expects v${SURF_VERSION}`,
  );
}

const sidecar = JSON.parse(fs.readFileSync(heroSidecarPath, "utf8"));
assert.ok(
  stepModuleFromKinematics(sidecar.kinematics),
  "Hero sidecar kinematics no longer compile into a step-module definition",
);
assert.ok(
  !("animation" in sidecar),
  "Hero sidecar still carries an animation section; choreography is the render module beside the document",
);
const heroRenderModulePath = path.join(docsRoot, "public/hero/planetary_gear_assembly.step.js");
assert.ok(fs.existsSync(heroRenderModulePath), `Hero render module missing: ${heroRenderModulePath}`);
assert.ok(
  fs.readFileSync(heroRenderModulePath, "utf8").includes("meshCycle"),
  "Hero render module does not declare the meshCycle clip",
);

console.log(`Hero STEP assets are current: ${components.length} components, kinematics + clips OK.`);
