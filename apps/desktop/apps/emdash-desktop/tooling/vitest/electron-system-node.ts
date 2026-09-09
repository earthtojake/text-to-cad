// System-Node tests must inject any Electron-owned behavior they exercise.
// Undefined exports allow Electron-aware modules to feature-detect the unavailable runtime.
export const app = undefined;
export const safeStorage = undefined;
