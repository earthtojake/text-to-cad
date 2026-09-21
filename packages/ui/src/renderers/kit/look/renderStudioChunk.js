// The Render studio's lazy boundary.
//
// Neutral CAD viewing is what every load pays for. The photographic rig and
// stage load only when an enabled lighting/background/floor group requires them.
// The lightweight grouped settings panel is always available in every preset.
//
// The scene half cannot be a React.lazy component: the viewport applies the studio
// from effects, not from JSX. It is a module handle instead — `studioScene()`
// answers synchronously with the loaded namespace or `null`, and `null` is a
// legitimate state that the viewer already knows how to present. A new canvas
// waits for `runtime.environmentReady` before its first presentation. An already
// visible canvas keeps drawing while the studio loads, then updates in place;
// changing View settings never covers or replaces the existing canvas.
//

let loadedScene = null;
let scenePromise = null;

/**
 * The loaded studio scene namespace, or null when the chunk has not arrived.
 * Callers treat null as "not yet", never as an error.
 */
export function studioScene() {
  return loadedScene;
}

export function loadStudioScene() {
  if (loadedScene) {
    return Promise.resolve(loadedScene);
  }
  if (!scenePromise) {
    scenePromise = Promise.all([
      import("@hardcore/core/common/photographicStudio.js"),
      import("@hardcore/core/common/environmentMap.js")
    ])
      .then(([studio, environment]) => {
        loadedScene = { ...studio, ...environment };
        return loadedScene;
      })
      .catch((error) => {
        // A failed fetch must not poison the boundary: the next request retries.
        scenePromise = null;
        throw error;
      });
  }
  return scenePromise;
}

/**
 * Warm every piece Render needs. Called on the mode switch itself, and
 * speculatively from the Viewing mode control's hover and focus.
 * Rejections are the caller's to report; a prefetch swallows them because a
 * failed prefetch is not yet a failure anyone asked about.
 */
export function loadRenderStudio() {
  return loadStudioScene();
}

export function prefetchRenderStudio() {
  loadRenderStudio().catch(() => {});
}
