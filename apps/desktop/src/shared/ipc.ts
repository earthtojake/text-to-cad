/**
 * The IPC contract: one place that says what main can be asked, what it
 * answers with, and what it pushes.
 *
 * A channel is declared once, as a pair of zod schemas. From that one
 * declaration three things follow, with no second source to keep in step:
 *
 *   - main gets `IpcHandlers`, a nested object of functions whose argument and
 *     return types are the schemas, registered with request *and* response
 *     validation (`src/main/ipc/index.ts`);
 *   - preload builds `window.hardcore` by walking the same tree
 *     (`src/preload/index.ts`), so the renderer's API and the contract cannot
 *     disagree;
 *   - the renderer imports `HardcoreApi` — types only. Renderer code never
 *     touches `ipcRenderer`, and never imports anything from `src/main`.
 *
 * Validation is not decoration. The renderer is a browser context: everything
 * arriving from it is untrusted input, and a handler that reads
 * `request.path` should know a string was actually sent.
 *
 * Each phase keeps its channels in its own file under `src/shared/ipc/` and
 * is spread into the contract and the event map here, one line each.
 */
import { z } from "zod";

import {
  AppInfoSchema,
  ProjectSchema,
  SessionSchema,
  SettingsSchema,
  WindowStateSchema,
} from "./types";
// The machinery (`invoke`, `defineIpc`, the derived types) lives in
// ./ipc/define.ts and is re-exported here, so importing "@shared/ipc" still
// gets the whole surface.
import { defineIpc, invoke, type IpcClient } from "./ipc/define";
// One module per branch, spread in below: phases land in parallel, and a
// contract that grows by a spread per branch is one several people can extend
// at once.
import { appEvents, appIpc } from "./ipc/app";
import { acpContract, acpEvents } from "./ipc/acp";
import { agentsContract, agentsEvents } from "./ipc/agents";

export * from "./ipc/define";

/* -------------------------------------------------------------------------- */
/* Requests                                                                    */
/* -------------------------------------------------------------------------- */

const Id = z.object({ id: z.string().min(1) });

export const ipcContract = defineIpc({
  app: {
    /** Version, platform and dev flag — everything About needs. */
    info: invoke(z.void(), AppInfoSchema),
    /** The updater: status, check, download, install (`./ipc/app.ts`). */
    ...appIpc,
  },

  projects: {
    list: invoke(z.void(), z.array(ProjectSchema)),
    /**
     * Opens the native folder chooser and adds what comes back. Resolves to
     * null when the dialog is cancelled — a cancelled dialog is an ordinary
     * outcome, not an error.
     */
    add: invoke(z.void(), ProjectSchema.nullable()),
    /** Adds a directory by path, for tests and for `--open <dir>`. */
    addPath: invoke(z.object({ path: z.string().min(1) }), ProjectSchema),
    /** Forgets the project. Never touches the directory on disk. */
    remove: invoke(Id, z.void()),
    rename: invoke(Id.extend({ name: z.string().min(1) }), ProjectSchema),
  },

  /** P1: `sessions.*` lives in ./ipc/acp.ts. */
  ...acpContract,

  /** P1: `agents.*` lives in ./ipc/agents.ts. */
  ...agentsContract,

  settings: {
    get: invoke(z.void(), SettingsSchema),
    /** Merges a partial update and answers with the whole settings object. */
    set: invoke(SettingsSchema.partial(), SettingsSchema),
  },

  window: {
    state: invoke(z.void(), WindowStateSchema),
  },

  shell: {
    /**
     * Opens a URL in the user's browser. Main refuses anything that is not
     * http(s) — the renderer must not be able to hand the OS a `file:` or
     * custom-scheme URL.
     */
    openExternal: invoke(z.object({ url: z.string().url() }), z.void()),
    /** Reveals a path in Finder/Explorer. */
    showItemInFolder: invoke(z.object({ path: z.string().min(1) }), z.void()),
  },
});

export type IpcContract = typeof ipcContract;

/* -------------------------------------------------------------------------- */
/* Events                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Main → renderer pushes. Flat: an event has one payload and no answer, so
 * there is nothing to nest.
 */
export const ipcEvents = {
  /** The project list changed (added, removed, renamed). */
  "projects.changed": z.array(ProjectSchema),
  /** The session index changed. */
  "sessions.changed": z.array(SessionSchema),
  /** Settings changed anywhere — including from the app menu. */
  "settings.changed": SettingsSchema,
  /** The menu (or a shortcut) asked the renderer to navigate. */
  "ui.command": z.object({
    command: z.enum([
      "open-settings",
      "close-settings",
      "toggle-sidebar",
      "toggle-explorer",
      "new-session",
      "command-palette",
    ]),
  }),
  /** electron-updater's progress, surfaced on About & Updates. */
  ...appEvents,
  ...acpEvents,
  ...agentsEvents,
} as const;

export type IpcEvents = typeof ipcEvents;
export type IpcEventChannel = keyof IpcEvents;
export type IpcEventPayload<C extends IpcEventChannel> = z.infer<IpcEvents[C]>;

/* -------------------------------------------------------------------------- */
/* The bridge                                                                  */
/* -------------------------------------------------------------------------- */

/** What preload puts on `window.hardcore`. */
export type HardcoreApi = IpcClient<IpcContract> & {
  /**
   * Subscribe to a main-process event. Returns the unsubscribe function —
   * React effects want a teardown, and a listener that outlives its component
   * is a leak in a process that never reloads.
   */
  on<C extends IpcEventChannel>(
    channel: C,
    listener: (payload: IpcEventPayload<C>) => void,
  ): () => void;
};
