// The engine's look (`xbfLook.js`) as the engine serves it: `__fixtures__/look.json` is
// `GET /api/look`'s answer, which cadgen's tests hold to `render/look.py`. What it says, the image
// its environment is, the rig it lights an engine document with, what a surface wears by it (X-ray's
// colour-only model apart), and that what it says of edges, the palette and the modes is what the
// viewer's own modes draw.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { resolveCadEdgeSettings } from "../../common/cadInk.js";
import { resolveViewSettings } from "../../common/viewSettings.js";
import { isSceneRig } from "../viewer/sceneRig.js";
import {
  XBF_ENVIRONMENT_ROTATION, decodeRadiance, fetchXbfLook, parseXbfLook, xbfLookHighlight, xbfLookRig, xbfLookSurface, xbfLookXray,
  xbfLookXrayRig, xbfLookXraySurface
} from "./xbfLook.js";

const SERVED = JSON.parse(fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "__fixtures__", "look.json"), "utf8"));
const near = (actual, expected, tolerance = 1e-9) => assert.ok(Math.abs(actual - expected) < tolerance, `${actual} is not ${expected}`);

/** A 2 x 2 Radiance image, its top row run-length encoded the new way and its bottom row flat. */
function tinyRadiance() {
  const header = new TextEncoder().encode("#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 2 +X 2\n");
  // Top row: two pixels of (255, 0, 0, e 131), 8, 0, 0, a run of each channel. Bottom: flat, 1, 1, 1 then 0.
  const top = [2, 2, 0, 2, 130, 255, 130, 0, 130, 0, 130, 131];
  const bottom = [255, 255, 255, 128, 0, 0, 0, 0];
  return new Uint8Array([...header, ...top, ...bottom]).buffer;
}

