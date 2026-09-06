/**
 * `runtime.*` handlers: the managed Python and cadgen (src/main/cad/runtime.ts).
 *
 * `status` probes without provisioning; `repair` installs (or reinstalls) the
 * managed runtime, streaming `runtime.progress` as it goes, and answers with
 * the state at the end. With an override or a checkout in force there is
 * nothing to install, and repair is a fresh probe of that interpreter.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { runtimeContract } from "../../shared/ipc/runtime";
import { cadRuntime } from "../cad";
import type { IpcContext } from "./register";

export const runtimeHandlers = {
  runtime: {
    status: () => cadRuntime().status(),
    repair: () => cadRuntime().repair(),
  },
} satisfies IpcHandlers<typeof runtimeContract, IpcContext>;
