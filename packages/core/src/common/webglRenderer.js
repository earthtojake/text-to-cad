export function cadWebGlRendererAttributes({
  alpha = true,
  antialias = true,
  powerPreference = "high-performance",
  preserveDrawingBuffer = false,
  logarithmicDepthBuffer = true
} = {}) {
  return {
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

export function createCadWebGlRenderer(THREE, {
  allowFallback = false,
  isRecoverableError = () => true,
  ...options
} = {}) {
  try {
    return new THREE.WebGLRenderer(cadWebGlRendererAttributes(options));
  } catch (error) {
    if (!allowFallback || !isRecoverableError(error)) {
      throw error;
    }
    return new THREE.WebGLRenderer(fallbackCadWebGlRendererAttributes(options));
  }
}
