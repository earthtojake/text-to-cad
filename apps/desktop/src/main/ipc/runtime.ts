/**
 * `runtime.*` handlers: the CAD runtime (src/main/cad/runtime.ts).
 *
 * `status` probes the resolved interpreter once and remembers the answer;
 * `repair` forgets it and probes again — there is nothing to install, the
 * runtime ships inside the app — and both broadcast `runtime.status` so the
 * About page and an open CAD tab agree afterwards. `revealLog` shows the
 * runtime log in the file manager — main's own path, never the renderer's.
 */
import { existsSync } from "node:fs";
import { app, shell } from "electron";
import type { IpcHandlers } from "../../shared/ipc";
import type { RuntimeStatus, runtimeContract } from "../../shared/ipc/runtime";
import { cadRuntime } from "../cad";
import { runtimeLogPath } from "../cad/runtime";
import { broadcast, type IpcContext } from "./register";

export const runtimeHandlers = {
  runtime: {
    status: () => cadRuntime().status(),
    repair: () => freshStatus(),
    revealLog: () => revealRuntimeLog(),
  },
} satisfies IpcHandlers<typeof runtimeContract, IpcContext>;

/**
 * The CAD interpreter override changed (`settings.set`): probe afresh and
 * tell every window, so About and a CAD tab's build-failure note stop quoting
 * the old interpreter's kernel. The probe cache is per interpreter, so a new
 * path would probe anyway; forgetting all of it also re-asks an interpreter
 * that was probed before and has changed since.
 */
export async function refreshRuntimeAfterOverride(): Promise<RuntimeStatus> {
  return freshStatus();
}

/**
 * Every fresh probe that will broadcast takes a generation; only the newest
 * one's answer is broadcast. Override A (slow) then B: A's probe may answer
 * after B's, and a broadcast of it would put the OLD interpreter back on
 * About — the stale note this exists to clear.
 */
let generation = 0;

async function freshStatus(): Promise<RuntimeStatus> {
  const mine = ++generation;
  const status = await cadRuntime().repair();
  if (mine === generation) {
    broadcast("runtime.status", status);
  }
  return status;
}

/** Reveals `userData/cad-runtime.log` when it exists; answers whether it did. */
export function revealRuntimeLog(): { revealed: boolean } {
  const log = runtimeLogPath(app.getPath("userData"));
  if (!existsSync(log)) {
    return { revealed: false };
  }
  shell.showItemInFolder(log);
  return { revealed: true };
}
