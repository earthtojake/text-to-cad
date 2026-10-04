// One neutral product-photography rig shared by the direct light and the HDR
// reflection cards. Public rotation moves these directions together about Z.
// The key sits above and to the side of the default isometric camera: a
// camera-aligned key flattens cylinders and hides depth between assembly parts.
export const PHOTOGRAPHIC_STUDIO_KEY_DIRECTION = Object.freeze([-0.35, -1, 1.5]);
// The broad rear fill reflects into horizontal surfaces viewed from iso, so
// polished plates and black plastic retain detail instead of reflecting void.
export const PHOTOGRAPHIC_STUDIO_FILL_DIRECTION = Object.freeze([-0.65, 0.8, 0.6]);
// A broad bounce low on the key's far side, toward the default camera. It
// fills the faces the key cannot reach — the right-hand side of an iso view —
// and gives polished metal a second, opposing highlight. Fill sets it with the
// rear fill card.
export const PHOTOGRAPHIC_STUDIO_BOUNCE_DIRECTION = Object.freeze([0.95, 0.33, 0.45]);

// Calibrated together at 0 EV. PMREM also supplies diffuse illumination, so
// its key card and the shadow-casting spotlight share the illumination budget.
export const PHOTOGRAPHIC_STUDIO_KEY_ILLUMINANCE = 2.4;
export const PHOTOGRAPHIC_STUDIO_CARD_RADIANCE = 8;
// The sweep the cards hang in: dim walls and ceiling, the darkest band at the
// horizon and a light floor below. Most of the studio's light comes from its
// sources rather than the room, so metal shows a lit softbox against a darker
// surround, but nothing is a void: a black enclosure crushed every face turned
// away from the cards, and every polished surface that reflected it, to black.
export const PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE = Object.freeze({ zenith: 0.14, horizon: 0.07, nadir: 0.3 });
// The studio's fixed soft sources, beside the key and the two fill cards: a large
// overhead softbox and two tall strip boxes about 75 degrees either side of the
// default camera. Their bright cores fall off toward the edges (`falloff`: across
// the width, then along the height), so polished and satin metal show defined
// gradients and highlight lines between darker gaps, which is what reads as metal.
// Sizes are at Size 1 and grow with the softbox Size at constant flux, like the
// cards. A strip's `up` stands it upright.
export const PHOTOGRAPHIC_STUDIO_PANELS = Object.freeze([
  Object.freeze({
    name: "studio-top-softbox", direction: Object.freeze([0, 0, 1]),
    width: 7, height: 5, radiance: 2.2, falloff: Object.freeze([0.6, 0.6])
  }),
  Object.freeze({
    name: "studio-strip-left", direction: Object.freeze([-0.5, -0.87, 0.05]), up: Object.freeze([0, 0, 1]),
    width: 1.2, height: 9, radiance: 3, falloff: Object.freeze([0.7, 0.4])
  }),
  Object.freeze({
    name: "studio-strip-right", direction: Object.freeze([0.87, 0.5, 0.05]), up: Object.freeze([0, 0, 1]),
    width: 1.2, height: 9, radiance: 3, falloff: Object.freeze([0.7, 0.4])
  })
]);
// The opaque stage is mostly backdrop-colored fill, with a smaller diffuse
// response for subtle contact shadows. This also softens the spotlight pool
// against the surrounding floor. Both weights are material-local: the model
// and calibrated studio lighting are unaffected.
export const PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT = 0.25;
export const PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY = 0.85;
export const PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX = 0.02;
// The floor shadow (studioContactShadow.js) is baked over a square that reaches
// `reach` times the model's height past its footprint, so the key's soft shadow
// fits; occlusion fades out over `height` times the larger of that height and
// half the footprint.
export const PHOTOGRAPHIC_STUDIO_CONTACT_SHADOW = Object.freeze({ reach: 0.85, height: 0.5 });
// The floor's two finishes (Display's Floor finish). Matte reflects the studio broadly,
// so the floor reads as the backdrop's colour. Glossy reflects its softbox and strips as
// soft highlights, and the model itself (studioFloorReflection.js, at half the canvas's
// resolution): crisp where the model meets the floor, softening and fading over its
// height. `strength` is the reflection's weight at grazing and `normalWeight` the share
// of it looking straight down.
export const PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES = Object.freeze({
  matte: Object.freeze({ roughness: 0.88, envMapIntensity: 0.22, reflection: null }),
  glossy: Object.freeze({
    roughness: 0.35,
    envMapIntensity: 0.22,
    reflection: Object.freeze({
      resolution: 0.5, blur: 2, sharpBlur: 0, blurHeight: 0.8, fadeHeight: 1, strength: 0.75, normalWeight: 0.45
    })
  })
});

// Full square-ground width relative to model-bounds radius. Keep the camera's
// fitted far padding on this same multiplier so the ordinary-depth frustum
// contains the stage instead of cutting an artificial horizon through it.
// The plane remains two triangles, so increasing its extent adds no geometry.
export const PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER = 96;

/**
 * The studio's material policy: one fixed finish for every part the rig
 * lights. Render exposes no material controls, so these are constants of the
 * rig rather than anything the Render recipe can reach. STEP package material
 * channels remain authored inputs and still win over these fallbacks.
 */
export const PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS = Object.freeze({
  defaultColor: "#b9bdc3",
  fillColors: Object.freeze(["#b9bdc3"]),
  cycleColors: false,
  overrideSourceColors: false,
  tintMode: "blend",
  tintStrength: 0,
  roughness: 0.42,
  metalness: 0.03,
  clearcoat: 0,
  clearcoatRoughness: 0.26,
  opacity: 1,
  envMapIntensity: 1,
  emissiveIntensity: 0
});
