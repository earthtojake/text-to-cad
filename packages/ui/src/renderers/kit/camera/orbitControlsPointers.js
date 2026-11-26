// three's OrbitControls (r186) records a position only for TOUCH pointers, yet its touch gestures
// assume every pointer they hold is a touch: a lift restarts a one-finger gesture from
// `_pointerPositions[_pointers[0]].x`, and a second press starts a two-finger one from the other
// pointer's. Three real sequences leave a mouse or pen there instead, and three throws "Cannot read
// properties of undefined (reading 'x')":
//   - a finger and a pen (or mouse) both pressed on the canvas, and the finger lifts;
//   - a mouse or pen dragging, and any OTHER pointer lifts anywhere on the page, since the
//     controls listen for pointerup on the whole document; and
//   - a pen (or mouse) dragging, and a finger (a resting palm) presses the canvas.
// Its press also captures the pointer before anything else, and `setPointerCapture` throws
// NotFoundError for a pointer the browser does not know: a synthetic press's id (an automation's),
// or one it dropped before the listener ran.
// The subclass keeps three's gestures as they are and fixes only those: a lift of a pointer the
// controls never took is not theirs and is ignored; a pointer left alone without a position is let
// go, which ends the gesture as a last lift does (its own lift is then ignored); a finger pressed
// while a mouse or pen holds the controls is not theirs; and a first press whose pointer cannot be
// captured starts nothing, since a pointer the browser does not know never lifts and would hold the
// controls for good.

import { capturePointer } from "../../../lib/pointerCapture.js";

const guardedClasses = new WeakMap();

/** `OrbitControls`, with its pointerdown and pointerup made safe for mixed, foreign and unknown pointers. */
export function guardedOrbitControls(OrbitControls) {
  let Guarded = guardedClasses.get(OrbitControls);
  if (!Guarded) {
    Guarded = class extends OrbitControls {
      // three's constructor binds `_onPointerDown` and `_onPointerUp` and then calls `connect()`,
      // which registers them, so the wraps go in here, before the first registration. No class
      // fields: they would run after that constructor and miss it.
      connect(element) {
        if (!this._pointersGuarded) {
          this._pointersGuarded = true;
          const onPointerDown = this._onPointerDown;
          this._onPointerDown = (event) => {
            if (this.enabled !== false && !this._isTrackingPointer(event)) {
              // Captured here first, as three would on a first press: where that throws, three's would.
              if (this._pointers.length === 0 && !capturePointer(this.domElement, event.pointerId)) return;
              if (event.pointerType === "touch" && this._pointers.some(id => this._pointerPositions[id] === undefined)) return;
            }
            onPointerDown(event);
          };
          const onPointerUp = this._onPointerUp;
          this._onPointerUp = (event) => {
            if (this._isTrackingPointer(event)) onPointerUp(event);
          };
        }
        super.connect(element);
      }

      _removePointer(event) {
        super._removePointer(event);
        if (this._pointers.length === 1 && this._pointerPositions[this._pointers[0]] === undefined) {
          this._pointers.length = 0;
        }
      }
    };
    guardedClasses.set(OrbitControls, Guarded);
  }
  return Guarded;
}
