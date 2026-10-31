// One WebGL context for every view on the page: the GPU device.
//
// A view (a viewport: the editor's, Preview's) is a DOM canvas of its own, with its own
// scene, camera, look and controls. What it draws is drawn by the device's one WebGLRenderer,
// on an OffscreenCanvas, and handed to the view's canvas as a bitmap at the end of the frame
// (`transferToImageBitmap` → the canvas's `bitmaprenderer` context: zero-copy, about 0.06 ms a
// frame). So geometry, textures and compiled programs are uploaded once whatever number of views
// draw them, and a view that is not drawing keeps the last picture it was handed, untouched by
// anything another view does.
//
// Each view gets a renderer HANDLE (`device.createView(canvas)`) that the viewport uses as it
// used its own renderer: the handle's `domElement` is the view's canvas (pointer input, layout,
// cursors), its size and pixel ratio are the view's, and the renderer state a view sets for
// itself (tone mapping, exposure, colour space, clipping, auto-clear, the shadow map's policy,
// the clear colour, viewport and scissor) is swapped in when the view draws and kept aside when
// another one does. Everything else is the device's, shared. Pixels a caller reads back right
// after drawing come from `drawingCanvas` (the device's buffer), not from the view's canvas,
// which is handed the frame only once the frame's draws are done.
//
// Where the browser cannot draw WebGL into an OffscreenCanvas or show a bitmap on a canvas, there
// is no device (`acquireGpuDevice` returns null) and each viewport creates a renderer of its own.

const SWAPPED_FIELDS = [
  "toneMapping", "toneMappingExposure", "outputColorSpace", "localClippingEnabled", "clippingPlanes",
  "autoClear", "autoClearColor", "autoClearDepth", "autoClearStencil", "sortObjects"
];
const SWAPPED_SHADOW_FIELDS = ["enabled", "type", "autoUpdate", "needsUpdate"];
// How long the device outlives its last view: a file switch releases one view and creates the next
// within a moment, and the programs compiled for the first are worth keeping for the second.
const DEVICE_GRACE_MS = 5000;

export function gpuDeviceSupported() {
  return typeof OffscreenCanvas === "function"
    && typeof ImageBitmapRenderingContext === "function"
    && typeof OffscreenCanvas.prototype.transferToImageBitmap === "function";
}

let shared = null;

/**
 * The page's device, created on first use; `null` where the browser cannot have one, or the
 * device could not be created. `createRenderer(canvas)` makes the device's WebGLRenderer on the
 * OffscreenCanvas it is handed (the caller's attributes and fallback rules).
 */
export function acquireGpuDevice(THREE, createRenderer) {
  if (!gpuDeviceSupported()) return null;
  if (shared && !shared.disposed && shared.THREE === THREE) {
    shared.retain();
    return shared;
  }
  let device;
  try {
    device = createGpuDevice(THREE, createRenderer);
  } catch {
    return null;
  }
  shared = device;
  device.retain();
  return device;
}

