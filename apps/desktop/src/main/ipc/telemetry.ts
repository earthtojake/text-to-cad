/**
 * Handlers for `telemetry.*` (src/shared/ipc/telemetry.ts).
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { telemetryContract } from "../../shared/ipc/telemetry";
import { fileExtension, sentEvents, telemetryStatus, track } from "../telemetry";
import type { IpcContext } from "./register";

export const telemetryHandlers = {
  telemetry: {
    status: () => telemetryStatus(),
    log: () => ({ events: sentEvents() }),
    fileOpened: ({ path }: { path: string }) => {
      track({ name: "file_opened", extension: fileExtension(path) });
    },
  },
} satisfies IpcHandlers<typeof telemetryContract, IpcContext>;
