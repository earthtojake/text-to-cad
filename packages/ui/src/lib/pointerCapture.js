// Pointer capture is best-effort. `setPointerCapture` throws NotFoundError for a
// pointer that is no longer active -- one lifted between the event's dispatch and
// its handler, or a synthetic event's id -- and InvalidStateError on an element
// that has left the document. A press that cannot capture still works as an
// uncaptured one, so neither may escape a pointer handler as a page crash.

export function capturePointer(element, pointerId) {
  try {
    element?.setPointerCapture?.(pointerId);
    return true;
  } catch {
    return false;
  }
}

// Released only where it is held: a capture that never took, or one the browser
// already dropped (the pointer lifted, the element left the document), has
// nothing to release, and asking throws the same NotFoundError.
export function releasePointer(element, pointerId) {
  try {
    if (element?.hasPointerCapture?.(pointerId)) element.releasePointerCapture(pointerId);
  } catch {
    // Nothing held, nothing to undo.
  }
}
