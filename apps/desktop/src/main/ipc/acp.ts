/**
 * `sessions.*` handlers: the index plus the live ACP connection behind each
 * row, through one `SessionManager`. `ipc/index.ts` spreads `acpHandlers`
 * into the contract; main calls `shutdownAcp` on quit.
 */
import { randomUUID } from "node:crypto";

import { app } from "electron";

import { IpcError, broadcast, type IpcContext } from "./register";
import { detector } from "./agents";
import type { IpcHandlers } from "../../shared/ipc";
import type { acpContract } from "../../shared/ipc/acp";
import type { AgentSnapshot } from "../acp/agent-options";
import { spawnPtyTerminal } from "../acp/pty-backend";
import { AgentOptionStore } from "../acp/agent-options";
import { SessionManager } from "../acp/sessions";
import { forgetSession, mcpServersFor, sessionPreamble, skillsRoot } from "../integrations";
import { forgetCadSession, sessionRuntimePath } from "../cad";
import { track } from "../telemetry";
import {
  agentOptions as agentOptionsRepo,
  projects,
  sessions,
  sessionStates,
  settings,
} from "../db/repositories";
import { dropMarks, emptyTreeIfUnborn, head, sessionsUsing, snapshotTree } from "../projects/git";
import { releaseWorkspace } from "../projects/workspace";
import { sessionWorkspace, sessionWorkspaceSettled } from "./git";
import { browserService } from "../browser/service";
import { clearBrowserSessionStorage } from "../browser/storage";
import { explorerTerminals } from "./explorer";

/**
 * `TEXT_TO_CAD_FAKE_AGENT=<path to tests/fake-agent/index.mjs>` makes every
 * provider launch the scripted agent instead of its adapter. The Playwright
 * suite runs the built app this way; a packaged app ignores it.
 */
const fakeAgent = app.isPackaged ? undefined : process.env.TEXT_TO_CAD_FAKE_AGENT;

/**
 * What each agent's sessions can be configured with, between sessions
 * (`src/main/acp/agent-options.ts`): the snapshot the new-session screen's
 * model and effort chips are drawn from, the defaults `create` applies, and
 * the probe that takes a first snapshot from an agent nobody has run yet.
 *
 * Declared before the manager it calls into and closing over it lazily, so
 * the two can refer to each other without a module cycle.
 */
export const agentOptions: AgentOptionStore = new AgentOptionStore({
  read: () => agentOptionsRepo.list(),
  get: (agentId) => agentOptionsRepo.get(agentId),
  writeOptions: (agentId, options, modes) => agentOptionsRepo.setOptions(agentId, options, modes),
  writeDefaults: (agentId, defaults) => agentOptionsRepo.setDefaults(agentId, defaults),
  writeEffort: (agentId, model, effort) => agentOptionsRepo.setEffort(agentId, model, effort),
  probe: async (agentId, projectId): Promise<AgentSnapshot> => {
    const project = projectId
      ? (projects.get(projectId) ?? null)
      : (projects.list()[0] ?? null);
    if (!project) {
      throw new Error("no project to probe in");
    }
    return sessionManager.probeOptions({ agentId, cwd: project.path, projectId: project.id });
  },
  // Only an agent whose CLI is here (or any, under the fake agent): the
  // new-session screen asks for every agent that can launch.
  probeable: (agentId) => sessionManager.canProbe(agentId),
  onChange: (all) => broadcast("agentOptions.changed", all),
  onProbeFailed: (agentId, error) => {
    // Not installed, not signed in, no adapter: the new-session screen shows
    // that provider nothing, which is the whole of what the person needs.
    console.info(`[acp] ${agentId} answered no config options: ${String(error)}`);
  },
});

export const sessionManager: SessionManager = new SessionManager({
  repo: sessions,
  detector,
  spawnTerminal: spawnPtyTerminal,
  broadcast,
  // Every session gets the text-to-cad MCP server, with a token that names it.
  mcpServers: mcpServersFor,
  forgetProbe: (probeId) => forgetSession(probeId),
  forgetSession: (sessionId) => forgetSession(sessionId),
  // …the app's skills as an additional directory, and the preamble for an
  // agent that will not read one (src/main/integrations/skills.ts)…
  skills: { root: skillsRoot, preamble: sessionPreamble },
  // …and the bundled runtime's `cadgen` and `python` in front of its PATH.
  runtimePath: sessionRuntimePath,
  agentOptions: {
    defaults: (agentId) => agentOptions.defaults(agentId),
    effortFor: (agentId, model) => agentOptions.effortFor(agentId, model),
    remember: (agentId, options, modes) => agentOptions.remember(agentId, options, modes),
    rememberChoice: (agentId, configId, value, options) =>
      agentOptions.rememberChoice(agentId, configId, value, options),
    rememberMode: (agentId, modeId) => agentOptions.rememberMode(agentId, modeId),
  },
  clientVersion: app.isPackaged ? app.getVersion() : __APP_VERSION__,
  newId: () => randomUUID(),
  track,
  // The transcript on this machine, so a row clicked paints before its agent
  // has said a word (migration 10, `src/main/acp/snapshots.ts`).
  snapshots: sessionStates,
  launchOverride: fakeAgent
    ? () => ({
        // Electron's own binary, told to be plain Node.
        command: process.execPath,
        args: [fakeAgent, ...(process.env.TEXT_TO_CAD_FAKE_AGENT_ARGS?.split(" ").filter(Boolean) ?? [])],
        env: { ELECTRON_RUN_AS_NODE: "1" },
      })
    : undefined,

  /** P7: the git mode as a directory, and a worktree when the mode asks (plan §9). */
  workspace: sessionWorkspace,
  // The keep-limit sweep starts here, after the row, and is not awaited.
  workspaceSettled: sessionWorkspaceSettled,

  head: (cwd) => head(cwd),
  snapshot: (cwd, mark) => snapshotTree(cwd, mark),
  dropMarks: (cwd, sessionId) => dropMarks(cwd, sessionId),
  emptyTree: (cwd) => emptyTreeIfUnborn(cwd),

  releaseWorkspace: async (session, options) => {
    const worktree = session.worktreePath;
    if (worktree && sessionsUsing(sessions.list().filter(other => other.id !== session.id), worktree).length > 0) {
      return { removed: false, reason: "another session still uses it" };
    }
    return releaseWorkspace(session, settings.get(), options);
  },
});