test("the look as served: every field read, frozen; another version or a missing field refused by name", () => {
  const look = parseXbfLook(SERVED);
  assert.equal(Object.isFrozen(look), true);
  assert.deepEqual([look.backdrop, look.colourPower, look.brdf, look.tone, look.exposure], ["#f0f4f9", 2, "occt", "clamp", 0]);
  assert.deepEqual(look.lights.map(light => [light.name, light.direction, light.intensity]), [["key", [-0.35, 0.55, -1], 4]]);
  assert.deepEqual(look.environment, { url: "/api/look/environment", intensity: 0.5 });
  assert.deepEqual(look.plain, { metallic: 0, roughness: 0.5, ior: 1.5 });
  assert.deepEqual(look.modes.xray, { faces: "lit", edges: "all", opacity: 0.22, palette: false });
  assert.deepEqual([look.xray.ambient, look.xray.specular, look.xray.shininess], [0.5, 0.08, 0.35]);
  assert.deepEqual(look.xray.lights.map(light => [light.name, light.direction, light.intensity]),
    [["key", [-0.35, 0.55, -1], 1], ["fill", [0.6, 0.2, -0.3], 1]]);
  assert.throws(() => parseXbfLook({ ...SERVED, version: 3 }), /version 3; this viewer reads 4/);
  assert.throws(() => parseXbfLook({ ...SERVED, xray: { ...SERVED.xray, lights: [] } }), /no xray.lights/);
  assert.throws(() => parseXbfLook({ ...SERVED, lights: [] }), /no lights/);
  assert.throws(() => parseXbfLook({ ...SERVED, environment: null }), /no environment/);
  assert.throws(() => parseXbfLook({ ...SERVED, backdrop: "blue" }), /backdrop is a #rrggbb colour/);
  assert.throws(() => parseXbfLook({ ...SERVED, brdf: "phong" }), /brdf is one of occt, not "phong"/);
});

test("the environment's image: RGBE decoded as the engine decodes it, the bottom row first, fetched with its look", async () => {
  const { width, height, data } = decodeRadiance(tinyRadiance());
  assert.deepEqual([width, height], [2, 2]);
  assert.deepEqual([...data.subarray(0, 4)], [1, 1, 1, 1], "the image's bottom row comes first: 255 / 255 * 2 ** 0");
  assert.deepEqual([...data.subarray(8, 12)], [8, 0, 0, 1], "its top row last: 255 / 255 * 2 ** 3");
  const asked = [];
  const fetch = async (url) => {
    asked.push(url);
    return url.endsWith("/api/look") ? new Response(JSON.stringify(SERVED)) : new Response(tinyRadiance());
  };
  const look = await fetchXbfLook("http://127.0.0.1:9", { fetch });
  assert.deepEqual(asked, ["http://127.0.0.1:9/api/look", "http://127.0.0.1:9/api/look/environment"]);
  assert.equal(look.environment.image.width, 2);
  const missing = async url => (url.endsWith("/api/look") ? new Response(JSON.stringify(SERVED)) : new Response("", { status: 404 }));
  await assert.rejects(fetchXbfLook("http://127.0.0.1:9", { fetch: missing }), /environment: the engine answered 404/);
});

test("the rig: the key at the look's intensity, from where it comes; the image at its intensity, in the document's frame", () => {
  const parsed = parseXbfLook(SERVED);
  const look = { ...parsed, environment: { ...parsed.environment, image: decodeRadiance(tinyRadiance()) } };
  const rig = xbfLookRig(look);
  assert.equal(isSceneRig(rig), true);
  assert.equal(rig.ambient, null, "the environment is the only light besides the key");
  const [key] = rig.lights;
  near(key.intensity, 4);
  const length = Math.hypot(0.35, 0.55, 1);
  [0.35 / length, -0.55 / length, 1 / length].forEach((value, at) => near(key.towards[at], value));
  assert.deepEqual([rig.environment.width, rig.environment.height, rig.environment.intensity], [2, 2, 0.5]);
  assert.equal(rig.environment.data, look.environment.image.data, "the image's own pixels, shared by every rig of the look");
  assert.deepEqual(rig.environment.rotation, XBF_ENVIRONMENT_ROTATION);
  assert.deepEqual([rig.exposure, rig.toneCurve], [1, "clamp"]);
  assert.equal(xbfLookRig(parsed).environment, null, "a look read without its image lights with none");
});

test("a surface under the look: colours squared, nothing graded, the plain finish and no lift, OCCT's surface model", () => {
  const surface = xbfLookSurface(parseXbfLook(SERVED));
  assert.equal(surface.colorPower, 2);
  assert.equal(surface.brdf, "occt");
  assert.deepEqual({ ...surface.materialSettings }, { saturation: 1, contrast: 1, brightness: 1, tintStrength: 0, roughness: 0.5,
    metalness: 0, clearcoat: 0, clearcoatRoughness: 0, envMapIntensity: 1, emissiveIntensity: 0 });
});

test("X-ray: the colour-only model, its ambient and lights at pi times their radiance, no environment, three's surface model", () => {
  const parsed = parseXbfLook(SERVED);
  const look = { ...parsed, environment: { ...parsed.environment, image: decodeRadiance(tinyRadiance()) } };
  const rig = xbfLookXrayRig(look);
  assert.equal(isSceneRig(rig), true);
  assert.notEqual(rig.id, xbfLookRig(look).id);
  assert.deepEqual(rig.ambient, { color: "#ffffff", intensity: Math.PI * 0.5 });
  assert.equal(rig.environment, null, "no image-based light, the image read or not");
  assert.deepEqual(rig.lights.map(light => light.name), ["key", "fill"]);
  for (const [light, direction] of [[rig.lights[0], [-0.35, 0.55, -1]], [rig.lights[1], [0.6, 0.2, -0.3]]]) {
    near(light.intensity, Math.PI);
    const length = Math.hypot(...direction);
    direction.forEach((value, at) => near(light.towards[at], -value / length));
  }
  assert.deepEqual([rig.exposure, rig.toneCurve], [1, "clamp"]);
  assert.equal(rig.blend, "linear", "its see-through surfaces blended in linear light, as OCCT's frame buffer blends them");
  assert.equal(xbfLookRig(look).blend, undefined, "the regular modes' rig blends as three does");
  const surface = xbfLookXraySurface(look);
  const highlight = xbfLookHighlight(0.08, 0.35);
  assert.deepEqual([surface.colorPower, surface.brdf, surface.finishes], [2, null, false]);
  assert.deepEqual({ ...surface.materialSettings }, { saturation: 1, contrast: 1, brightness: 1, tintStrength: 0,
    roughness: highlight.roughness, metalness: 0, specularIntensity: highlight.specularIntensity, clearcoat: 0, clearcoatRoughness: 0,
    envMapIntensity: 0, emissiveIntensity: 0 });
  // Phong's exponent 128 * 0.35 is a GGX slope of 2 / 46.8: roughness its fourth root.
  near(highlight.roughness, (2 / 46.8) ** 0.25);
  assert.ok(highlight.specularIntensity > 0 && highlight.specularIntensity < 1);
  assert.equal(xbfLookXray({ surface: { style: "shaded", opacity: 0.22 } }), true);
  for (const other of [{ surface: { style: "shaded", opacity: 1 } }, { surface: null }, null]) assert.equal(xbfLookXray(other), false);
});

test("what the look says of edges, the palette and each mode is what the viewer's modes draw", () => {
  const look = parseXbfLook(SERVED);
  const ink = resolveCadEdgeSettings();
  for (const [line, colour] of Object.entries(look.edges.colours)) assert.equal(ink.classes[line].color, colour, line);
  assert.deepEqual(resolveViewSettings({ mode: "parts" }).surfaces.colors, [...look.palette]);
  assert.equal(look.fill, look.palette[0]);
  const faces = { shaded: "lit", hidden: "backdrop", off: "none" };
  for (const [mode, recipe] of Object.entries(look.modes)) {
    const view = resolveViewSettings({ mode });
    assert.deepEqual({ faces: faces[view.surfaces.style], edges: view.edges.enabled ? view.edges.visibility : "none",
      opacity: view.surfaces.opacity, palette: view.surfaces.colorMode === "by-part" }, recipe, mode);
  }
});
