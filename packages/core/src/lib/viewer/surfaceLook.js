import { syncMaterialClipPlanes } from "./clipPlane.js";
import { useSurfaceBrdf } from "./surfaceBrdf.js";
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
//                           grading and the finish channels (a `specularIntensity`
//                           among them replaces the authored one)
//     authored: boolean,    true: keep each material's own finish, sidedness and
//                           source colours (photographic Render)
//     surface: { style: "shaded" | "flat", opacity },
//     colorPower?: number,  the colour of every surface without a finish of its own, and
//                           of every fill, linear, raised to this power (1: as written,
//                           unless a scene's own look says otherwise: `lib/xbf/xbfLook.js`)
//     brdf?: string,        the surface model the lit surfaces are drawn by (a name of
//                           `surfaceBrdf.js`'s `SURFACE_BRDFS`); three's own when absent,
//                           and in an authored look always
//     finishes?: boolean }  false: no surface keeps a finish or a glow its file authored, and
//                           every colour is raised to `colorPower` (a scene's own look that
//                           draws none: X-ray's, `lib/xbf/xbfLook.js`)
//
// A material marked `userData.cadAuthoredFinish` (a finish its file authored, which the
// scene asks to keep) keeps it in the shaded looks too -- opaque, its source colour shown --
// reflecting the scene's environment; in every other look (a fill, X-ray, Flat) it wears the
// look's finish like any other surface.
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
// What an authored finish is beyond a colour: what its stand-in copies from it in a shaded
// look, and resets to a plain surface's in any other.
const FINISH_KEYS = Object.freeze(["roughness", "metalness", "clearcoat", "clearcoatRoughness", "ior", "anisotropy",
  "anisotropyRotation", "transmission", "thickness", "attenuationDistance"]);

function plainFinish(THREE) {
  const plain = new THREE.MeshPhysicalMaterial();
  const found = Object.fromEntries(FINISH_KEYS.map(key => [key, plain[key]]));
  found.attenuationColor = plain.attenuationColor.clone();
  plain.dispose();
  return found;
}

// How strongly an authored material answers light specularly (a standard one: three's default).
const authoredSpecular = (material) => (material.isMeshPhysicalMaterial ? material.specularIntensity : 1);

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
 * Textures stay with whoever authored them. Clip's planes (`setClipPlanes`) cut every material under
 * `root`, the stand-ins a later look puts on included.
 *
 * @returns {{ apply(look: object | null): void, setClipPlanes(planes: object[]): void, dispose(): void,
 *   meshCount: number }}
 */
export function createSurfaceLook(THREE, root) {
  let clipPlanes = [];
  let plain = null;
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
    const power = Number(look?.colorPower) > 0 ? Number(look.colorPower) : 1;
    const finishes = look?.finishes !== false;
    for (const entry of slots) {
      const { lit, authored } = entry;
      const sourceColored = lit.userData?.cadSourceColor !== false;
      const filled = forceFill || (!authoredLook && !sourceColored);
      const fillIndex = settings.cycleColors === true ? entry.fillIndex : 0;
      let color = filled ? resolveMaterialFillBaseColor(THREE, settings, fillIndex)
        : authoredLook || authored.vertexColors ? authored.color
          : shapeSourceColor(THREE, authored.color, settings);
      if (power !== 1 && (filled || !finishes || lit.userData?.cadAuthoredFinish !== true)) {
        color = new THREE.Color(color.r ** power, color.g ** power, color.b ** power);
      }
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
        const finish = lit.userData?.cadAuthoredFinish === true;
        const preserveFinish = finish && finishes && !forceFill && opacityScale >= 0.999;
        if (preserveFinish) {
          // Standard materials have no Physical-only channels. Keep their authored
          // fields and use neutral Physical defaults for the stand-in's other fields.
          plain ||= plainFinish(THREE);
          for (const key of FINISH_KEYS) target[key] = lit[key] ?? plain[key];
          target.attenuationColor.copy(lit.attenuationColor || plain.attenuationColor);
          target.specularIntensity = authoredSpecular(lit);
          target.envMapIntensity = 1;
        } else {
          if (finish) {
            plain ||= plainFinish(THREE);
            for (const key of FINISH_KEYS) target[key] = plain[key];
            target.attenuationColor.copy(plain.attenuationColor);
          }
          for (const key of ["roughness", "metalness", "clearcoat", "clearcoatRoughness"]) target[key] = clamp01(settings[key]);
          target.specularIntensity = settings.specularIntensity === undefined ? authoredSpecular(lit) : clamp01(settings.specularIntensity);
          target.envMapIntensity = Math.max(Number(settings.envMapIntensity) || 0, 0);
        }
        // The viewer lifts its surfaces by a trace of their own colour. A part that
        // authored a glow of its own keeps it, where the look keeps finishes.
        if (authored.glows && finishes) {
          target.emissive.copy(lit.emissive);
          target.emissiveIntensity = lit.emissiveIntensity;
        } else if (!authored.glows || !finishes) {
          target.emissive.copy(color);
          target.emissiveIntensity = clamp01(settings.emissiveIntensity);
        }
      }
      const brdfChanged = !flat && target !== lit && useSurfaceBrdf(THREE, target, look?.brdf ?? null);
      const programChanged = brdfChanged || ["map", "vertexColors", "side", "transparent"].some((key) => target[key] !== next[key]);
      Object.assign(target, next);
      target.color.copy(color);
      // Clip takes the normal base hue, before selection/hover ink is applied.
      if (entry.slot === 0) entry.mesh.userData.cadBaseColor = color.clone();
      if (programChanged) target.needsUpdate = true;
      syncMaterialClipPlanes(target, clipPlanes);
      assign(entry, target);
    }
  }

  return {
    apply,
    setClipPlanes(planes) {
      clipPlanes = Array.isArray(planes) ? planes : [];
      // The caps' own stencils are cut by the planes they cap (`sectionCaps.js`).
      root?.traverse?.((object) => { if (object?.isMesh && object.name !== "Section stencil") syncMaterialClipPlanes(object.material, clipPlanes); });
    },
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
