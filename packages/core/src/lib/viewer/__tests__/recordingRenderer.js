// TEST-ONLY: a renderer that draws nothing and says what it was asked to draw, for the tests of a
// stage's draw (`../sceneRig.js`'s `renderWithSceneRig`). Its canvas is 400 x 300 at a pixel ratio
// of 2; as three's renderer does, it floors the canvas's viewport when the canvas is made the
// target again and rounds it when it is set.
import * as THREE from "three";

/**
 * Each draw says what was drawn (`scene`), into what (`target`, null: the canvas), with what
 * auto-clear and viewport, and which of the scene's meshes and lines three would draw there
 * (`drawn`: visible, on a layer the camera sees).
 */
export function recordingRenderer({ halfFloats = true, antialias = true } = {}) {
  const draws = [];
  const ratio = 2;
  const viewport = new THREE.Vector4(0, 0, 400, 300);
  const current = new THREE.Vector4(0, 0, 800, 600);
  let target = null;
  const renderer = {
    toneMapping: THREE.ACESFilmicToneMapping,
    toneMappingExposure: 1,
    autoClear: true,
    shadowMap: { autoUpdate: true, needsUpdate: false },
    extensions: { has: name => halfFloats && name === "EXT_color_buffer_float" },
    getContext: () => ({ getContextAttributes: () => ({ antialias }) }),
    getRenderTarget: () => target,
    setRenderTarget(next) {
      target = next;
      current.copy(next ? next.viewport : viewport.clone().multiplyScalar(ratio).floor());
    },
    getDrawingBufferSize: size => size.set(800, 600),
    getPixelRatio: () => ratio,
    getCurrentViewport: into => into.copy(current),
    getViewport: into => into.copy(viewport),
    setViewport(next) {
      viewport.copy(next);
      current.copy(next).multiplyScalar(ratio).round();
    },
    getScissor: into => into.set(0, 0, 400, 300),
    getScissorTest: () => false,
    render(scene, camera) {
      const drawn = [];
      scene.traverseVisible((object) => {
        if ((object.isMesh || object.isLine) && object.layers.test(camera.layers)) drawn.push(object);
      });
      draws.push({ scene, camera, target, autoClear: renderer.autoClear, viewport: current.clone(), drawn,
        background: scene.background ?? null, shadows: renderer.shadowMap.autoUpdate });
    },
    compileAsync(scene) {
      draws.push({ compiled: scene, target });
      return Promise.resolve();
    }
  };
  return { renderer, draws };
}
