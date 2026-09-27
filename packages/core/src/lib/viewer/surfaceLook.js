import { resolveMaterialFillBaseColor, shapeSourceColor } from "./surfaceMaterials.js";

// The viewer's surface LOOK over a scene somebody else authored: the Display
// tab's Surfaces section (style, colour mode, opacity) and the Inspect finish,
// applied to whatever lit materials hang under a root. It never rebuilds
// geometry and never forgets what was authored, so every setting is reversible
// and "Render + Original + Shaded + 100%" is the file exactly as written.
// Inspect keeps what identifies a part (its colour, maps and opacity) and
// replaces how it answers light, so two files read as one product under one rig.
//
// A look is plain data:
//   { materialSettings,     resolved display material settings
//                           (`resolveDisplayMaterialSettings`): fills, colour
//                           grading and the finish channels
//     authored: boolean,    true: keep each material's own finish, sidedness and
//                           source colours (photographic Render)
//     surface: { style: "shaded" | "flat", opacity } }
//
// Colour modes are the material settings' own: `overrideSourceColors` paints every
// part with a fill (one colour, or the palette cycled per mesh: in traversal
// order, or at the place a mesh names in `userData.cadFillIndex`); otherwise a
// source colour is kept and only a material marked
// `userData.cadSourceColor === false` takes the fill.

const clamp01 = (value, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(Math.max(number, 0), 1) : fallback;
};

function litMaterial(material) {
  return Boolean(material?.isMeshStandardMaterial);
}

function readAuthored(material) {
  return {
    color: material.color.clone(),
    opacity: material.opacity,
    transparent: material.transparent,
    depthWrite: material.depthWrite,
    side: material.side,
    vertexColors: material.vertexColors,
    map: material.map || null,
    glows: Boolean(material.emissiveMap) || (material.emissiveIntensity > 0 && material.emissive?.getHex?.() !== 0)
  };
}

// The viewer's Inspect surface is a physical material (it has a clear coat); most
// authored ones are plain standard materials, which have no such channel. So
// Inspect wears a physical stand-in that starts as the authored material, maps
// included, and the authored material itself is only ever touched by settings
// that apply to it (colour mode, opacity) and is always written back in full.
function inspectStandIn(THREE, authored) {
  if (authored.isMeshPhysicalMaterial) return authored.clone();
  const material = new THREE.MeshPhysicalMaterial();
  THREE.MeshStandardMaterial.prototype.copy.call(material, authored);
  material.defines = { STANDARD: "", PHYSICAL: "" };
  return material;
}

/**
 * Take over the lit materials under `root`. Materials shared between meshes are
 * un-shared first (a per-part palette needs one colour per mesh); those clones
 * and the stand-ins Inspect and "Flat" wear are this object's to dispose.
 * Textures stay with whoever authored them.
 *
 * @returns {{ apply(look: object | null): void, dispose(): void, meshCount: number }}
 */
export function createSurfaceLook(THREE, root) {
  const slots = [];
  const seen = new Set();
  const owned = new Set();
  let meshIndex = 0;
  root?.traverse?.((object) => {
    if (!object?.isMesh) return;
    const ownIndex = object.userData?.cadFillIndex;
    const fillIndex = Number.isInteger(ownIndex) && ownIndex >= 0 ? ownIndex : meshIndex;
    meshIndex += 1;
    const list = Array.isArray(object.material) ? object.material : [object.material];
    list.forEach((material, slot) => {
      if (!litMaterial(material)) return;
      let own = material;
      if (seen.has(material)) {
        own = material.clone();
        own.userData = { ...material.userData };
        owned.add(own);
        if (Array.isArray(object.material)) object.material[slot] = own;
        else object.material = own;
      }
      seen.add(own);
      slots.push({ mesh: object, slot, fillIndex, lit: own, inspect: null, unlit: null, authored: readAuthored(own) });
    });
  });

  const assign = (entry, material) => {
    if (Array.isArray(entry.mesh.material)) entry.mesh.material[entry.slot] = material;
    else entry.mesh.material = material;
  };

  function apply(look = null) {
    const settings = look?.materialSettings || {};
    const authoredLook = !look || look.authored === true;
    const forceFill = Boolean(look) && settings.overrideSourceColors === true;
    const flat = look?.surface?.style === "flat";
    const opacityScale = look?.surface ? clamp01(look.surface.opacity, 1) : 1;
    for (const entry of slots) {
      const { lit, authored } = entry;
      const sourceColored = lit.userData?.cadSourceColor !== false;
      const filled = forceFill || (!authoredLook && !sourceColored);
      const fillIndex = settings.cycleColors === true ? entry.fillIndex : 0;
      const color = filled ? resolveMaterialFillBaseColor(THREE, settings, fillIndex)
        : authoredLook || authored.vertexColors ? authored.color
          : shapeSourceColor(THREE, authored.color, settings);
      const opacity = clamp01(authored.opacity * opacityScale, 1);
      const next = {
        map: forceFill ? null : authored.map,
        vertexColors: forceFill ? false : authored.vertexColors,
        side: authoredLook ? authored.side : THREE.DoubleSide,
        transparent: authored.transparent || opacity < 0.999,
        opacity,
        depthWrite: authored.transparent ? authored.depthWrite : opacity >= 0.999
      };
      let target = lit;
      if (flat) {
        // "Flat" is unlit, as it is for every other model: colour without shading.
        target = entry.unlit ||= new THREE.MeshBasicMaterial({ name: lit.name });
      } else if (!authoredLook) {
        target = entry.inspect ||= inspectStandIn(THREE, lit);
        for (const key of ["roughness", "metalness", "clearcoat", "clearcoatRoughness"]) target[key] = clamp01(settings[key]);
        target.envMapIntensity = Math.max(Number(settings.envMapIntensity) || 0, 0);
        // The viewer lifts its surfaces by a trace of their own colour. A part that
        // authored a glow of its own keeps it.
        if (!authored.glows) {
          target.emissive.copy(color);
          target.emissiveIntensity = clamp01(settings.emissiveIntensity);
        }
      }
      const programChanged = ["map", "vertexColors", "side", "transparent"].some((key) => target[key] !== next[key]);
      Object.assign(target, next);
      target.color.copy(color);
      if (programChanged) target.needsUpdate = true;
      assign(entry, target);
    }
  }

  return {
    apply,
    meshCount: meshIndex,
    dispose() {
      apply(null);
      for (const entry of slots) {
        entry.inspect?.dispose();
        entry.unlit?.dispose();
        entry.inspect = entry.unlit = null;
      }
      for (const material of owned) material.dispose();
      owned.clear();
    }
  };
}
