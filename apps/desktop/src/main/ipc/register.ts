/**
 * Registration: walks the contract and the handler tree together, so every
 * channel that exists is served and every handler that exists is reachable.
 *
 * Both directions are validated. The request because the renderer is a browser
 * context and its messages are untrusted input; the response because a handler
 * that quietly returns the wrong shape produces a bug in the renderer, three
 * files away from its cause.
 */
import { BrowserWindow, ipcMain, type IpcMainInvokeEvent, type WebContents } from "electron";
import { z } from "zod";

import {
  IPC_EVENT_PREFIX,
  IPC_INVOKE_PREFIX,
  ipcChannels,
  ipcEvents,
  isInvokeDef,
  type IpcEventChannel,
  type IpcEventPayload,
  type IpcHandlers,
  type IpcNode,
} from "../../shared/ipc";

/** What a handler is given besides its request. */
export type IpcContext = {
  event: IpcMainInvokeEvent;
  sender: WebContents;
};

/**
 * An error a handler raised on purpose, whose message is safe to show. Any
 * other throw is reported to the renderer as a generic failure and logged
 * here, so a stack trace or a filesystem path never leaks into the UI.
 */
export class IpcError extends Error {
  override readonly name = "IpcError";
}

function handlerAt(handlers: unknown, path: string[]): unknown {
  return path.reduce<unknown>(
    (node, key) => (node as Record<string, unknown> | undefined)?.[key],
    handlers,
  );
}

export function registerIpc<T extends IpcNode>(
  contract: T,
  handlers: IpcHandlers<T, IpcContext>,
): void {
  for (const [name, def] of ipcChannels(contract)) {
    const handler = handlerAt(handlers, name.split("."));
    if (typeof handler !== "function") {
      throw new Error(`no IPC handler for channel ${name}`);
    }
    const channel = `${IPC_INVOKE_PREFIX}${name}`;
    ipcMain.handle(channel, async (event, rawRequest) => {
      const request = parse(def.request, rawRequest, `${name} request`);
      let result: unknown;
      try {
        result = await (handler as (req: unknown, ctx: IpcContext) => unknown)(request, {
          event,
          sender: event.sender,
        });
      } catch (error) {
        if (error instanceof IpcError) {
          throw error;
        }
        console.error(`[ipc] ${name} failed`, error);
        throw new Error(`${name} failed`, { cause: error });
      }
      return parse(def.response, result, `${name} response`);
    });
  }
}

function parse<S extends z.ZodType>(schema: S, value: unknown, what: string): z.output<S> {
  const parsed = schema.safeParse(value);
  if (!parsed.success) {
    throw new IpcError(`invalid ${what}: ${z.prettifyError(parsed.error)}`);
  }
  return parsed.data;
}

/** Remove every handler this contract registered. Used on quit and in tests. */
export function unregisterIpc<T extends IpcNode>(contract: T): void {
  for (const [name] of ipcChannels(contract)) {
    ipcMain.removeHandler(`${IPC_INVOKE_PREFIX}${name}`);
  }
}

/**
 * Push an event to a set of renderers, validated on the way out for the same
 * reason responses are.
 */
export function emit<C extends IpcEventChannel>(
  targets: Iterable<WebContents>,
  channel: C,
  payload: IpcEventPayload<C>,
): void {
  const validated = parse(ipcEvents[channel] as z.ZodType, payload, `${channel} event`);
  for (const target of targets) {
    if (!target.isDestroyed()) {
      target.send(`${IPC_EVENT_PREFIX}${channel}`, validated);
    }
  }
}

/** Broadcast to every open window. */
export function broadcast<C extends IpcEventChannel>(channel: C, payload: IpcEventPayload<C>) {
  emit(
    BrowserWindow.getAllWindows().map((window) => window.webContents),
    channel,
    payload,
  );
}

/** Guard used by the contract walk; re-exported so handlers can assert shapes. */
export { isInvokeDef };