function createGpuDevice(THREE, createRenderer) {
  const canvas = new OffscreenCanvas(1, 1);
  const renderer = createRenderer(canvas);
  const gl = renderer.getContext();
  const views = new Set();
  let active = null;
  let users = 0;
  let graceTimer = 0;
  // The view whose frame is drawn but not yet handed to its canvas.
  let pending = null;
  let presentQueued = false;

  const readState = () => {
    const state = {};
    for (const field of SWAPPED_FIELDS) state[field] = renderer[field];
    state.shadowMap = {};
    for (const field of SWAPPED_SHADOW_FIELDS) state.shadowMap[field] = renderer.shadowMap[field];
    state.clearColor = renderer.getClearColor(new THREE.Color());
    state.clearAlpha = renderer.getClearAlpha();
    state.viewport = renderer.getViewport(new THREE.Vector4());
    state.scissor = renderer.getScissor(new THREE.Vector4());
    state.scissorTest = renderer.getScissorTest();
    return state;
  };
  const writeState = (state) => {
    for (const field of SWAPPED_FIELDS) renderer[field] = state[field];
    for (const field of SWAPPED_SHADOW_FIELDS) renderer.shadowMap[field] = state.shadowMap[field];
    renderer.setClearColor(state.clearColor, state.clearAlpha);
    renderer.setViewport(state.viewport);
    renderer.setScissor(state.scissor);
    renderer.setScissorTest(state.scissorTest);
  };
  // The renderer's state as a fresh renderer has it: every view starts from it.
  const initialState = readState();

  const present = () => {
    presentQueued = false;
    const view = pending;
    pending = null;
    if (!view || view.released || gl.isContextLost()) return;
    const bitmap = canvas.transferToImageBitmap();
    view.bitmapContext.transferFromImageBitmap(bitmap);
  };
  // A frame is several draws (a scene, its studio passes, a composite), all in one task: it is
  // handed over once they are done.
  const framePresented = (view) => {
    if (pending && pending !== view) present();
    pending = view;
    if (!presentQueued) {
      presentQueued = true;
      queueMicrotask(present);
    }
  };

  const activate = (view) => {
    if (active === view) return;
    if (pending && pending !== view) present();
    if (active && !active.released) active.state = readState();
    active = view;
    const { width, height, pixelRatio } = view.size;
    const bufferWidth = Math.max(1, Math.floor(width * pixelRatio));
    const bufferHeight = Math.max(1, Math.floor(height * pixelRatio));
    if (canvas.width !== bufferWidth || canvas.height !== bufferHeight || renderer.getPixelRatio() !== pixelRatio) {
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(width, height, false);
    }
    writeState(view.state);
  };

  // The views hear of a lost or restored context on their own canvases, as from their own renderer.
  canvas.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    for (const view of views) view.canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
  }, false);
  canvas.addEventListener("webglcontextrestored", () => {
    active = null;
    for (const view of views) view.canvas.dispatchEvent(new Event("webglcontextrestored"));
  }, false);

  // Read-only debug/test seam: what the device holds, and for how many views.
  const stats = () => ({ views: views.size, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures,
    programs: renderer.info.programs?.length ?? 0, buffer: [canvas.width, canvas.height] });
  if (typeof window !== "undefined") window.__cadGpuDevice = stats;
  const device = {
    THREE,
    renderer,
    canvas,
    disposed: false,
    get viewCount() { return views.size; },
    activeView: () => active,
    retain() {
      users += 1;
      if (graceTimer) { clearTimeout(graceTimer); graceTimer = 0; }
    },
    release() {
      users = Math.max(0, users - 1);
      if (users > 0 || device.disposed) return;
      graceTimer = setTimeout(() => {
        graceTimer = 0;
        if (users > 0) return;
        device.disposed = true;
        if (shared === device) shared = null;
        // What the views shared besides the renderer (a studio environment cache) goes with it.
        device.onDispose?.();
        if (typeof window !== "undefined" && window.__cadGpuDevice === stats) delete window.__cadGpuDevice;
        renderer.dispose();
        if (!gl.isContextLost()) renderer.forceContextLoss();
      }, DEVICE_GRACE_MS);
      // Nothing waits on it: a page or process with nothing else to do may end before it fires.
      graceTimer.unref?.();
    },
    /** A renderer handle for the view drawn on `canvas` (see the head of this file). */
    createView(viewCanvas) {
      const bitmapContext = viewCanvas.getContext("bitmaprenderer");
      if (!bitmapContext) throw new Error("This canvas cannot show the GPU device's frames.");
      const view = {
        canvas: viewCanvas,
        bitmapContext,
        size: { width: 1, height: 1, pixelRatio: 1 },
        state: { ...initialState, shadowMap: { ...initialState.shadowMap },
          clearColor: initialState.clearColor.clone(), viewport: initialState.viewport.clone(),
          scissor: initialState.scissor.clone() },
        released: false,
      };
      views.add(view);
      return createViewHandle(device, view, { activate, framePresented, release: () => {
        if (view.released) return;
        view.released = true;
        views.delete(view);
        if (pending === view) pending = null;
        // The drawing buffer was this view's size: it goes to nothing until the next view draws,
        // which sizes it for itself (each view's canvas keeps the picture it was handed).
        if (active === view) {
          active = null;
          renderer.setPixelRatio(1);
          renderer.setSize(1, 1, false);
        }
        device.release();
      } });
    },
  };
  return device;
}

