import assert from "node:assert/strict";
import test from "node:test";

import {
  canvasToBlob,
  dataUrlToBlob,
  flipPixelsVertically,
  normalizeScreenshotCrop,
  paintScreenshotImageData,
  paintScreenshotSourceCanvas,
  resolveElementBackgroundColor
} from "./screenshotCapture.js";

function replaceGlobal(name, value) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value
  });
  return () => {
    if (descriptor) {
      Object.defineProperty(globalThis, name, descriptor);
      return;
    }
    delete globalThis[name];
  };
}

test("dataUrlToBlob decodes base64 payloads and mime types", async () => {
  const blob = dataUrlToBlob("data:text/plain;base64,aGVsbG8=");

  assert.equal(blob.type, "text/plain");
  assert.equal(await blob.text(), "hello");
  assert.throws(() => dataUrlToBlob("not-a-data-url"), /Screenshot capture failed/);
});

test("canvasToBlob uses native canvas blobs and falls back to data URLs", async () => {
  const nativeBlob = new Blob(["native"], { type: "image/png" });
  const fromNative = await canvasToBlob({
    toBlob(callback, type) {
      assert.equal(type, "image/png");
      callback(nativeBlob);
    }
  });
  assert.equal(fromNative, nativeBlob);

  const fromDataUrl = await canvasToBlob({
    toDataURL(type) {
      assert.equal(type, "image/png");
      return "data:text/plain;base64,ZmFsbGJhY2s=";
    }
  });
  assert.equal(await fromDataUrl.text(), "fallback");
});

test("flipPixelsVertically reverses image rows without mutating source pixels", () => {
  const pixels = new Uint8Array([
    1, 2, 3, 4,
    5, 6, 7, 8,
    9, 10, 11, 12,
    13, 14, 15, 16
  ]);

  assert.deepEqual([...flipPixelsVertically(pixels, 2, 2)], [
    9, 10, 11, 12,
    13, 14, 15, 16,
    1, 2, 3, 4,
    5, 6, 7, 8
  ]);
  assert.deepEqual([...pixels], [
    1, 2, 3, 4,
    5, 6, 7, 8,
    9, 10, 11, 12,
    13, 14, 15, 16
  ]);
});

test("normalizeScreenshotCrop clamps crop rectangles to the source frame", () => {
  assert.deepEqual(normalizeScreenshotCrop(null, 20, 12), {
    x: 0,
    y: 0,
    width: 20,
    height: 12,
    isFullFrame: true
  });
  assert.deepEqual(normalizeScreenshotCrop({ x: 4.8, y: 2.2, width: 50, height: 6 }, 20, 12), {
    x: 4,
    y: 2,
    width: 16,
    height: 6,
    isFullFrame: false
  });
});

test("paintScreenshotImageData flattens transparent captures over a provided background", () => {
  const events = [];
  const imageData = { id: "webgl-pixels" };
  const overlayCanvas = { id: "overlay" };
  const imageCanvas = {
    id: "image-canvas",
    width: 0,
    height: 0,
    getContext(type) {
      assert.equal(type, "2d");
      return {
        putImageData(value, x, y) {
          events.push(["image.putImageData", value.id, x, y]);
        }
      };
    }
  };
  const context = {
    fillStyle: "#111111",
    fillRect(x, y, width, height) {
      events.push(["main.fillRect", this.fillStyle, x, y, width, height]);
    },
    drawImage(canvas, ...args) {
      events.push(["main.drawImage", canvas.id, ...args]);
    },
    putImageData() {
      events.push(["main.putImageData"]);
    }
  };

  paintScreenshotImageData(context, imageData, 24, 16, {
    backgroundColor: "rgb(250, 251, 252)",
    overlayCanvas,
    createCanvas: () => imageCanvas
  });

  assert.equal(imageCanvas.width, 24);
  assert.equal(imageCanvas.height, 16);
  assert.equal(context.fillStyle, "#111111");
  assert.deepEqual(events, [
    ["image.putImageData", "webgl-pixels", 0, 0],
    ["main.fillRect", "rgb(250, 251, 252)", 0, 0, 24, 16],
    ["main.drawImage", "image-canvas", 0, 0, 24, 16, 0, 0, 24, 16],
    ["main.drawImage", "overlay", 0, 0, 24, 16, 0, 0, 24, 16]
  ]);
});

