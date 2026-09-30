import { fitCameraDepthToBounds } from "@text-to-cad/core/common/renderOptions.js";
import { mergeBoundsList } from "@text-to-cad/core/lib/viewer/autoZoom.js";
import { getSceneScaleSettings } from "@text-to-cad/core/lib/viewer/sceneScale.js";
import { canvasToBlob } from "@text-to-cad/core/lib/viewer/screenshotCapture.js";
import { interactiveCameraFrameForBounds } from "../camera/viewportCameraFit.js";
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from "../camera/viewportCameraKit.js";
import { viewerDepthSettings } from "./renderDepthPolicy.js";

/** The room a card leaves around its model: the fit's padding on its framed box (about 4% a side; a round part's box corners leave it more). */
export const THUMBNAIL_FIT_PADDING = 1.08;

/**
 * A picture of the model for a library card: the scene as the view draws it — its look and its
 * Display settings — but framed whole, from the default direction, at the card's own aspect,
 * whatever camera the person holds and however large the view is or what covers it. The model is
 * drawn on its own, on transparency — no backdrop, and none of the stage a person may have turned
 * on (the floor with its glow and shadow, the grid, the origin axes), which take the scheme's
 * colours: a card shows it on the viewport's own colour for the home's colour scheme, whichever
 * scheme it was pictured in.
 *
 * It is drawn into the corner of the view's own drawing buffer and copied out in the same task,
 * and then the view's own frame is drawn again over it: the browser composites only once the task
 * ends, so the card's frame is never on screen, and nothing of the view — its camera, its size,
 * its lines' widths — is left changed. The picture is `width` × `height` pixels, or the largest
 * region of that aspect a small view's buffer holds.
 *
 * @param {object} runtime The viewport's live runtime (`useViewerRuntime`).
 * @param {{ bounds: object, modelOffset?: object | null, sceneScaleMode: string, width: number, height: number }} options
 *   `bounds` is the model's box at rest, in its own coordinates; `modelOffset` where the view put it.
 * @returns {Promise<Blob>} A PNG.
 */
export async function renderThumbnail(runtime, { bounds, modelOffset = null, sceneScaleMode, width, height }) {
  const { THREE, renderer, scene, camera: viewCamera } = runtime || {};
  const framed = mergeBoundsList([bounds]);
  if (!THREE || !renderer || !scene || !viewCamera || !framed) throw new Error("The viewer has no model to picture yet.");
  if (!(width > 0) || !(height > 0)) throw new Error("A picture needs a positive size.");
  const aspect = width / height;
  const buffer = renderer.getDrawingBufferSize(new THREE.Vector2());
  let pixelWidth = Math.min(Math.round(width), buffer.x);
  let pixelHeight = Math.round(pixelWidth / aspect);
  if (pixelHeight > buffer.y) { pixelHeight = buffer.y; pixelWidth = Math.round(pixelHeight * aspect); }
  if (pixelWidth < 1 || pixelHeight < 1) throw new Error("The viewer is too small to picture the model.");

  // The view's own lens — its projection and focal length — posed as the view opens a file.
  const camera = viewCamera.clone();
  camera.clearViewOffset?.();
  const frame = interactiveCameraFrameForBounds(THREE, {
    camera, controls: { target: new THREE.Vector3() }, bounds: framed, modelOffset, frameAspect: aspect,
    minRadius: getSceneScaleSettings(sceneScaleMode).minModelRadius,
    viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP, padding: THUMBNAIL_FIT_PADDING
  });
  if (!frame) throw new Error("The model's bounds cannot be framed.");
  camera.up.copy(frame.up);
  camera.position.copy(frame.position);
  camera.lookAt(frame.target);
  camera.zoom = 1;
  if (camera.isOrthographicCamera) {
    camera.top = frame.halfHeight;
    camera.bottom = -frame.halfHeight;
    camera.right = frame.halfHeight * aspect;
    camera.left = -frame.halfHeight * aspect;
  } else {
    camera.aspect = aspect;
  }
  camera.updateMatrixWorld(true);
  fitCameraDepthToBounds(camera, runtime.modelBounds, viewerDepthSettings(runtime));
  camera.updateProjectionMatrix();

  const canvas = document.createElement("canvas");
  canvas.width = pixelWidth;
  canvas.height = pixelHeight;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("The browser cannot draw the model's picture.");
  const pixelRatio = renderer.getPixelRatio();
  const viewport = renderer.getViewport(new THREE.Vector4());
  const scissorTest = renderer.getScissorTest();
  const target = renderer.getRenderTarget();
  const background = scene.background;
  const clearAlpha = renderer.getClearAlpha();
  const stage = [runtime.stageGroup, runtime.gridHelper, runtime.originAxis].filter(Boolean).map(object => [object, object.visible]);
  try {
    renderer.setRenderTarget(null);
    renderer.setScissorTest(false);
    scene.background = null;
    renderer.setClearAlpha(0);
    for (const [object] of stage) object.visible = false;
    // Screen-space lines keep their width in pixels of the picture, as they do on screen.
    runtime.setScreenSpaceLineResolution?.(pixelWidth, pixelHeight);
    renderer.setViewport(0, 0, pixelWidth / pixelRatio, pixelHeight / pixelRatio);
    renderer.render(scene, camera);
    // The GL viewport starts at the buffer's bottom-left; the canvas's rows run from its top.
    context.drawImage(renderer.domElement, 0, buffer.y - pixelHeight, pixelWidth, pixelHeight, 0, 0, pixelWidth, pixelHeight);
  } finally {
    scene.background = background;
    for (const [object, visible] of stage) object.visible = visible;
    renderer.setClearAlpha(clearAlpha);
    renderer.setViewport(viewport);
    renderer.setScissorTest(scissorTest);
    runtime.syncScreenSpaceLineMaterials?.();
    renderer.render(scene, viewCamera);
    renderer.setRenderTarget(target);
  }
  return canvasToBlob(canvas);
}
