import assert from "node:assert/strict";
import test from "node:test";
import { GESTURE_GAP_MS, createWheelGesture, isTrackpadScroll } from "./wheelGesture.js";

const wheel = (props) => ({ deltaX: 0, deltaY: 0, deltaMode: 0, ctrlKey: false, metaKey: false, ...props });

test("a trackpad's scroll is told from a mouse's wheel, a pinch and a modifier zoom", () => {
  // Chrome and Safari: a trackpad's legacy delta is -3 times its delta; a mouse's notch is 120.
  assert.equal(isTrackpadScroll(wheel({ deltaY: 4, wheelDeltaY: -12 })), true);
  assert.equal(isTrackpadScroll(wheel({ deltaY: 100, wheelDeltaY: -120 })), false);
  assert.equal(isTrackpadScroll(wheel({ deltaY: 4.5, wheelDeltaY: -120 })), false);
  // Sideways is a trackpad; a mouse that counts lines (Firefox) is a mouse.
  assert.equal(isTrackpadScroll(wheel({ deltaX: 3, deltaY: 1 })), true);
  assert.equal(isTrackpadScroll(wheel({ deltaY: 3, deltaMode: 1 })), false);
  // No legacy delta: a whole notch is a mouse's, a fine step a trackpad's.
  assert.equal(isTrackpadScroll(wheel({ deltaY: 100 })), false);
  assert.equal(isTrackpadScroll(wheel({ deltaY: 2.25 })), true);
  // A pinch (ctrl-wheel) and Cmd held are zooms.
  assert.equal(isTrackpadScroll(wheel({ deltaY: 2, ctrlKey: true })), false);
  assert.equal(isTrackpadScroll(wheel({ deltaY: 2, metaKey: true })), false);
});

test("a gesture is read at its start and kept through its momentum; a pinch zooms whenever it comes", () => {
  let now = 0;
  const read = createWheelGesture({ now: () => now });
  // A two-finger scroll pans with the fingers, both ways at once.
  assert.deepEqual(read(wheel({ deltaX: 2, deltaY: 5 })), { pan: { x: -2, y: -5 } });
  // Its momentum tail grows coarse, and is still the pan.
  now += 16;
  assert.deepEqual(read(wheel({ deltaY: 60 })), { pan: { x: 0, y: -60 } });
  now += 16;
  assert.deepEqual(read(wheel({ deltaY: 3, ctrlKey: true })), { zoom: 3, pinch: true });
  // After a rest, a mouse's notch is a zoom.
  now += GESTURE_GAP_MS + 1;
  assert.deepEqual(read(wheel({ deltaY: 100, wheelDeltaY: -120 })), { zoom: 100, pinch: false });
  now += 16;
  assert.deepEqual(read(wheel({ deltaY: 3, deltaMode: 1 })), { zoom: 48, pinch: false });
});