/** Re-raise as an IpcError so the renderer sees the agent's words, not "failed". */
async function surfacing<T>(work: () => Promise<T> | T): Promise<T> {
  try {
    return await work();
  } catch (error) {
    throw new IpcError(error instanceof Error ? error.message : String(error));
  }
}

export const acpHandlers = {
  sessions: {
    list: ({ projectId }) => sessionManager.list(projectId),
    get: ({ id }) => sessionManager.get(id),
    // The mode falls back to the setting here rather than in the composer:
    // Settings › Git & Worktrees' `Default git mode` has to hold for every
    // caller, including the menu's New Session and Settings' `New session in
    // this worktree`, not only the one chip that happens to read it.
    create: (input) =>
      surfacing(() =>
        sessionManager.create({
          ...input,
          gitMode: input.gitMode ?? settings.get().defaultGitMode,
        }),
      ),
    load: ({ id }) => surfacing(() => sessionManager.load(id)),
    state: ({ id }) => sessionManager.state(id),
    prompt: ({ id, content }) => surfacing(() => sessionManager.prompt(id, content)),
    cancel: ({ id }) => surfacing(() => sessionManager.cancel(id)),
    setMode: ({ id, modeId }) => surfacing(() => sessionManager.setMode(id, modeId)),
    setConfigOption: ({ id, configId, value }) =>
      surfacing(() => sessionManager.setConfigOption(id, configId, value)),
    respondPermission: ({ id, requestId, optionId }) =>
      surfacing(() => sessionManager.respondPermission(id, requestId, optionId)),
    retrySetup: ({ id }) => surfacing(() => sessionManager.retrySetup(id)),
    rename: ({ id, title }) => surfacing(() => sessionManager.rename(id, title)),
    // The row first, as `delete` does: an archive that throws leaves the session
    // active with its tokens, pages and shells, not half torn down.
    archive: ({ id, archived }) => surfacing(async () => {
      const session = await sessionManager.archive(id, archived);
      if (archived) {
        forgetSession(id);
        browserService.disposeSession(id);
        explorerTerminals().disposeSession(id);
        // An archived thread is not open: its worktree's viewer stops with the last open one.
        forgetCadSession(id, session.worktreePath ?? null);
      }
      return session;
    }),
    setPinned: ({ id, pinned }) => surfacing(() => sessionManager.setPinned(id, pinned)),
    close: ({ id }) => surfacing(async () => { forgetSession(id); await sessionManager.close(id); }),
    delete: ({ id }) =>
      surfacing(async () => {
        // The row goes first, so a delete that fails leaves the session whole
        // with its tools; then everything running inside its directory, before
        // `delete` may remove the worktree — a terminal, browser target or CAD
        // viewer still holding it open would outlive its own directory.
        await sessionManager.delete(id, {
          beforeRelease: (row) => {
            forgetSession(id);
            browserService.disposeSession(id);
            explorerTerminals().disposeSession(id);
            forgetCadSession(id, row?.worktreePath ?? null);
          },
        });
        // Delete, unlike archive, takes the session's logins, cookies, cache
        // and browser artifacts with it — once the row is certainly gone.
        void clearBrowserSessionStorage(id);
      }),
  },
} satisfies IpcHandlers<typeof acpContract, IpcContext>;

export function shutdownAcp() {
  sessionManager.closeAll();
}

/** How long after launch the idle adapters are spawned. */
const PREWARM_DELAY_MS = 1_500;

/**
 * Spawn one idle adapter per agent the session index says is in use, so the
 * first session opened does not pay for the spawn (`src/main/acp/warm.ts`,
 * README "Opening a session").
 *
 * The index is read straight from sqlite: which agents are worth an adapter,
 * and the directory to spawn each in, are facts about the rows rather than
 * about anything the renderer has bound yet — so nothing waits for a window.
 * Delayed, so the spawn does not compete with the first paint, and gated the
 * way the CAD pre-warm is (`./cad.ts`): under `NODE_ENV=test` a dozen
 * launches spawning idle adapters is load no spec sees a result from, so
 * only `TEXT_TO_CAD_PREWARM=1` asks for it.
 */
export function prewarmAgents(): void {
  // Which agents are installed, probed now rather than when the renderer
  // first asks: the login shell and the `--version` runs overlap the
  // renderer's load, and a cold `agents.list` waits on this probe
  // (`COLD_LIST_WAIT_MS`). Not gated: it starts no agent, and every launch's
  // renderer asks for the table anyway.
  void detector.settled().catch((error: unknown) => {
    console.info(`[agents] the launch probe failed: ${String(error)}`);
  });
  if (process.env.NODE_ENV === "test" && process.env.TEXT_TO_CAD_PREWARM !== "1") {
    return;
  }
  const timer = setTimeout(() => {
    // The launch probe's table, above, not a second probe.
    void detector
      .settled()
      .then(() => sessionManager.warmAgents())
      .catch((error: unknown) => {
        console.info(`[acp] the idle adapters were not warmed: ${String(error)}`);
      });
  }, PREWARM_DELAY_MS);
  timer.unref?.();
}
