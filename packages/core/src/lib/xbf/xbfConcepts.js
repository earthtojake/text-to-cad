// The GSL concepts of an engine document, drawn in its scene.
//
// A part of a document may name a concept (its prototype's `concept`: `{ gsl, role, digest, values }`,
// the engine's `declarations.concept_value`). A part whose role is `body` has no shape of its own and
// IS the concept; one whose role is `baked` is an exact part made from it, the concept its other
// representation. Either way the concept is drawn as its field (`../render/fieldScene.js`, the scene a
// `.gsl` shown alone is drawn by), placed where the part's instance stands: an opaque surface that
// writes its depth, so the frame's depth buffer hides fields and exact parts behind each other with
// no pass of their own. It is lit as they are (the field's `lit`): by the stage's lights and
// environment, wearing what the scene's look gives a part with no finish of its own (`look`), and
// drawn see-through in X-ray: the first surface along each ray, where an exact part shows its far
// faces too.
//
// A field has no triangles for a ray to meet, so a pick marches it: every shown field along the
// pointer's ray, each in its own frame, in one draw of one pixel that answers how far along the ray
// the nearest surface is and whose it is. The scene holds that against its triangles' hit.

import { buildFieldScene, FIELD_CLIP_GLSL, fieldClipUniforms, writeFieldClip } from "../render/fieldScene.js";
import { SURFACE_BRDFS } from "../viewer/surfaceBrdf.js";
import { resolveMaterialFillBaseColor, shapeSourceColor } from "../viewer/surfaceMaterials.js";

/** How a baked part is shown: its exact body, the concept it was made from, or both. */
export const XBF_REPRESENTATIONS = Object.freeze(["exact", "concept", "both"]);

/** What a document's fields are kept by: the concept's file and the digest of its text. */
export function xbfConceptKey(concept) {
  return `${concept?.gsl || ""}\n${concept?.digest || ""}`;
}

/** The concepts a structure's prototypes name, one of each (`xbfConceptKey`). */
export function xbfStructureConcepts(structure) {
  const found = new Map();
  for (const prototype of structure?.prototypes || []) {
    if (prototype?.concept?.gsl) found.set(xbfConceptKey(prototype.concept), prototype.concept);
  }
  return [...found.values()];
}

const clamp01 = (value, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(Math.max(number, 0), 1) : fallback;
};

const PICK_VERTEX = "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }";

// The pick's own half, after a concept's library: the field marched along one ray given in the
// concept's frame. Each writes how far the surface is and which concept it is; the nearest wins by depth.
const PICK_FRAGMENT = `
uniform vec3 uOrigin;
uniform vec3 uDirection;
uniform vec3 uBoxMin;
uniform vec3 uBoxMax;
uniform float uPixel;
uniform float uFar;
uniform float uConcept;
void main() {
  vec3 a = (uBoxMin - uOrigin) / uDirection;
  vec3 b = (uBoxMax - uOrigin) / uDirection;
  vec3 lower = min(a, b);
  vec3 upper = max(a, b);
  float tEntry = max(max(max(lower.x, lower.y), lower.z), 0.0);
  float tExit = min(min(upper.x, upper.y), upper.z);
  if (tExit <= tEntry) { discard; }
  // A section cuts what is picked as it cuts what is drawn: the cut's own face where it is through the solid.
  vec3 cap;
  if (fieldClipped(uOrigin, uDirection, tEntry, tExit, cap)) { discard; }
  float t = -1.0;
#ifdef FIELD_CAPS
  if (cap != vec3(0.0) && gsl_field(uOrigin + uDirection * tEntry).distance_ < 0.0) { t = tEntry; }
#endif
  if (t < 0.0) {
    gsl_hit hit = gsl_march(uOrigin, uDirection, tEntry, tExit, uPixel, 1.0, 1.0, vec4(0.0));
    if (!hit.hit) { discard; }
    t = hit.t;
  }
  gl_FragDepth = clamp(t / uFar, 0.0, 1.0);
  gl_FragColor = vec4(t, uConcept, 0.0, 1.0);
}
`;

// A lit concept's colour: under the pointer, and selected.
const HOVERED = [0.62, 0.78, 0.98];
const SELECTED = [0.36, 0.62, 0.98];
// How fine the pick's march is, in the scene's unit, and the farthest it answers.
const PICK_PIXEL = 0.02;
const PICK_FAR = 1e6;

