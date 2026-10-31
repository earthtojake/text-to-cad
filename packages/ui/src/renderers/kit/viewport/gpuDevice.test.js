import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

// A browser's OffscreenCanvas and bitmap canvas, as far as the device uses them.
class FakeOffscreenCanvas extends EventTarget {
  constructor(width, height) { super(); this.width = width; this.height = height; this.frames = 0; }
  transferToImageBitmap() { this.frames += 1; return { frame: this.frames, width: this.width, height: this.height }; }
}
globalThis.OffscreenCanvas ??= FakeOffscreenCanvas;
globalThis.ImageBitmapRenderingContext ??= class {};
const { acquireGpuDevice } = await import('./gpuDevice.js');

function fakeRenderer(canvas) {
  const state = { viewport: new THREE.Vector4(0, 0, 1, 1), scissor: new THREE.Vector4(0, 0, 1, 1), scissorTest: false,
    clearColor: new THREE.Color(0x000000), clearAlpha: 0, pixelRatio: 1, target: null };
  const draws = [];
  return {
    draws, canvas,
    toneMapping: THREE.NoToneMapping, toneMappingExposure: 1, outputColorSpace: THREE.SRGBColorSpace,
    localClippingEnabled: false, clippingPlanes: [], autoClear: true, autoClearColor: true, autoClearDepth: true,
    autoClearStencil: true, sortObjects: true,
    shadowMap: { enabled: false, type: THREE.PCFShadowMap, autoUpdate: true, needsUpdate: false },
    getContext: () => ({ isContextLost: () => false }),
    getClearColor: target => target.copy(state.clearColor), getClearAlpha: () => state.clearAlpha,
    setClearColor(color, alpha) { state.clearColor = new THREE.Color(color); if (alpha !== undefined) state.clearAlpha = alpha; },
    setClearAlpha(alpha) { state.clearAlpha = alpha; },
    getViewport: target => target.copy(state.viewport), setViewport(x, y, w, h) { state.viewport = x?.isVector4 ? x.clone() : new THREE.Vector4(x, y, w, h); },
    getScissor: target => target.copy(state.scissor), setScissor(x, y, w, h) { state.scissor = x?.isVector4 ? x.clone() : new THREE.Vector4(x, y, w, h); },
    getScissorTest: () => state.scissorTest, setScissorTest(value) { state.scissorTest = value; },
    getPixelRatio: () => state.pixelRatio, setPixelRatio(value) { state.pixelRatio = value; },
    setSize(width, height) { canvas.width = Math.floor(width * state.pixelRatio); canvas.height = Math.floor(height * state.pixelRatio); state.viewport = new THREE.Vector4(0, 0, width, height); },
    getRenderTarget: () => state.target, setRenderTarget(target) { state.target = target; },
    render(scene) { draws.push({ scene: scene.name, toneMapping: this.toneMapping, shadows: this.shadowMap.enabled, size: [canvas.width, canvas.height], target: state.target }); },
    clear() {}, dispose() {}, forceContextLoss() {},
  };
}

function viewCanvas() {
  const shown = [];
  return { shown, width: 0, height: 0, style: {}, getContext: kind => (kind === 'bitmaprenderer' ? { transferFromImageBitmap: bitmap => shown.push(bitmap) } : null), dispatchEvent() {} };
}
const tick = () => new Promise(resolve => queueMicrotask(resolve));

test('two views share one renderer, each drawing with its own state and size', async () => {
  const device = acquireGpuDevice(THREE, fakeRenderer);
  const editorCanvas = viewCanvas(), previewCanvas = viewCanvas();
  const editor = device.createView(editorCanvas), preview = device.createView(previewCanvas);
  assert.equal(editor.domElement, editorCanvas, "a view's canvas is its own");
  editor.setPixelRatio(2); editor.setSize(400, 300, false);
  editor.toneMapping = THREE.ACESFilmicToneMapping; editor.shadowMap.enabled = true;
  preview.setPixelRatio(1); preview.setSize(1000, 800, false);
  preview.toneMapping = THREE.NeutralToneMapping; preview.shadowMap.enabled = false;

  editor.render({ name: 'editor' });
  preview.render({ name: 'preview' });
  editor.render({ name: 'editor' });
  assert.deepEqual(device.renderer.draws.map(draw => [draw.scene, draw.toneMapping, draw.shadows, draw.size]), [
    ['editor', THREE.ACESFilmicToneMapping, true, [800, 600]],
    ['preview', THREE.NeutralToneMapping, false, [1000, 800]],
    ['editor', THREE.ACESFilmicToneMapping, true, [800, 600]],
  ]);
  assert.equal(preview.toneMapping, THREE.NeutralToneMapping, "a view's state is kept while another draws");
  assert.deepEqual(editor.getDrawingBufferSize(new THREE.Vector2()).toArray(), [800, 600]);
  editor.dispose(); preview.dispose();
  await tick();
});

test("a frame's draws reach its canvas once, after the frame; another view's draw hands it over first", async () => {
  const device = acquireGpuDevice(THREE, fakeRenderer);
  const aCanvas = viewCanvas(), bCanvas = viewCanvas();
  const a = device.createView(aCanvas), b = device.createView(bCanvas);
  a.render({ name: 'pass 1' });
  a.render({ name: 'pass 2' });
  assert.equal(aCanvas.shown.length, 0, 'nothing is handed over mid-frame');
  await tick();
  assert.equal(aCanvas.shown.length, 1, 'one bitmap per frame');

  a.render({ name: 'a' });
  b.render({ name: 'b' });
  assert.equal(aCanvas.shown.length, 2, "a's frame is handed over before b draws over it");
  await tick();
  assert.equal(bCanvas.shown.length, 1);

  // A draw into a render target is not a frame.
  b.setRenderTarget({ isRenderTarget: true });
  b.render({ name: 'offscreen' });
  b.setRenderTarget(null);
  await tick();
  assert.equal(bCanvas.shown.length, 1);
  a.dispose(); b.dispose();
});

test('a released view leaves the device and is never handed a frame', async () => {
  const device = acquireGpuDevice(THREE, fakeRenderer);
  const canvas = viewCanvas();
  const view = device.createView(canvas);
  const count = device.viewCount;
  view.render({ name: 'last' });
  view.dispose();
  await tick();
  assert.equal(canvas.shown.length, 0);
  assert.equal(device.viewCount, count - 1);
});
