export function dataUrlToBlob(dataUrl) {
  const parts = String(dataUrl || "").split(",");
  if (parts.length !== 2) {
    throw new Error("Screenshot capture failed");
  }
  const mimeMatch = parts[0].match(/data:(.*?);base64/);
  const mimeType = mimeMatch?.[1] || "image/png";
  const binary = atob(parts[1]);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
}

export async function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => {
    if (!canvas) {
      reject(new Error("Screenshot capture failed"));
      return;
    }
    if (typeof canvas.toBlob === "function") {
      canvas.toBlob((value) => {
        if (value) {
          resolve(value);
          return;
        }
        reject(new Error("Screenshot capture failed"));
      }, "image/png");
      return;
    }

    try {
      resolve(dataUrlToBlob(canvas.toDataURL("image/png")));
    } catch (captureError) {
      reject(captureError);
    }
  });
}

export function flipPixelsVertically(pixels, width, height) {
  const rowSize = width * 4;
  const flipped = new Uint8ClampedArray(pixels.length);
  for (let row = 0; row < height; row += 1) {
    const sourceStart = (height - row - 1) * rowSize;
    const targetStart = row * rowSize;
    flipped.set(pixels.subarray(sourceStart, sourceStart + rowSize), targetStart);
  }
  return flipped;
}

export function normalizeScreenshotCrop(crop, width, height) {
  const fullWidth = Math.max(1, Math.floor(Number(width) || 1));
  const fullHeight = Math.max(1, Math.floor(Number(height) || 1));
  const x = Math.min(Math.max(0, Math.floor(Number(crop?.x) || 0)), fullWidth - 1);
  const y = Math.min(Math.max(0, Math.floor(Number(crop?.y) || 0)), fullHeight - 1);
  const maxWidth = Math.max(1, fullWidth - x);
  const maxHeight = Math.max(1, fullHeight - y);
  const cropWidth = Math.min(Math.max(1, Math.floor(Number(crop?.width) || maxWidth)), maxWidth);
  const cropHeight = Math.min(Math.max(1, Math.floor(Number(crop?.height) || maxHeight)), maxHeight);
  return {
    x,
    y,
    width: cropWidth,
    height: cropHeight,
    isFullFrame: x === 0 && y === 0 && cropWidth === fullWidth && cropHeight === fullHeight
  };
}

function isTransparentCssColor(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized || normalized === "transparent") {
    return true;
  }
  if (/^[a-z]+\(\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*0(?:\.0+)?%?\s*\)$/.test(normalized)) {
    return true;
  }
  return /^[a-z]+\([^)]*\/\s*0(?:\.0+)?%?\s*\)$/.test(normalized);
}

export function resolveElementBackgroundColor(element, fallback = "#ffffff") {
  const getComputedStyle = globalThis.window?.getComputedStyle || globalThis.getComputedStyle;
  let current = element || null;
  const visited = new Set();

  while (current && !visited.has(current)) {
    visited.add(current);
    const backgroundColor = typeof getComputedStyle === "function"
      ? getComputedStyle(current)?.backgroundColor
      : "";
    if (!isTransparentCssColor(backgroundColor)) {
      return backgroundColor;
    }
    current = current.parentElement || null;
  }

  const body = globalThis.document?.body || null;
  if (body && !visited.has(body) && typeof getComputedStyle === "function") {
    const backgroundColor = getComputedStyle(body)?.backgroundColor;
    if (!isTransparentCssColor(backgroundColor)) {
      return backgroundColor;
    }
  }

  return fallback;
}

