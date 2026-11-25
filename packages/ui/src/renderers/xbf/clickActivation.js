import { DOUBLE_CLICK_WAIT_MS } from "../kit/viewport/touchGestures.js";

/**
 * Which tap of a click sequence activates what it picked, and when: an engine document's Select
 * (`XbfRenderer.jsx`'s `XbfPick`), by the rules a STEP's Select kept.
 *
 * A click acts at once: nothing waits to tell it from a double-click. What makes that safe
 * is the browser's own count. The second click of a double-click (a press the browser counts
 * as the second, `MouseEvent.detail` 2) is dispatched a moment before the `dblclick` that
 * owns the gesture, so its activation is held for one turn of the task queue and `double()`
 * cancels it; a second click the browser pairs with nothing commits after that turn, as the
 * click it turned out to be. The double-click is then told whether the gesture's FIRST click
 * activated (`double()` returns it), so the surface can put back the selection that click
 * changed before it isolates, leaves isolation or looks at a face or edge — the gesture ends as it did when
 * every click waited.
 *
 * A tap still waits the double-click window (`tap(..., { wait: true, waitMs })`) where what it does
 * would have to be undone: one that would take a selection away (the thing selected pressed again:
 * `XbfRenderer.jsx`'s `pickTakesAway`), so a double-click never shows the selection going and coming
 * back. A press on empty space clears at once: what a double-click there does (fit, leave isolation)
 * needs no selection. Explode and Clip stand over Select, so a tap under them picks as Select's does
 * and the tool stays in hand. A lone click that waits acts once the window has passed. A finger's
 * window is its double tap's.
 *
 * `tap(clickCount, referenceId, options, { wait })`: a press released within the tap slop;
 * `miss(clickCount)`: a press that was not one (a drag, a cancel, a chord), which for a fresh
 * gesture (count 1) forgets any earlier click; `double()`: the dblclick; `cancel()`: drop a
 * held tap.
 */
// The kit's window, the one every selecting view's take-away click waits (`usePointerPick`).
export const VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS = DOUBLE_CLICK_WAIT_MS;

export function createClickActivation({
  commit,
  doubleClick = true,
  defer = (fn, ms) => window.setTimeout(fn, ms),
  cancel = (id) => window.clearTimeout(id)
}) {
  let heldId = 0;
  // Whether this gesture's first click activated: what a following double-click undoes.
  let activated = false;

  function drop() {
    if (!heldId) return;
    cancel(heldId);
    heldId = 0;
  }

  function hold(referenceId, options, ms) {
    heldId = defer(() => {
      heldId = 0;
      activated = true;
      commit(referenceId, options);
    }, ms);
  }

  return {
    tap(clickCount, referenceId, options, { wait = false, waitMs = VIEWER_DOUBLE_CLICK_ACTIVATION_DELAY_MS } = {}) {
      drop();
      if (!doubleClick) {
        activated = true;
        commit(referenceId, options);
        return;
      }
      if (wait) {
        hold(referenceId, options, waitMs);
        return;
      }
      if (!(clickCount >= 2)) {
        activated = true;
        commit(referenceId, options);
        return;
      }
      hold(referenceId, options, 0);
    },
    miss(clickCount) {
      drop();
      if (!(clickCount >= 2)) activated = false;
    },
    double() {
      drop();
      const first = activated;
      activated = false;
      return first;
    },
    cancel: drop
  };
}
