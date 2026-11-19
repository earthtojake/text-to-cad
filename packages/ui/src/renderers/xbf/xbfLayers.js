// An app's own layers over an engine document's view (`XbfRendererOptions.layers`,
// `docs/viewer-host.md`, Model view layers): each is drawn over the model's canvas beside the view's
// own overlays, handed the scene and the viewport, and offered each click on the model before
// Select takes it. A layer that claims a click keeps the view's selection as it was.

/**
 * The clicks the layers claim. `claim(handler)` offers each click to `handler(hit, modifiers)` until
 * the function it returns is called; `offer(hit, modifiers)` asks each in the order they claimed and
 * is true once one returns true, which the view then leaves alone. `hit` is what the click found on
 * the model (a part, or a face or an edge by its id and `kind`), null over empty space.
 */
export function createPickClaims() {
  const handlers = new Set();
  return {
    claim(handler) {
      handlers.add(handler);
      return () => { handlers.delete(handler); };
    },
    offer(hit, modifiers) {
      for (const handler of handlers) if (handler(hit, modifiers) === true) return true;
      return false;
    }
  };
}
