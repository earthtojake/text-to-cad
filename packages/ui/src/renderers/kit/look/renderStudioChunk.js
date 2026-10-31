// The Render studio's lazy boundary.
//
// Neutral CAD viewing is what every load pays for. The photographic rig and
// stage load only for Render, which is Preview's alone: the shell
// warms them a moment after a model is on screen (`useRendererShell`'s
// `previewPrepare`, through the viewport's `prepareViewSettings`), and the
// viewport loads them itself on entering Render if nothing has yet.
//
// The scene half cannot be a React.lazy component: the viewport applies the studio
// from effects, not from JSX. It is a module handle instead — `studioScene()`
// answers synchronously with the loaded namespace or `null`, and `null` is a
// legitimate state that the viewer already knows how to present. A new canvas
// waits for `runtime.environmentReady` before its first presentation. An already
// visible canvas keeps drawing while the studio loads, then updates in place;
// changing View settings never covers or replaces the existing canvas.

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
      import("@text-to-cad/core/common/photographicStudio.js"),
      import("@text-to-cad/core/common/environmentMap.js")
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
