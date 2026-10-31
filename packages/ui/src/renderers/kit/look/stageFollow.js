// How the stage follows a scene that moves (a pose, a routine): the lights, the floor and the
// shadows they cast are fitted to where the scene is (`fitStageToScene`, ShellViewport.jsx).

/**
 * While a routine plays or a pose is dragged, the Render floor shadow's heights (its depth
 * pass of every caster) are measured at most this often; its cast shadow still follows every
 * frame, and the heights are measured once more when the scene comes to rest
 * (`createStudioContactShadow`, core `common/studioContactShadow.js`).
 */
export const CONTACT_SHADOW_HEIGHT_INTERVAL_MS = 100;

/**
 * What a stage fit depends on: the scene, where it is now and at rest, the model's offset,
 * and the fit itself, whose closure changes with every setting it reads.
 */
export function stageFitInputs(fit, scene, offset) {
  const bounds = scene?.bounds;
  const rest = scene?.restBounds;
  return {
    fit, scene,
    key: JSON.stringify([bounds?.min, bounds?.max, rest?.min, rest?.max, offset ?? null])
  };
}

/**
 * Whether the stage was last fitted to exactly these inputs. A pass that moved nothing (a pose
 * pass a hover re-ran, a routine's frame that holds still) then has nothing to refit, and no
 * shadow to re-render.
 */
export function stageFitCurrent(previous, next) {
  return Boolean(previous) && previous.fit === next.fit && previous.scene === next.scene && previous.key === next.key;
}
