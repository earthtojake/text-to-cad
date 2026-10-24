#!/usr/bin/env node
// Bake the shared reflection environment: the CAD Viewer's neutral studio (core's
// `createStudioEnvironmentScene` at its defaults, the one an authored finish reflected) as a
// Radiance HDR equirectangular image, which the engine ships (`cadgen/engine/render/studio.hdr`,
// served at `GET /api/look/environment`) and both renderers light an engine document's regular
// modes with: the viewer through PMREM, the OCCT prototype through its cube map.
//
//   node scripts/look/bake-environment.mjs [OUT.hdr]
//
// Each pixel is the studio's radiance along its direction, averaged over SAMPLES x SAMPLES rays
// cast through the studio's own meshes (the sweep's radiance by elevation and every card, with
// their vertex colours interpolated as a rasterizer would), so the image is that scene as a
// PMREM's cube camera sees it. Orientation, in the document's frame (Z up): rows run from +Z
// (the top row) to -Z; columns run once around +Z from -X through +Y, +X and -Y. A pixel is
// stored as RGBE and decoded as three's HDRLoader decodes it: `m / 255 * 2 ** (e - 128)`.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as THREE from "three";
import { acceleratedRaycast, computeBoundsTree } from "three-mesh-bvh";
import { createStudioEnvironmentScene } from "../../packages/core/src/common/environmentMap.js";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = process.argv[2] || path.join(REPO, "packages/cadgen/src/cadgen/engine/render/studio.hdr");
const WIDTH = 512;
const HEIGHT = 256;
const SAMPLES = 3;

THREE.Mesh.prototype.raycast = acceleratedRaycast;

/** The direction of a point of the image (`u`, `v` in 0..1 from its left and top edges). */
export function environmentDirection(u, v, target = new THREE.Vector3()) {
  const azimuth = (0.5 - u) * 2 * Math.PI;
  const elevation = (0.5 - v) * Math.PI;
  return target.set(Math.cos(azimuth) * Math.cos(elevation), Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation));
}

function radianceOf(hit) {
  const material = hit.object.material;
  const color = material.color.clone();
  if (material.vertexColors) {
    const colors = hit.object.geometry.getAttribute("color");
    const position = hit.object.geometry.getAttribute("position");
    const { a, b, c } = hit.face;
    const local = hit.object.worldToLocal(hit.point.clone());
    const corners = [a, b, c].map(index => new THREE.Vector3().fromBufferAttribute(position, index));
    const weights = new THREE.Triangle(...corners).getBarycoord(local, new THREE.Vector3());
    const vertex = new THREE.Color(0, 0, 0);
    [a, b, c].forEach((index, at) => vertex.add(new THREE.Color().fromBufferAttribute(colors, index).multiplyScalar(weights.getComponent(at))));
    color.multiply(vertex);
  }
  return color;
}

function bake() {
  const scene = createStudioEnvironmentScene({});
  scene.updateMatrixWorld(true);
  const meshes = [];
  scene.traverse((object) => {
    if (!object.isMesh) return;
    object.geometry.boundsTree = computeBoundsTree.call(object.geometry);
    meshes.push(object);
  });
  const raycaster = new THREE.Raycaster();
  raycaster.firstHitOnly = true;
  const origin = new THREE.Vector3();
  const direction = new THREE.Vector3();
  const pixels = new Float32Array(WIDTH * HEIGHT * 3);
  for (let row = 0; row < HEIGHT; row += 1) {
    for (let column = 0; column < WIDTH; column += 1) {
      const sum = [0, 0, 0];
      for (let i = 0; i < SAMPLES; i += 1) {
        for (let j = 0; j < SAMPLES; j += 1) {
          environmentDirection((column + (j + 0.5) / SAMPLES) / WIDTH, (row + (i + 0.5) / SAMPLES) / HEIGHT, direction);
          raycaster.set(origin, direction);
          const hits = raycaster.intersectObjects(meshes, false);
          const color = hits.length ? radianceOf(hits[0]) : scene.background;
          sum[0] += color.r;
          sum[1] += color.g;
          sum[2] += color.b;
        }
      }
      const at = (row * WIDTH + column) * 3;
      for (let channel = 0; channel < 3; channel += 1) pixels[at + channel] = sum[channel] / (SAMPLES * SAMPLES);
    }
  }
  return pixels;
}

/** One pixel as RGBE, the exponent chosen so the largest channel's mantissa fits 255. */
function rgbe(r, g, b, out, at) {
  const largest = Math.max(r, g, b);
  if (!(largest > 1e-30)) { out.fill(0, at, at + 4); return; }
  const exponent = Math.ceil(Math.log2(largest));
  const scale = 255 / 2 ** exponent;
  out[at] = Math.min(255, Math.round(r * scale));
  out[at + 1] = Math.min(255, Math.round(g * scale));
  out[at + 2] = Math.min(255, Math.round(b * scale));
  out[at + 3] = exponent + 128;
}

/** A scanline in the new run-length encoding: its four channels one after another, each in runs. */
function encodeScanline(line, width) {
  const bytes = [2, 2, width >> 8, width & 255];
  for (let channel = 0; channel < 4; channel += 1) {
    const values = Array.from({ length: width }, (_, x) => line[x * 4 + channel]);
    let at = 0;
    while (at < width) {
      let run = 1;
      while (at + run < width && run < 127 && values[at + run] === values[at]) run += 1;
      if (run >= 3) {
        bytes.push(128 + run, values[at]);
        at += run;
        continue;
      }
      let literal = 0;
      while (at + literal < width && literal < 128) {
        const next = at + literal;
        if (next + 2 < width && values[next] === values[next + 1] && values[next] === values[next + 2]) break;
        literal += 1;
      }
      bytes.push(literal, ...values.slice(at, at + literal));
      at += literal;
    }
  }
  return bytes;
}

const pixels = bake();
const encoded = new Uint8Array(WIDTH * HEIGHT * 4);
for (let index = 0; index < WIDTH * HEIGHT; index += 1) {
  rgbe(pixels[index * 3], pixels[index * 3 + 1], pixels[index * 3 + 2], encoded, index * 4);
}
const body = [];
for (let row = 0; row < HEIGHT; row += 1) body.push(...encodeScanline(encoded.subarray(row * WIDTH * 4, (row + 1) * WIDTH * 4), WIDTH));
const header = "#?RADIANCE\n# cadgen: the CAD Viewer's neutral studio (createStudioEnvironmentScene, its defaults), "
  + "rows +Z to -Z, columns -X, +Y, +X, -Y\nFORMAT=32-bit_rle_rgbe\n\n"
  + `-Y ${HEIGHT} +X ${WIDTH}\n`;
fs.writeFileSync(OUT, Buffer.concat([Buffer.from(header, "ascii"), Buffer.from(body)]));
let largest = 0;
for (const value of pixels) largest = Math.max(largest, value);
console.log(`wrote ${OUT}: ${WIDTH}x${HEIGHT}, ${fs.statSync(OUT).size} bytes, brightest ${largest.toFixed(3)}`);