function createViewHandle(device, view, { activate, framePresented, release }) {
  const { renderer, canvas: drawingCanvas, THREE } = device;
  // Whether this view's state is the one in the renderer just now; otherwise it is kept aside.
  const current = () => device.activeView() === view;
  const use = () => activate(view);

  const shadowMap = new Proxy(renderer.shadowMap, {
    get(target, field) {
      if (SWAPPED_SHADOW_FIELDS.includes(field)) return current() ? target[field] : view.state.shadowMap[field];
      const value = target[field];
      return typeof value === "function" ? (...args) => { use(); return value.apply(target, args); } : value;
    },
    set(target, field, value) {
      if (SWAPPED_SHADOW_FIELDS.includes(field) && !current()) view.state.shadowMap[field] = value;
      else target[field] = value;
      return true;
    },
  });

  const setViewSize = (width, height, pixelRatio, updateStyle) => {
    view.size = { width: Math.max(1, width), height: Math.max(1, height), pixelRatio };
    // Sizing a canvas clears what it shows: only a real change does, and the frame that follows
    // in the same task hands it its picture again.
    const bufferWidth = Math.max(1, Math.floor(view.size.width * pixelRatio));
    const bufferHeight = Math.max(1, Math.floor(view.size.height * pixelRatio));
    if (view.canvas.width !== bufferWidth) view.canvas.width = bufferWidth;
    if (view.canvas.height !== bufferHeight) view.canvas.height = bufferHeight;
    if (updateStyle && view.canvas.style) {
      view.canvas.style.width = `${view.size.width}px`;
      view.canvas.style.height = `${view.size.height}px`;
    }
    if (current()) {
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(view.size.width, view.size.height, false);
    } else {
      view.state.viewport = new THREE.Vector4(0, 0, view.size.width, view.size.height);
      view.state.scissor = new THREE.Vector4(0, 0, view.size.width, view.size.height);
    }
  };
  const vector4 = (x, y, width, height) => (x?.isVector4 ? x.clone() : new THREE.Vector4(x, y, width, height));

  const own = {
    domElement: view.canvas,
    drawingCanvas,
    sharedDevice: device,
    setSize(width, height, updateStyle = true) { setViewSize(width, height, view.size.pixelRatio, updateStyle); },
    setPixelRatio(pixelRatio) { setViewSize(view.size.width, view.size.height, pixelRatio, false); },
    setDrawingBufferSize(width, height, pixelRatio) { setViewSize(width, height, pixelRatio, false); },
    getSize(target) { return target.set(view.size.width, view.size.height); },
    getPixelRatio() { return view.size.pixelRatio; },
    getDrawingBufferSize(target) {
      return target.set(Math.floor(view.size.width * view.size.pixelRatio), Math.floor(view.size.height * view.size.pixelRatio));
    },
    getClearColor(target) { return current() ? renderer.getClearColor(target) : target.copy(view.state.clearColor); },
    getClearAlpha() { return current() ? renderer.getClearAlpha() : view.state.clearAlpha; },
    setClearColor(color, alpha) {
      if (current()) { renderer.setClearColor(color, alpha); return; }
      view.state.clearColor = new THREE.Color(color);
      if (alpha !== undefined) view.state.clearAlpha = alpha;
    },
    setClearAlpha(alpha) { if (current()) renderer.setClearAlpha(alpha); else view.state.clearAlpha = alpha; },
    getViewport(target) { return current() ? renderer.getViewport(target) : target.copy(view.state.viewport); },
    setViewport(x, y, width, height) {
      if (current()) renderer.setViewport(x, y, width, height); else view.state.viewport = vector4(x, y, width, height);
    },
    getScissor(target) { return current() ? renderer.getScissor(target) : target.copy(view.state.scissor); },
    setScissor(x, y, width, height) {
      if (current()) renderer.setScissor(x, y, width, height); else view.state.scissor = vector4(x, y, width, height);
    },
    getScissorTest() { return current() ? renderer.getScissorTest() : view.state.scissorTest; },
    setScissorTest(value) { if (current()) renderer.setScissorTest(value); else view.state.scissorTest = value; },
    render(scene, camera) {
      use();
      const toCanvas = renderer.getRenderTarget() === null;
      renderer.render(scene, camera);
      if (toCanvas) framePresented(view);
    },
    clear(color, depth, stencil) {
      use();
      const toCanvas = renderer.getRenderTarget() === null;
      renderer.clear(color, depth, stencil);
      if (toCanvas) framePresented(view);
    },
    getContext() { return renderer.getContext(); },
    // The device is not the view's to end: letting go of the view is.
    dispose() { release(); },
    forceContextLoss() {},
  };

  return new Proxy(renderer, {
    get(target, field) {
      if (field === "shadowMap") return shadowMap;
      if (Object.prototype.hasOwnProperty.call(own, field)) return own[field];
      if (SWAPPED_FIELDS.includes(field)) return current() ? target[field] : view.state[field];
      const value = target[field];
      if (typeof value === "function") return (...args) => { use(); return value.apply(target, args); };
      return value;
    },
    set(target, field, value) {
      if (SWAPPED_FIELDS.includes(field) && !current()) view.state[field] = value;
      else target[field] = value;
      return true;
    },
  });
}
