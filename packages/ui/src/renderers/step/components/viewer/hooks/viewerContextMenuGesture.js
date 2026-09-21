export const VIEWER_CONTEXT_MENU_SUPPRESSION_MS = 1200;

export function createViewerContextMenuGestureState({
  now = () => Date.now(),
  suppressionMs = VIEWER_CONTEXT_MENU_SUPPRESSION_MS
} = {}) {
  let suppressUntil = 0;

  return {
    suppressNextContextMenu() {
      suppressUntil = Math.max(suppressUntil, now() + suppressionMs);
    },
    consumeSuppression() {
      if (now() > suppressUntil) {
        suppressUntil = 0;
        return false;
      }
      suppressUntil = 0;
      return true;
    },
    clear() {
      suppressUntil = 0;
    },
    isSuppressed() {
      return now() <= suppressUntil;
    }
  };
}
