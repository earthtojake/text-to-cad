const CAD_VIEWER_ACTIVE_DIR_SESSION_STORAGE_KEY = "cad-viewer:active-dir:v1";

function sessionStorageForWindow() {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage || null;
  } catch {
    return null;
  }
}

export function readStoredActiveCadDir() {
  const storage = sessionStorageForWindow();
  if (!storage) {
    return "";
  }
  try {
    return String(storage.getItem(CAD_VIEWER_ACTIVE_DIR_SESSION_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function writeStoredActiveCadDir(activeDir) {
  const storage = sessionStorageForWindow();
  if (!storage) {
    return;
  }
  const normalizedDir = String(activeDir || "").trim();
  try {
    if (normalizedDir) {
      storage.setItem(CAD_VIEWER_ACTIVE_DIR_SESSION_STORAGE_KEY, normalizedDir);
    } else {
      storage.removeItem(CAD_VIEWER_ACTIVE_DIR_SESSION_STORAGE_KEY);
    }
  } catch {
    // Storage failures should not block Viewer navigation.
  }
}

export function rememberActiveCadDir(candidateDir) {
  const normalizedCandidate = String(candidateDir || "").trim();
  writeStoredActiveCadDir(normalizedCandidate);
  return normalizedCandidate;
}
