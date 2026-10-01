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
 *   - preload builds `window.textToCad` by walking the same tree
 *     (`src/preload/index.ts`), so the renderer's API and the contract cannot
 *     disagree;
 *   - the renderer imports `TextToCadApi` — types only. Renderer code never
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
  SettingsPatchSchema,
  SettingsSchema,
  WindowStateSchema,
} from "../types";
// The machinery (`invoke`, `defineIpc`, the derived types) lives in
// ./ipc/define.ts and is re-exported here, so importing "@shared/ipc" still
// gets the whole surface.
import { defineIpc, invoke, type IpcClient } from "./define";
// One module per branch, spread in below: phases land in parallel, and a
// contract that grows by a spread per branch is one several people can extend
// at once.
import { appEvents, appIpc } from "./app";
import { acpContract, acpEvents } from "./acp";
import { agentOptionsContract, agentOptionsEvents } from "./agent-options";
import { agentsContract, agentsEvents } from "./agents";
import { dialogsContract } from "./dialogs";
import { runtimeContract, runtimeEvents } from "./runtime";
import { onboardingContract } from "./onboarding";
import { skillsContract } from "./skills";
import { integrationsIpc, integrationsEvents } from "./integrations";
import { cadIpc } from "./cad";
import { explorerEvents, explorerIpc } from "./explorer";
import { gitIpc } from "./git";
import { clipboardContract } from "./clipboard";
import { browserIpc } from "./browser";

export * from "./define";
export * from "./agent-options";
export * from "./cad";
export * from "./explorer";
export * from "./git";

/** The menu (or a shortcut) asked the renderer to navigate. */
export const UiCommandSchema = z.object({
  command: z.enum([
    "open-settings",
    "close-settings",
    "toggle-sidebar",
    "toggle-explorer",
    "new-session",
    "command-palette",
    /**
     * The top level's history: the project new-session screens and the
     * threads the session pane has shown (`state/history.ts`). Not the
     * explorer's tabs.
     */
    "navigate-back",
    "navigate-forward",
  ]),
  /**
   * `new-session` only: the project to start it in, and the directory to
   * start it in — Settings › Git and worktrees' `New session in this worktree`
   * (plan §2). Without them, `new-session` means "in whatever project is
   * selected, in the default mode".
   */
  projectId: z.string().optional(),
  cwd: z.string().optional(),
});

/* -------------------------------------------------------------------------- */
/* Requests                                                                    */
/* -------------------------------------------------------------------------- */

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
     * Opens the native folder chooser and validates a transient session directory. Resolves to
     * null when the dialog is cancelled — a cancelled dialog is an ordinary
     * outcome, not an error.
     */
    add: invoke(z.void(), ProjectSchema.nullable()),
    // No channel takes a directory by name. A folder becomes a project only
    // through a chooser main opened, the sample main copied, or a session
    // that already records it (`projects.get` in src/main/db/repositories.ts).
  },

  /** P1: `sessions.*` lives in ./ipc/acp.ts. */
  ...acpContract,

  /** P1: `agents.*` lives in ./ipc/agents.ts. */
  ...agentsContract,

  /** P2: `agentOptions.*` — the model and effort chips before a session exists. */
  ...agentOptionsContract,

  /** P5: the skills root every session is handed. */
  ...skillsContract,

  /** P5: the CAD runtime that ships inside the app — its status and a re-probe. */
  ...runtimeContract,

  /** First run: whether onboarding shows, and the sample project. */
  ...onboardingContract,

  /** P6: the native folder and file choosers Settings' path rows use. */
  ...dialogsContract,

  settings: {
    get: invoke(z.void(), SettingsSchema),
    /**
     * Merges a patch and answers with the whole settings object. The request
     * is `SettingsPatchSchema`, not `SettingsSchema.partial()` — see the
     * comment on it: `.partial()` keeps the defaults, and a "patch" carrying
     * every default is a patch that resets everything the caller did not
     * mention.
     */
    set: invoke(SettingsPatchSchema, SettingsSchema),
    /**
     * Stored values the read refused and answered with the default in place
     * of, by field — a branch prefix git refuses, written before the check
     * existed — so the page that shows the field can say so; and, apart from
     * those, the remembered folders that are gone.
     */
    fallbacks: invoke(
      z.void(),
      z.object({
        refused: z.record(z.string(), z.string()),
        /**
         * Remembered folders (`defaultProjectFolder`, `worktreeRoot`) that are not folders any more: stored fine, just
         * gone. `missing` is nothing at the path; `file` is a file there, which a worktree cannot be made under.
         */
        gone: z.record(z.string(), z.object({ path: z.string(), reason: z.enum(["missing", "file"]) })),
      }),
    ),
  },

  window: {
    state: invoke(z.void(), WindowStateSchema),
  },

  ui: {
    /**
     * The page is listening: answers with the `ui.command`s main held for it
     * (the menu's New Session or Settings… that opened this window), once.
     * A push at `did-finish-load` could arrive before the page subscribed.
     */
    ready: invoke(z.void(), z.array(UiCommandSchema)),
  },

  shell: {
    /**
     * Opens a URL in the user's browser. Main refuses anything that is not
     * http(s) — the renderer must not be able to hand the OS a `file:` or
     * custom-scheme URL.
     */
    openExternal: invoke(z.object({ url: z.string().url() }), z.void()),
    /**
     * Reveals a project directory in Finder/Explorer: the project itself, one
     * of its worktrees (`root`), or the folder its worktrees live in
     * (`worktrees`). Never a bare path — main resolves it like every other
     * renderer path, and refuses anything that is not the project's.
     */
    showItemInFolder: invoke(
      z.object({
        projectId: z.string().min(1),
        root: z.string().nullable().optional(),
        worktrees: z.literal(true).optional(),
      }),
      z.void(),
    ),
  },

  ...clipboardContract,
  ...browserIpc,

  // The branches a phase owns are declared in their own file and spread in
  // here, so this map stays a map. `explorer.*` and `terminal.*` come from
  // ./explorer (P3); `git.*` from ./git (P3's reads, P7's worktrees);
  // `cad.*` from ./cad (P3's stub, P5's implementation).
  ...explorerIpc,
  ...gitIpc,
  ...cadIpc,
  ...integrationsIpc,
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
  /** Explicit folder choice for a new session draft; never saved as a project. */
  "ui.directorySelected": ProjectSchema,
  /** The session index changed. */
  "sessions.changed": z.array(SessionSchema),
  /** Settings changed anywhere — including from the app menu. */
  "settings.changed": SettingsSchema,
  /** The menu (or a shortcut) asked the renderer to navigate. */
  "ui.command": UiCommandSchema,
  /** electron-updater's progress, surfaced on About and updates. */
  ...appEvents,
  ...acpEvents,
  ...agentsEvents,
  ...agentOptionsEvents,
  ...runtimeEvents,
  // `files.changed`, `terminal.data` and `terminal.exit` (P3).
  ...explorerEvents,
  // `integrations.command` — the text-to-cad MCP server's way into the explorer (P5).
  ...integrationsEvents,
} as const;

export type IpcEvents = typeof ipcEvents;
export type IpcEventChannel = keyof IpcEvents;
export type IpcEventPayload<C extends IpcEventChannel> = z.infer<IpcEvents[C]>;

/* -------------------------------------------------------------------------- */
/* The bridge                                                                  */
/* -------------------------------------------------------------------------- */

/** What preload puts on `window.textToCad`. */
export type TextToCadApi = IpcClient<IpcContract> & {
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
