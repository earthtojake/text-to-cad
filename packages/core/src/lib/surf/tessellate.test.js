// SURF tessellation correctness (design/surface-rendering.md R2).
//
// The decisive invariants: (1) the signed volume of the tessellated closed
// solid matches OCCT's VolumeProperties — wrong trims, cracks, flipped
// windings, or missing faces all break it; (2) per-face mesh area matches
// OCCT's SurfaceProperties — over/under-trimming breaks it; (3) every
// refined vertex lies exactly on its surface by construction, so chord
// error is bounded by the refinement criterion.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseSurf } from "./container.js";
import { tessellateComponent } from "./tessellate.js";

const here = dirname(fileURLToPath(import.meta.url));

function loadFixture(name) {
  const surfBytes = readFileSync(join(here, `fixtures/${name}.surf`));
  const truth = JSON.parse(readFileSync(join(here, `fixtures/${name}.truth.json`), "utf8"));
  const parsed = parseSurf(
    surfBytes.buffer.slice(surfBytes.byteOffset, surfBytes.byteOffset + surfBytes.byteLength),
  );
  return { ...parsed, truth, name };
}

const FIXTURES = [loadFixture("sun_gear"), loadFixture("mixed")];

function meshVolumeAndAreas(result) {
  const { positions, indices, faceRanges } = result;
  let volume = 0;
  const areas = new Map();
  for (const range of faceRanges) {
    let area = 0;
    for (let i = range.indexStart; i < range.indexStart + range.indexCount; i += 3) {
      const a = indices[i] * 3;
      const b = indices[i + 1] * 3;
      const c = indices[i + 2] * 3;
      const ax = positions[a];
      const ay = positions[a + 1];
      const az = positions[a + 2];
      const bx = positions[b];
      const by = positions[b + 1];
      const bz = positions[b + 2];
      const cx = positions[c];
      const cy = positions[c + 1];
      const cz = positions[c + 2];
      const ux = bx - ax;
      const uy = by - ay;
      const uz = bz - az;
      const vx = cx - ax;
      const vy = cy - ay;
      const vz = cz - az;
      const nx = uy * vz - uz * vy;
      const ny = uz * vx - ux * vz;
      const nz = ux * vy - uy * vx;
      area += Math.hypot(nx, ny, nz) / 2;
      volume += (ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx)) / 6;
    }
    areas.set(range.ord, (areas.get(range.ord) ?? 0) + area);
  }
  return { volume, areas };
}

for (const fixture of FIXTURES) {
  test(`${fixture.name}: tessellated volume matches OCCT within 0.5%`, () => {
    const result = tessellateComponent(fixture.index, fixture.floats);
    const { volume } = meshVolumeAndAreas(result);
    const truthVolume = fixture.truth.volume;
    const error = Math.abs(Math.abs(volume) - truthVolume) / truthVolume;
    assert.ok(
      error < 5e-3,
      `mesh volume ${volume} vs OCCT ${truthVolume} (${(error * 100).toFixed(2)}%)`,
    );
    // Orientation: outward normals give POSITIVE signed volume.
    assert.ok(volume > 0, `signed volume ${volume} is negative — windings flipped`);
  });

  test(`${fixture.name}: per-face mesh area matches OCCT within 1%`, () => {
    const result = tessellateComponent(fixture.index, fixture.floats);
    const { areas } = meshVolumeAndAreas(result);
    let failures = 0;
    for (const [ordString, truthArea] of Object.entries(fixture.truth.faceAreas)) {
      const ord = Number(ordString);
      const meshArea = areas.get(ord) ?? 0;
      const relative = Math.abs(meshArea - truthArea) / Math.max(truthArea, 1e-9);
      if (relative > 1e-2) {
        failures += 1;
        if (failures <= 5) {
          console.error(`  face ${ord}: mesh ${meshArea.toFixed(4)} vs OCCT ${truthArea.toFixed(4)}`);
        }
      }
    }
    assert.equal(failures, 0, `${failures} faces off by >1% area`);
  });

  test(`${fixture.name}: edges polyline with finite points and known classes`, () => {
    const result = tessellateComponent(fixture.index, fixture.floats);
    assert.ok(result.edges.length > 0);
    const classes = new Set(result.edges.map((edge) => edge.visibilityClass));
    for (const cls of classes) {
      assert.ok(
        ["feature", "tangent", "seam", "boundary", "nonManifold", "degenerate", "unknown"].includes(cls),
        cls,
      );
    }
    for (const edge of result.edges) {
      assert.ok(edge.polyline.length >= 6);
      for (const value of edge.polyline) assert.ok(Number.isFinite(value));
    }
  });
}
