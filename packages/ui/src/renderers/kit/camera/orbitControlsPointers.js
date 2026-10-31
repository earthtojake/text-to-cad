// three's OrbitControls (r186) records a position only for TOUCH pointers, yet its pointerup
// assumes the one pointer left after a lift is a touch: it restarts a one-finger gesture from
// `_pointerPositions[_pointers[0]].x`. Two real sequences leave a mouse or pen there instead, and
// the lift throws "Cannot read properties of undefined (reading 'x')":
//   - a finger and a pen (or mouse) both pressed on the canvas, and the finger lifts; and
//   - a mouse or pen dragging, and any OTHER pointer lifts anywhere on the page, since the
//     controls listen for pointerup on the whole document.
// The subclass keeps three's gestures as they are and fixes only those two lifts: a lift of a
// pointer the controls never took is not theirs and is ignored, and a pointer left alone without
// a position is let go, which ends the gesture as a last lift does (its own lift is then ignored).

const guardedClasses = new WeakMap();

/** `OrbitControls`, with its pointerup made safe for mixed and foreign pointers. */
export function guardedOrbitControls(OrbitControls) {
  let Guarded = guardedClasses.get(OrbitControls);
  if (!Guarded) {
    Guarded = class extends OrbitControls {
      // three's constructor binds `_onPointerUp` and then calls `connect()`, which registers it, so
      // the wrap goes in here, before the first registration. No class fields: they would run
      // after that constructor and miss it.
      connect(element) {
        if (!this._pointerUpGuarded) {
          this._pointerUpGuarded = true;
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
