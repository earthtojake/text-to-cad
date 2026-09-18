import path from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "electron";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export function appVersion(): string {
  return app.isPackaged ? app.getVersion() : __APP_VERSION__;
}

/** `apps/desktop` in a checkout; the asar's root when packaged. */
export function appRoot(): string {
  // out/main/index.js -> apps/desktop (or app.asar/out/main -> app.asar)
  return path.resolve(dirname, "..", "..");
}

/** `resources/` in a checkout, `Contents/Resources` (process.resourcesPath) packaged. */
export function resourcesDir(): string {
  return app.isPackaged ? process.resourcesPath : path.join(appRoot(), "resources");
}
