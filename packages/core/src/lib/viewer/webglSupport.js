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

// The card shows an alert's `recovery` under its message, and files its `details` with a report: what
// the renderer said, and the browser or app the view runs in (an agent app's names it), which is most
// of what tells one WebGL failure from another.
function runtimeDetails(message) {
  const agent = String(globalThis.navigator?.userAgent || "");
  return [message, agent && `User agent: ${agent}`].filter(Boolean).join("\n");
}

export function buildRuntimeInitializationAlert(error) {
  const message = runtimeErrorMessage(error).trim();

  if (isWebGlContextCreationError(error)) {
    return {
      severity: "error",
      blocking: true,
      summary: "WebGL unavailable",
      title: "WebGL is unavailable",
      message: "CAD Viewer needs WebGL to draw 3D models, but the browser or app it runs in could not create a WebGL context.",
      // A Chromium browser or app whose GPU process crashed can keep WebGL off until it restarts.
      recovery: "Quit and reopen the browser or app this view runs in: after a graphics crash, it can keep WebGL off until it restarts. If WebGL stays unavailable, turn on hardware acceleration or update the graphics drivers. In Chrome, chrome://gpu shows WebGL's status.",
      details: runtimeDetails(message)
    };
  }

  return {
    severity: "error",
    blocking: true,
    summary: "CAD Viewer startup failed",
    title: "CAD Viewer could not start",
    message: message || "The 3D renderer failed before CAD Viewer finished starting.",
    recovery: "Reload or reopen CAD Viewer. If it fails again, report it with the details below.",
    details: runtimeDetails(message)
  };
}