test("paintScreenshotImageData preserves direct image data path without a background", () => {
  const events = [];
  const imageData = { id: "webgl-pixels" };
  const context = {
    putImageData(value, x, y) {
      events.push(["putImageData", value.id, x, y]);
    },
    drawImage(canvas, sx, sy, sw, sh, dx, dy, dw, dh) {
      events.push(["drawImage", canvas.id, sx, sy, sw, sh, dx, dy, dw, dh]);
    }
  };

  paintScreenshotImageData(context, imageData, 10, 8, {
    overlayCanvas: { id: "overlay" }
  });

  assert.deepEqual(events, [
    ["putImageData", "webgl-pixels", 0, 0],
    ["drawImage", "overlay", 0, 0, 10, 8, 0, 0, 10, 8]
  ]);
});

test("paintScreenshotImageData crops render and overlay pixels to the visible viewport", () => {
  const events = [];
  const imageData = { id: "webgl-pixels" };
  const imageCanvas = {
    id: "image-canvas",
    width: 0,
    height: 0,
    getContext() {
      return {
        putImageData(value, x, y) {
          events.push(["image.putImageData", value.id, x, y]);
        }
      };
    }
  };
  const context = {
    fillStyle: "#111111",
    putImageData() {
      events.push(["main.putImageData"]);
    },
    fillRect() {
      events.push(["main.fillRect"]);
    },
    drawImage(canvas, sx, sy, sw, sh, dx, dy, dw, dh) {
      events.push(["main.drawImage", canvas.id, sx, sy, sw, sh, dx, dy, dw, dh]);
    }
  };

  paintScreenshotImageData(context, imageData, 100, 60, {
    crop: { x: 8, y: 12, width: 70, height: 40 },
    overlayCanvas: { id: "overlay" },
    createCanvas: () => imageCanvas
  });

  assert.deepEqual(events, [
    ["image.putImageData", "webgl-pixels", 0, 0],
    ["main.drawImage", "image-canvas", 8, 12, 70, 40, 0, 0, 70, 40],
    ["main.drawImage", "overlay", 8, 12, 70, 40, 0, 0, 70, 40]
  ]);
});

test("paintScreenshotSourceCanvas copies the live framebuffer crop and overlays drawings", () => {
  const events = [];
  const context = {
    fillStyle: "#111111",
    fillRect(x, y, width, height) {
      events.push(["fillRect", this.fillStyle, x, y, width, height]);
    },
    drawImage(canvas, ...args) {
      events.push(["drawImage", canvas.id, ...args]);
    }
  };

  paintScreenshotSourceCanvas(context, { id: "webgl-canvas" }, 100, 60, {
    backgroundColor: "rgb(13, 17, 23)",
    crop: { x: 5, y: 7, width: 70, height: 40 },
    overlayCanvas: { id: "overlay" }
  });

  assert.equal(context.fillStyle, "#111111");
  assert.deepEqual(events, [
    ["fillRect", "rgb(13, 17, 23)", 0, 0, 70, 40],
    ["drawImage", "webgl-canvas", 5, 7, 70, 40, 0, 0, 70, 40],
    ["drawImage", "overlay", 5, 7, 70, 40, 0, 0, 70, 40]
  ]);
});

test("resolveElementBackgroundColor walks to the first opaque computed background", () => {
  const body = { name: "body", parentElement: null };
  const parent = { name: "parent", parentElement: body };
  const canvas = { name: "canvas", parentElement: parent };
  const colors = new Map([
    [canvas, "rgba(0, 0, 0, 0)"],
    [parent, "transparent"],
    [body, "rgb(248, 250, 252)"]
  ]);
  const restoreWindow = replaceGlobal("window", {
    getComputedStyle(element) {
      return { backgroundColor: colors.get(element) || "transparent" };
    }
  });
  const restoreDocument = replaceGlobal("document", { body });

  try {
    assert.equal(resolveElementBackgroundColor(canvas), "rgb(248, 250, 252)");
    colors.set(parent, "rgb(15, 23, 42)");
    assert.equal(resolveElementBackgroundColor(canvas), "rgb(15, 23, 42)");
    colors.set(parent, "rgb(255, 255, 0)");
    assert.equal(resolveElementBackgroundColor(canvas), "rgb(255, 255, 0)");
  } finally {
    restoreDocument();
    restoreWindow();
  }
});
