// A runtime with a REAL three OrbitControls, for the tests that must notice when three
// renames a field we reach into. The element is a stub: it keeps the listeners the controls
// add, which is all `update()` and a synthetic drag need.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

function stubElement() {
  const listeners = new Map();
  const target = {
    addEventListener(type, fn, options) {
      listeners.set(type, [...(listeners.get(type) || []), { fn, capture: Boolean(options?.capture) }]);
    },
    removeEventListener(type, fn) { listeners.set(type, (listeners.get(type) || []).filter(item => item.fn !== fn)); },
    // At the target, capture listeners run first, then the rest in the order they were added.
    dispatch(type, event) {
      const held = listeners.get(type) || [];
      for (const { fn } of [...held.filter(item => item.capture), ...held.filter(item => !item.capture)]) fn(event);
    },
    style: {}, clientWidth: 800, clientHeight: 600,
    setPointerCapture() {}, releasePointerCapture() {},
    getRootNode() { return target.ownerDocument; },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 })
  };
  target.ownerDocument = { ...target, addEventListener: target.addEventListener, removeEventListener: target.removeEventListener, style: {} };
  return target;
}

/** `{ THREE, camera, perspectiveCamera, controls, drag, ... }`, damping on as the viewer runs it. */
export function createRealOrbitRuntime({ maxDistance = Infinity, minDistance = 0, autoRotate = false, position = [10, -10, 8] } = {}) {
  const element = stubElement();
  const camera = new THREE.PerspectiveCamera(45, 800 / 600, 0.1, 10_000);
  camera.up.set(0, 0, 1);
  camera.position.set(...position);
  const controls = new OrbitControls(camera, element);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.minDistance = minDistance;
  controls.maxDistance = maxDistance;
  controls.autoRotate = autoRotate;
  controls.target.set(0, 0, 0);
  camera.lookAt(controls.target);
  controls.update();
  const runtime = { THREE, camera, perspectiveCamera: camera, controls, requestRender() {}, cameraTransition: null };
  let next = 1;
  /**
   * A pointer drag, through three's own handlers: down, one move, up. Leaves damping momentum
   * behind. It rotates; with `pan` (shift held) it pans.
   */
  runtime.drag = (dx, dy = 0, { pan = false } = {}) => {
    const event = (type, x, y) => ({ pointerId: next, pointerType: "mouse", button: 0, isPrimary: true, clientX: x, clientY: y, pageX: x, pageY: y, ctrlKey: false, metaKey: false, shiftKey: pan });
    element.dispatch("pointerdown", event("down", 100, 100));
    element.ownerDocument.dispatch("pointermove", event("move", 100 + dx, 100 + dy));
    element.ownerDocument.dispatch("pointerup", event("up", 100 + dx, 100 + dy));
    next += 1;
  };
  /** A wheel event at the canvas, through every wheel listener on it (ours and three's). */
  runtime.wheel = deltaY => element.dispatch("wheel", { deltaY, deltaMode: 0, clientX: 400, clientY: 300, ctrlKey: false, preventDefault() {} });
  runtime.element = element;
  return runtime;
}
