// The tube/braid runtime's lazy boundary.
//
// tubeDeformation.js and the three modules under it (the GPU path, the braid
// material and their shared shader attributes) are ~29 kB of the client's
// initial chunk, and only one thing in the whole viewer can reach them: a
// document's embedded animation calling `deformTube` on a clip handle. Nothing
// else produces a deformation — a step module's effects only carry what an
// animation frame already put there — so a document with no `animation.source`
// can never need this code, and must never download it.
//
// The load therefore happens at the one async door every clip must pass
// through: `compileAnimationSource` in renderModule.js awaits it before a clip
// exists to be evaluated. Frame evaluation stays synchronous and sees a loaded
// runtime, so an animated tube renders exactly as it did when this was a static
// import — there is no first-frame rest pose and no dropped frame.
//
// `tubeDeformation()` answers null until then. Every caller outside the
// animation path (the scene's resets, the edge-line pass) is a no-op on a
// record that has no tube state, and a record can only acquire tube state after
// a deformation was applied, so `tubeDeformation()?.fn(...)` is exact rather
// than merely tolerant. `deformTube` itself, which cannot no-op, throws.

let loaded = null;
let pending = null;

/** The loaded tube runtime, or null when the chunk has not been fetched. */
export function tubeDeformation() {
  return loaded;
}

export function loadTubeDeformation() {
  if (loaded) {
    return Promise.resolve(loaded);
  }
  if (!pending) {
    pending = import("./tubeDeformation.js")
      .then((module) => {
        loaded = module;
        return loaded;
      })
      .catch((error) => {
        // A failed fetch must not poison the boundary: the next call retries.
        pending = null;
        throw error;
      });
  }
  return pending;
}

/** The loaded runtime, or a loud failure naming the door that loads it. */
export function requireTubeDeformation(what = "a tube deformation") {
  if (!loaded) {
    throw new Error(
      `${what} needs the tube runtime, which is loaded with the document's animation. `
      + "Compile clips through compileAnimationSource/loadSourceAnimation, or await "
      + "loadTubeDeformation() first."
    );
  }
  return loaded;
}
