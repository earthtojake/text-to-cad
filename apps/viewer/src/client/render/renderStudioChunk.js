// The Render studio's lazy boundary.
//
// Inspect is what every load pays for. The photographic rig — its softbox
// environment, its stage and its two settings panels — is only reachable
// through the navbar's Viewing mode menu, so it ships as its own chunk and is
// fetched the first time someone asks for Render (or, cheaply, on hover and on
// idle, so that asking is usually free).
//
// The scene half cannot be a React.lazy component: CadViewer applies the studio
// from effects, not from JSX. It is a module handle instead — `studioScene()`
// answers synchronously with the loaded namespace or `null`, and `null` is a
// legitimate state that the viewer already knows how to present. While it holds,
// `runtime.environmentReady` stays false and framePresentation keeps the canvas
// covered with the destination backdrop, which is the same cover a mode switch
// already shows until lighting has drawn its first frame. A half-configured
// photographic scene is therefore not reachable: either the studio has applied
// or nothing is presented.
//
// The panel half is ordinary React.lazy, wired in RenderSettingsTab.js and
// MaterialsSettingsTab.js. Both halves are requested together, so opening
// Render does not stage two separate waits.

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
      import("cadgen-js/common/photographicStudio.js"),
      import("cadgen-js/common/environmentMap.js")
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

export function importRenderSettingsContent() {
  return import("../components/workbench/RenderSettingsContent.js");
}

export function importMaterialsSettingsContent() {
  return import("../components/workbench/MaterialsSettingsContent.js");
}

/**
 * Warm every piece Render needs. Called on the mode switch itself, and
 * speculatively from the Viewing mode menu's hover and from first idle.
 * Rejections are the caller's to report; a prefetch swallows them because a
 * failed prefetch is not yet a failure anyone asked about.
 */
export function loadRenderStudio() {
  return Promise.all([
    loadStudioScene(),
    importRenderSettingsContent(),
    importMaterialsSettingsContent()
  ]);
}

export function prefetchRenderStudio() {
  loadRenderStudio().catch(() => {});
}
