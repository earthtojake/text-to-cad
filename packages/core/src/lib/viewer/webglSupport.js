const WEBGL_CONTEXT_ERROR_PATTERN = /(?:error creating webgl context|webgl context could not be created|failed to create webgl|webgl is not supported)/i;
const SOFTWARE_WEBGL_RENDERER_PATTERN = /(?:swiftshader|llvmpipe|softpipe|software rasterizer|lavapipe)/i;

export function runtimeErrorMessage(error) {
  return error instanceof Error ? error.message : String(error || "");
}

export function isWebGlContextCreationError(error) {
  return WEBGL_CONTEXT_ERROR_PATTERN.test(runtimeErrorMessage(error));
}

export function isSoftwareWebGlRenderer(renderer) {
  const context = renderer?.getContext?.();
  if (!context) {
    return false;
  }

  let rendererName = "";
  try {
    const debugInfo = context.getExtension?.("WEBGL_debug_renderer_info");
    const rendererParameter = debugInfo?.UNMASKED_RENDERER_WEBGL ?? context.RENDERER;
    rendererName = String(context.getParameter?.(rendererParameter) || "");
  } catch {
    return false;
  }
  return SOFTWARE_WEBGL_RENDERER_PATTERN.test(rendererName);
}

export function buildRuntimeInitializationAlert(error) {
  const message = runtimeErrorMessage(error).trim();

  if (isWebGlContextCreationError(error)) {
    return {
      severity: "error",
      blocking: true,
      summary: "WebGL unavailable",
      title: "Browser WebGL is unavailable",
      message: "CAD Viewer needs browser WebGL to render 3D models, but this browser could not create a WebGL context.",
      resolution: "Enable hardware acceleration or software WebGL in the browser, update the graphics or Mesa drivers, then reload CAD Viewer. In Chrome, check chrome://gpu for the WebGL status."
    };
  }

  return {
    severity: "error",
    blocking: true,
    summary: "CAD Viewer startup failed",
    title: "CAD Viewer could not start",
    message: message || "The 3D renderer failed before CAD Viewer finished starting.",
    resolution: "Reload CAD Viewer. If the problem persists, check the browser console for the renderer startup error."
  };
}
