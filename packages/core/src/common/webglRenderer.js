export function cadWebGlRendererAttributes({
  stencil = true,
  alpha = true,
  antialias = true,
  powerPreference = "high-performance",
  preserveDrawingBuffer = false,
  logarithmicDepthBuffer = true
} = {}) {
  return {
    stencil,
    alpha,
    antialias,
    powerPreference,
    preserveDrawingBuffer,
    logarithmicDepthBuffer
  };
}

export function fallbackCadWebGlRendererAttributes(options = {}) {
  return {
    ...cadWebGlRendererAttributes(options),
    antialias: false,
    powerPreference: "default",
    logarithmicDepthBuffer: false
  };
}

function createCanvas() {
  return typeof document === "undefined" ? undefined : document.createElement("canvas");
}

// A renderer whose constructor threw has no `dispose()` to call: the canvas it was given is
// the only handle left on whatever context it managed to create before failing. Ask the canvas
// for that context (the same one comes back) and lose it, so the failed attempt does not hold
// a GPU context until garbage collection.
//
// Why this asks for a context without making one: `getContext(type)` on a canvas that already
// has a context of that type returns that same object, and on a canvas whose creation of that
// type failed it returns null again. Three (pinned at 0.186.1) asks for "webgl2" and only
// "webgl2" (`WebGLRenderer.js`, `contextName`), so this call either gets three's own context
// back or null. It must ask for the same single type: a canvas that failed "webgl2" has no
// context mode yet, and a second `getContext("webgl")` here would try to create a WebGL 1
// context three never asked for, only to lose it. If three ever tries another type, add that
// one here, in three's order.
function releaseFailedAttempt(canvas) {
  try {
    const context = canvas?.getContext?.("webgl2");
    context?.getExtension?.("WEBGL_lose_context")?.loseContext?.();
  } catch {
    // Nothing to release, or the context is already gone.
  }
}

export function createCadWebGlRenderer(THREE, {
  allowFallback = false,
  isRecoverableError = () => true,
  createCanvas: makeCanvas = createCanvas,
  ...options
} = {}) {
  // The canvas is ours, not three's, so a failed first attempt can still be released.
  const firstCanvas = makeCanvas();
  try {
    return new THREE.WebGLRenderer({
      ...cadWebGlRendererAttributes(options),
      ...(firstCanvas ? { canvas: firstCanvas } : {})
    });
  } catch (error) {
    releaseFailedAttempt(firstCanvas);
    if (!allowFallback || !isRecoverableError(error)) {
      throw error;
    }
    const fallbackCanvas = makeCanvas();
    return new THREE.WebGLRenderer({
      ...fallbackCadWebGlRendererAttributes(options),
      ...(fallbackCanvas ? { canvas: fallbackCanvas } : {})
    });
  }
}