export function paintScreenshotImageData(context, imageData, width, height, {
  backgroundColor = "",
  crop = null,
  overlayCanvas = null,
  createCanvas = () => globalThis.document?.createElement?.("canvas")
} = {}) {
  if (!context) {
    throw new Error("Screenshot capture failed");
  }

  const cropRect = normalizeScreenshotCrop(crop, width, height);
  const resolvedBackground = String(backgroundColor || "").trim();
  if (resolvedBackground || !cropRect.isFullFrame) {
    const imageCanvas = createCanvas();
    imageCanvas.width = width;
    imageCanvas.height = height;
    const imageContext = imageCanvas.getContext("2d");
    if (!imageContext) {
      throw new Error("Screenshot capture failed");
    }
    imageContext.putImageData(imageData, 0, 0);

    const previousFillStyle = context.fillStyle;
    context.fillStyle = "#ffffff";
    context.fillStyle = resolvedBackground;
    if (resolvedBackground) {
      context.fillRect(0, 0, cropRect.width, cropRect.height);
    }
    context.drawImage(
      imageCanvas,
      cropRect.x,
      cropRect.y,
      cropRect.width,
      cropRect.height,
      0,
      0,
      cropRect.width,
      cropRect.height
    );
    context.fillStyle = previousFillStyle;
  } else {
    context.putImageData(imageData, 0, 0);
  }

  if (overlayCanvas) {
    context.drawImage(
      overlayCanvas,
      cropRect.x,
      cropRect.y,
      cropRect.width,
      cropRect.height,
      0,
      0,
      cropRect.width,
      cropRect.height
    );
  }
}

export function paintScreenshotSourceCanvas(context, sourceCanvas, width, height, {
  backgroundColor = "",
  crop = null,
  overlayCanvas = null
} = {}) {
  if (!context || !sourceCanvas) {
    throw new Error("Screenshot capture failed");
  }

  const cropRect = normalizeScreenshotCrop(crop, width, height);
  const resolvedBackground = String(backgroundColor || "").trim();
  const previousFillStyle = context.fillStyle;
  if (resolvedBackground) {
    context.fillStyle = "#ffffff";
    context.fillStyle = resolvedBackground;
    context.fillRect(0, 0, cropRect.width, cropRect.height);
  }
  context.drawImage(
    sourceCanvas,
    cropRect.x,
    cropRect.y,
    cropRect.width,
    cropRect.height,
    0,
    0,
    cropRect.width,
    cropRect.height
  );
  context.fillStyle = previousFillStyle;

  if (overlayCanvas) {
    context.drawImage(
      overlayCanvas,
      cropRect.x,
      cropRect.y,
      cropRect.width,
      cropRect.height,
      0,
      0,
      cropRect.width,
      cropRect.height
    );
  }
}

// Render the live framebuffer once and immediately copy it into a 2D export
// canvas, keeping normal interaction free to use `preserveDrawingBuffer: false`.
export async function buildCompositeScreenshotBlob(runtime, overlayCanvas, {
  backgroundColor = "",
  crop = null
} = {}) {
  const renderer = runtime?.renderer;
  const scene = runtime?.scene;
  const camera = runtime?.camera;
  const width = renderer?.domElement?.width || 0;
  const height = renderer?.domElement?.height || 0;
  if (!renderer || !scene || !camera || width <= 0 || height <= 0) {
    throw new Error("Screenshot capture failed");
  }

  const previousRenderTarget = renderer.getRenderTarget();
  const previousXrEnabled = renderer.xr?.enabled === true;
  try {
    if (renderer.xr) {
      renderer.xr.enabled = false;
    }
    renderer.setRenderTarget(null);
    renderer.render(scene, camera);
  } finally {
    renderer.setRenderTarget(previousRenderTarget);
    if (renderer.xr) {
      renderer.xr.enabled = previousXrEnabled;
    }
  }

  const cropRect = normalizeScreenshotCrop(crop, width, height);
  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = cropRect.width;
  exportCanvas.height = cropRect.height;
  const context = exportCanvas.getContext("2d");
  if (!context) {
    throw new Error("Screenshot capture failed");
  }

  paintScreenshotSourceCanvas(context, renderer.domElement, width, height, {
    backgroundColor,
    crop: cropRect,
    overlayCanvas
  });
  return canvasToBlob(exportCanvas);
}