/**
 * The concepts of a document's instances, added to its scene.
 *
 * @param {typeof import("three")} THREE
 * @param {{ structure: object, fields?: Map<string, { payload: object, textures: object }> }} document
 * @param {{ index: number, prototype: object, instance: object, group: object, carrier: object }[]} instances
 *   The scene's instances: each concept goes under its instance's `carrier`, standing where `group` does.
 */
export function createXbfConcepts(THREE, document, instances) {
  const fields = document.fields || new Map();
  const held = new Map();
  const rgb = rgba => (Array.isArray(rgba) ? new THREE.Vector3(Number(rgba[0]) || 0, Number(rgba[1]) || 0, Number(rgba[2]) || 0) : null);
  for (const entry of instances) {
    const concept = entry.prototype.concept;
    if (!concept?.gsl) continue;
    const named = entry.prototype.name || entry.instance.path;
    const loaded = fields.get(xbfConceptKey(concept));
    if (!loaded) {
      // An exact part is drawn without its concept; a part that IS its concept cannot be.
      if (concept.role === "body") throw new Error(`${named} is the concept ${concept.gsl}, and its field was not read`);
      continue;
    }
    const field = buildFieldScene(THREE, loaded.payload, loaded.textures || {}, { lit: true });
    for (const [name, value] of Object.entries(concept.values || {})) {
      if (!field.setParameter(name, Number(value))) {
        field.dispose();
        throw new Error(`${named} gives ${concept.gsl} the value ${name}=${value}, and the concept has no ranged name ${name}: `
          + "only a name with a range is set where it is drawn");
      }
    }
    const holder = new THREE.Group();
    holder.name = `${entry.instance.path} concept`;
    holder.matrixAutoUpdate = false;
    holder.matrix.copy(entry.group.matrix);
    holder.userData.xbfInstance = entry.index;
    holder.add(field.object3D);
    entry.carrier.add(holder);
    const drawn = field.object3D.children[0];
    const surface = drawn.material.uniforms.uSurface.value;
    const [x0, y0, z0, x1, y1, z1] = loaded.payload.region;
    held.set(entry.index, {
      index: entry.index, entry, concept, field, holder, drawn, surface, name: named, role: concept.role,
      payload: loaded.payload,
      // Each body's colour as the field gives it, and as the look has it worn (`look`).
      palette: surface.map(colour => colour.clone()),
      colours: surface.map(colour => colour.clone()),
      // The part's own colour, linear, where the document gives it one: its first body's.
      own: rgb(entry.instance.color || entry.prototype.color),
      box: new THREE.Box3(new THREE.Vector3(x0, y0, z0), new THREE.Vector3(x1, y1, z1)),
      // A baked part opens as its exact body; a concept that is the part is all there is to show.
      representation: concept.role === "baked" ? "exact" : "concept",
      shown: true, pick: null
    });
    holder.visible = concept.role === "body";
  }

  // --- the pick ------------------------------------------------------------------------------
  let renderer = null;
  let target = null;
  const pickScene = new THREE.Scene();
  const pickCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const triangle = new THREE.BufferGeometry();
  triangle.setAttribute("position", new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
  let ordinal = 0;
  const byOrdinal = [];
  for (const item of held.values()) {
    // The renderer the scene is drawn by is the one a pick draws with: there is one context.
    const before = item.drawn.onBeforeRender;
    item.drawn.onBeforeRender = (...given) => { renderer = given[0]; before(...given); };
    ordinal += 1;
    byOrdinal[ordinal] = item;
    item.pick = new THREE.Mesh(triangle, new THREE.ShaderMaterial({
      name: "concept pick", vertexShader: PICK_VERTEX,
      fragmentShader: `precision highp sampler3D;\n${item.payload.entry?.field === "gsl_field" ? "#define FIELD_CAPS\n" : ""}${item.payload.code}\n${FIELD_CLIP_GLSL}\n${PICK_FRAGMENT}`,
      // The concept's own block of time and sliders, and its textures: the field picked is the field drawn.
      uniformsGroups: item.drawn.material.uniformsGroups,
      uniforms: {
        ...Object.fromEntries(Object.entries(item.drawn.material.uniforms).filter(([, uniform]) => uniform.value?.isTexture)),
        uOrigin: { value: new THREE.Vector3() }, uDirection: { value: new THREE.Vector3() },
        uBoxMin: { value: item.box.min.clone() }, uBoxMax: { value: item.box.max.clone() },
        uPixel: { value: PICK_PIXEL }, uFar: { value: PICK_FAR }, uConcept: { value: ordinal },
        ...fieldClipUniforms(THREE)
      },
      depthTest: true, depthWrite: true, toneMapped: false, blending: THREE.NoBlending
    }));
    item.pick.frustumCulled = false;
    pickScene.add(item.pick);
  }
  // A concept's world matrix as it stands now: its holder's matrix is set by hand, so it is worked out here.
  const placedNow = (item) => {
    const { holder } = item;
    holder.parent.updateWorldMatrix(true, false);
    holder.matrixWorld.multiplyMatrices(holder.parent.matrixWorld, holder.matrix);
  };
  const visible = item => item.shown && (item.role === "body" || item.representation !== "exact");
  const inverse = new THREE.Matrix4();
  const texel = new Float32Array(4);
  const clearColor = new THREE.Color();
  const last = { key: "", at: 0, hit: null };
  let clipPlanes = [];
  let inked = { hovered: new Set(), selected: new Set() };
  const paint = (item) => {
    const colour = inked.selected.has(item.index) ? SELECTED : inked.hovered.has(item.index) ? HOVERED : null;
    item.surface.forEach((value, at) => (colour ? value.set(...colour) : value.copy(item.colours[at])));
  };
  const asColor = new THREE.Color();

  const concepts = {
    /** Whether the document draws any concept. */
    any: held.size > 0,
    /** Each concept drawn: its instance's index, the part's name, its role and the names it lets the view set. */
    list: () => [...held.values()].map(item => ({ index: item.index, name: item.name, role: item.role,
      file: item.concept.gsl.split("/").pop(),
      representation: item.representation, parameters: item.field.parameters })),
    has: index => held.has(index),
    parameterValue: (index, name) => held.get(index)?.field.parameterValue(name),
    setParameter(index, name, value) {
      last.key = "";
      return Boolean(held.get(index)?.field.setParameter(name, value));
    },
    representation: index => held.get(index)?.representation || null,
    /** Show a baked part as its exact body, its concept or both. False where it changes nothing. */
    setRepresentation(index, value) {
      const item = held.get(index);
      if (!item || item.role !== "baked" || !XBF_REPRESENTATIONS.includes(value) || item.representation === value) return false;
      item.representation = value;
      item.holder.visible = visible(item);
      last.key = "";
      return true;
    },
    /** Whether an instance's exact body is drawn: not where a baked part is shown as its concept. */
    exactShown(index) {
      const item = held.get(index);
      return !item || item.role !== "baked" || item.representation !== "concept";
    },
    /** An instance shown or not (hidden, or dimmed by an isolation: a field is not drawn see-through). */
    show(index, shown) {
      const item = held.get(index);
      if (!item || item.shown === shown) return;
      item.shown = shown;
      item.holder.visible = visible(item);
      last.key = "";
    },
    /** Whether any concept reads its clock: one that does is played with the document's motion, or by a clip of its own. */
    timed: [...held.values()].some(item => item.field.timed),
    /** Every concept's clock, in seconds. True when one moved. */
    setTime(seconds) {
      let moved = false;
      for (const item of held.values()) moved = item.field.setTime(seconds) || moved;
      if (moved) last.key = "";
      return moved;
    },
    /** A section's planes: every concept is cut by them as the exact parts are, and picked as cut. */
    setClipPlanes(planes) {
      clipPlanes = Array.isArray(planes) ? planes : [];
      for (const item of held.values()) item.field.setClipPlanes(clipPlanes);
      last.key = "";
    },
    /** Each concept back where its instance's placed group stands (a pose moved it). */
    pose() {
      for (const item of held.values()) item.holder.matrix.copy(item.entry.group.matrix);
      last.key = "";
    },
    /** The box of an instance's concept where it stands now, or null: only a part that is its concept has one of its own. */
    box(index) {
      const item = held.get(index);
      if (!item || item.role !== "body") return null;
      placedNow(item);
      return item.box.clone().applyMatrix4(item.holder.matrixWorld);
    },
    /** The concepts lit: under the pointer, and selected, by their instances' indices. */
    ink(hovered, selected) {
      inked = { hovered, selected };
      for (const item of held.values()) paint(item);
    },
    /**
     * What the concepts wear under the scene's look (`../viewer/surfaceLook.js`'s, as the scene hands it
     * to its exact parts): what a part with no finish of its own wears there. A body without a colour
     * (the field's first) takes the part's colour, else the look's fill, as an uncoloured part does;
     * the field's other bodies keep theirs as source colours; every colour is raised to the look's
     * power. The finish, the surface model, "Flat" and the opacity are the look's. Null: as built.
     */
    look(next = null) {
      const settings = next?.materialSettings || {};
      const power = Number(next?.colorPower) > 0 ? Number(next.colorPower) : 1;
      const forceFill = Boolean(next) && settings.overrideSourceColors === true;
      const model = next?.brdf ? SURFACE_BRDFS[next.brdf] : null;
      model?.prepare(THREE);
      for (const item of held.values()) {
        item.colours.forEach((colour, at) => {
          const source = at > 1 ? item.palette[at] : item.own;
          if (!next) { colour.copy(source || item.palette[at]); return; }
          const found = forceFill || !source
            ? resolveMaterialFillBaseColor(THREE, settings, settings.cycleColors === true ? item.index : 0)
            : shapeSourceColor(THREE, asColor.setRGB(source.x, source.y, source.z), settings);
          colour.set(found.r ** power, found.g ** power, found.b ** power);
        });
        item.field.setFinish(next ? {
          roughness: clamp01(settings.roughness), metalness: clamp01(settings.metalness),
          clearcoat: clamp01(settings.clearcoat), clearcoatRoughness: clamp01(settings.clearcoatRoughness),
          specularIntensity: settings.specularIntensity === undefined ? 1 : clamp01(settings.specularIntensity),
          envMapIntensity: Math.max(Number(settings.envMapIntensity) || 0, 0), lift: clamp01(settings.emissiveIntensity),
          flat: next.surface?.style === "flat", opacity: next.surface ? clamp01(next.surface.opacity, 1) : 1, model
        } : null);
        paint(item);
      }
    },
    /**
     * The nearest concept `ray` (the scene's coordinates) meets among those `reachable(index)` allows:
     * `{ index, distance, point }`, or null. Null too before the scene was first drawn.
     */
    hit(ray, reachable = () => true) {
      if (!renderer || !held.size) return null;
      const key = [...ray.origin.toArray(), ...ray.direction.toArray()].join();
      const now = performance.now();
      // One pointer event asks more than once (a press's reach, a resting pointer's): one draw answers them.
      if (key === last.key && now - last.at < 100) return last.hit;
      let any = false;
      for (const item of held.values()) {
        item.pick.visible = visible(item) && reachable(item.index);
        if (!item.pick.visible) continue;
        any = true;
        placedNow(item);
        inverse.copy(item.holder.matrixWorld).invert();
        writeFieldClip(THREE, item.pick.material.uniforms, clipPlanes, inverse);
        item.pick.material.uniforms.uOrigin.value.copy(ray.origin).applyMatrix4(inverse);
        item.pick.material.uniforms.uDirection.value.copy(ray.direction).transformDirection(inverse);
      }
      let hit = null;
      if (any) {
        target ||= new THREE.WebGLRenderTarget(1, 1, { type: THREE.FloatType, depthBuffer: true, generateMipmaps: false,
          minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
        const destination = renderer.getRenderTarget();
        const autoClear = renderer.autoClear;
        const alpha = renderer.getClearAlpha();
        renderer.getClearColor(clearColor);
        try {
          renderer.autoClear = true;
          renderer.setClearColor(0x000000, 0);
          renderer.setRenderTarget(target);
          renderer.render(pickScene, pickCamera);
          renderer.readRenderTargetPixels(target, 0, 0, 1, 1, texel);
        } finally {
          renderer.setClearColor(clearColor, alpha);
          renderer.autoClear = autoClear;
          renderer.setRenderTarget(destination);
        }
        const item = byOrdinal[Math.round(texel[1])];
        if (item) hit = { index: item.index, distance: texel[0], point: ray.at(texel[0], new THREE.Vector3()) };
      }
      Object.assign(last, { key, at: now, hit });
      return hit;
    },
    dispose() {
      for (const item of held.values()) {
        item.holder.removeFromParent();
        item.pick.material.dispose();
        item.field.dispose();
      }
      held.clear();
      triangle.dispose();
      target?.dispose();
      target = null;
      renderer = null;
    }
  };
  return concepts;
}
