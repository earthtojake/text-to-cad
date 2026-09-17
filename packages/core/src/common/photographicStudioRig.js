// One neutral product-photography rig shared by the direct light and the HDR
// reflection cards. Public rotation moves these directions together about Z.
// The key sits above and to the side of the default isometric camera: a
// camera-aligned key flattens cylinders and hides depth between assembly parts.
export const PHOTOGRAPHIC_STUDIO_KEY_DIRECTION = Object.freeze([-0.35, -1, 1.5]);
// The broad rear fill reflects into horizontal surfaces viewed from iso, so
// polished plates and black plastic retain detail instead of reflecting void.
export const PHOTOGRAPHIC_STUDIO_FILL_DIRECTION = Object.freeze([-0.65, 0.8, 0.6]);

// Calibrated together at 0 EV. PMREM also supplies diffuse illumination, so
// its key card and the shadow-casting spotlight share the illumination budget.
export const PHOTOGRAPHIC_STUDIO_KEY_ILLUMINANCE = 2.1;
export const PHOTOGRAPHIC_STUDIO_CARD_RADIANCE = 8;
export const PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE = 0.04;
// The opaque stage is mostly backdrop-colored fill, with a smaller diffuse
// response for subtle contact shadows. This also softens the spotlight pool
// against the surrounding floor. Both weights are material-local: the model
// and calibrated studio lighting are unaffected.
export const PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT = 0.25;
export const PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY = 0.85;
export const PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX = 0.02;

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
