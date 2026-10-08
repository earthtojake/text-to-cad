// The CI gate for the hero showcase assets: the committed render package under
// public/hero/planetary/ must still satisfy the contracts the hero page consumes
// through @text-to-cad/core — each component's mesh, as cadgen made it, readable
// as that component's mesh at the tolerances the hero draws; an articulation the
// player poses (controls and joints over the tree's occurrences); and the baked
// animation with the clip the hero plays. A cadgen format bump that regenerates
// these fails here instead of silently breaking the production render. Refresh
// with scripts/sync-hero-step-assets.mjs.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as THREE from "three";
import { packageSourceFromBaseUrl } from "@text-to-cad/core/common/source.js";
import { decodeComponentTessellation } from "@text-to-cad/core/lib/surf/tessellationCache.js";
import { articulationControls, jointDeltas, openingControlValues } from "@text-to-cad/core/common/articulation.js";
import { loadSourceAnimation } from "@text-to-cad/core/common/animationRuntime.js";

const docsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const heroPackageDir = path.join(docsRoot, "public/hero/planetary");

const descriptor = JSON.parse(
  fs.readFileSync(path.join(heroPackageDir, "assembly.json"), "utf8"),
);
const components = Object.entries(descriptor.components || {});
assert.ok(components.length > 0, "Hero render package descriptor lists no components");

// The mesh URLs the hero reads, resolved the way the page resolves them.
const { package: heroPackage } = packageSourceFromBaseUrl("/hero/planetary", descriptor);
for (const [cid, entry] of components) {
  const meshPath = path.join(docsRoot, "public", heroPackage.meshUrls[cid]);
  assert.ok(fs.existsSync(meshPath), `Hero component ${cid} is missing its mesh (${meshPath})`);
  const decoded = decodeComponentTessellation(new Uint8Array(fs.readFileSync(meshPath)), {
    surfaceInput: entry.surfaceInput, surfaceObject: entry.surfaceObject, tessellation: {},
  });
  assert.ok(decoded, `${meshPath} is not component ${cid}'s mesh at the default tolerances in the current mesh format`);
  assert.ok(decoded.component.indices.length > 0, `${meshPath} draws no triangles`);
}

const articulation = JSON.parse(fs.readFileSync(path.join(heroPackageDir, "articulation.json"), "utf8"));
assert.ok(articulationControls(articulation).length > 0, "Hero articulation declares no controls");
const occurrenceIds = new Set((descriptor.occurrences || []).map((occurrence) => occurrence.id));
for (const [joint, carried] of Object.entries(articulation.carries || {})) {
  for (const occurrenceId of carried) {
    assert.ok(occurrenceIds.has(occurrenceId), `Hero articulation joint ${joint} carries ${occurrenceId}, which the tree does not list`);
  }
}
assert.equal(jointDeltas(THREE, articulation, openingControlValues(articulation)).size, (articulation.joints || []).length,
  "Hero articulation does not evaluate to one delta per joint");

const animation = await loadSourceAnimation({ animation: JSON.parse(fs.readFileSync(path.join(heroPackageDir, "animation.json"), "utf8")) });
assert.ok(animation?.clips?.meshCycle, "Hero animation does not declare the meshCycle clip");

console.log(`Hero STEP assets are current: ${components.length} components, articulation + clips OK.`);
