/**
 * `runtime.*` handlers — stubs.
 *
 * P5 owns `src/main/cad/runtime.ts`: a pinned python-build-standalone under
 * `userData/runtime/<version>/` with the bundled wheel installed into it. Until
 * that exists the state is `missing`, which is exactly what a build with an
 * empty `resources/cadgen/` should report.
 *
 * The one thing that is real here is the override: `cadPythonOverride` is a
 * setting the user can already set, and reporting it back is how the page shows
 * that the field took effect.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { RuntimeStatus, runtimeContract } from "../../shared/ipc/runtime";
import { settings } from "../db/repositories";
import type { IpcContext } from "./register";

function status(): RuntimeStatus {
  const override = settings.get().cadPythonOverride;
  return {
    state: "missing",
    python: override,
    cadgenVersion: null,
    viewerBuilt: false,
    overridden: override !== null,
    log: null,
    message: "The managed Python and the bundled cadgen wheel arrive with P5.",
  };
}

export const runtimeHandlers = {
  runtime: {
    status,
    // P5: provision, streaming `runtime.progress` as it goes.
    repair: () => status(),
  },
} satisfies IpcHandlers<typeof runtimeContract, IpcContext>;
