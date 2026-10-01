import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect } from "@playwright/test";

const version = fs.readFileSync(new URL("../../../../VERSION", import.meta.url), "utf8").trim();

/** Python multiprocessing adds socket suffixes; macOS's normal temp path is too long once nested. */
export function cadTestProfile(name: string) {
  return fs.mkdtempSync(path.join(process.platform === "win32" ? os.tmpdir() : "/tmp", `hc-${name}-`));
}

/** The Viewer registry lives under the process temp directory, independently of its cache. */
export function cadRegistryEnvironment(profile: string) {
  return { TMPDIR: profile, TEMP: profile, TMP: profile };
}

/**
 * Local UI-only runs may omit Python; CAD qualification must never silently skip it.
 * The CAD spec compiles a STEP, so a runtime that is ready with a CAD kernel
 * warning (`missing`, `unsupported` — GLB/STL/DXF would open, a STEP may not
 * build) is not ready for it.
 */
export function cadRuntimeReady(status: { state: string; cadgenVersion: string | null; kernel?: { state: string; message: string } }) {
  if (process.env.TEXT_TO_CAD_E2E_REQUIRE_CAD === "1") {
    expect(status.state, `CAD qualification requires a ready runtime: ${JSON.stringify(status)}`).toBe("ready");
    expect(status.kernel, `CAD qualification requires a CAD kernel cadgen builds with: ${JSON.stringify(status)}`).toBeUndefined();
    expect(status.cadgenVersion, "CAD qualification must use this checkout's runtime version").toBe(version);
  }
  return status.state === "ready" && !status.kernel;
}
