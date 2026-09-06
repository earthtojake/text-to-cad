/**
 * `runtime.*` handlers: the CAD runtime (src/main/cad/runtime.ts).
 *
 * `status` probes the resolved interpreter once and remembers the answer;
 * `repair` forgets it and probes again — there is nothing to install, the
 * runtime ships inside the app — and both broadcast `runtime.status` so the
 * About page and an open CAD tab agree afterwards.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { runtimeContract } from "../../shared/ipc/runtime";
import { cadRuntime } from "../cad";
import { broadcast, type IpcContext } from "./register";

export const runtimeHandlers = {
  runtime: {
    status: () => cadRuntime().status(),
    repair: async () => {
      const status = await cadRuntime().repair();
      broadcast("runtime.status", status);
      return status;
    },
  },
} satisfies IpcHandlers<typeof runtimeContract, IpcContext>;
