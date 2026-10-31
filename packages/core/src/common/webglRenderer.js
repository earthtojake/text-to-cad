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

// `canvas`: draw on this canvas (an OffscreenCanvas, say) rather than one the renderer creates.
export function createCadWebGlRenderer(THREE, {
  allowFallback = false,
  isRecoverableError = () => true,
  canvas = undefined,
  ...options
} = {}) {
  const on = attributes => (canvas ? { ...attributes, canvas } : attributes);
  try {
    return new THREE.WebGLRenderer(on(cadWebGlRendererAttributes(options)));
  } catch (error) {
    if (!allowFallback || !isRecoverableError(error)) {
      throw error;
    }
    return new THREE.WebGLRenderer(on(fallbackCadWebGlRendererAttributes(options)));
  }
}
