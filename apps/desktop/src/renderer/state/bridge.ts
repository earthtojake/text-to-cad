/**
 * One place where main's pushes land in the stores.
 *
 * Components subscribe to stores, never to IPC. That keeps the event listeners
 * out of React's lifecycle — a `projects.changed` listener mounted per row
 * would be re-registered on every render of the sidebar — and it means a
 * change made from the app menu updates the same state a click would.
 */
import type { IpcEventPayload } from "@shared/ipc";

import { useAcp } from "./acp";
import { useAgents } from "./agents";
import { useComposer } from "./composer";
import { performCadCommand } from "./cad-commands";
import { useExplorer } from "./explorer";
import { usePlugins } from "./plugins";
import { useProjects } from "./projects";
import { useRuntime } from "./runtime";
import { useSessions } from "./sessions";
import { useSettings } from "./settings";
import { useUi } from "./ui";
import { useUpdates } from "./updates";

export type UiCommand = IpcEventPayload<"ui.command">["command"];

/** Attach every main → renderer listener. Returns a detach function. */
export function subscribeToMain(): () => void {
  const off = [
    window.hardcore.on("projects.changed", (projects) => {
      useProjects.getState().receive(projects);
    }),
    window.hardcore.on("sessions.changed", (sessions) => {
      useSessions.getState().receive(sessions);
    }),
    window.hardcore.on("settings.changed", (settings) => {
      useSettings.getState().receive(settings);
    }),
    window.hardcore.on("app.updateStatus", (status) => {
      useUpdates.getState().receive(status);
    }),
    window.hardcore.on("session.state", ({ sessionId, state }) => {
      useAcp.getState().receiveState(sessionId, state);
    }),
    window.hardcore.on("session.update", ({ sessionId, event }) => {
      useAcp.getState().receiveEvent(sessionId, event);
      // A turn that just ended frees the session for the next queued prompt.
      if (event.type === "prompt/end") {
        void useComposer.getState().drain(sessionId);
      }
    }),
    window.hardcore.on("terminal.output", ({ sessionId, terminalId, data }) => {
      useAcp.getState().receiveTerminalOutput(sessionId, terminalId, data);
    }),
    window.hardcore.on("agents.status", (agents) => {
      useAgents.getState().receive(agents);
    }),
    window.hardcore.on("agents.output", (chunk) => {
      useAgents.getState().receiveOutput(chunk);
    }),
    window.hardcore.on("plugins.status", (statuses) => {
      usePlugins.getState().receive(statuses);
    }),
    window.hardcore.on("runtime.status", (status) => {
      useRuntime.getState().receive(status);
    }),
    window.hardcore.on("files.changed", ({ projectId, changes }) => {
      useExplorer.getState().receiveChanges(
        projectId,
        changes.map((change) => change.path),
      );
    }),
    // An agent's tool call, relayed by main; answered whatever happens, so
    // the bridge's wait ends with the reason rather than a timeout.
    window.hardcore.on("cad.command", (command) => {
      void performCadCommand(command)
        .then((result) => window.hardcore.cad.reply({ requestId: command.requestId, ok: true, result }))
        .catch((error: unknown) =>
          window.hardcore.cad.reply({
            requestId: command.requestId,
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          }),
        )
        .catch(() => {});
    }),
    window.hardcore.on("ui.command", (payload) => runUiCommand(payload)),
  ];

  // The explorer strip belongs to the active project, so it follows the
  // project selection rather than being loaded once. Subscribing to the store
  // rather than doing this in a component keeps the load off React's
  // lifecycle — a remount must not re-read the strip and lose the selection.
  let boundProject: string | null | undefined;
  const unsubscribeProjects = useProjects.subscribe((state) => {
    if (state.activeId === boundProject) {
      return;
    }
    boundProject = state.activeId;
    void useExplorer.getState().bindProject(state.activeId);
  });

  return () => {
    unsubscribeProjects();
    for (const detach of off) {
      detach();
    }
  };
}

/**
 * One `ui.command`, whether it came from the app menu or from a button in the
 * renderer.
 *
 * Exported because Settings › Git & Worktrees' `New chat in this worktree` is
 * the same command as the menu's New Session, only with a directory attached —
 * and a second implementation of "start a thread and show it" would be a
 * second place for the two to disagree about what happens to Settings, the
 * project selection and the explorer strip.
 */
export function runUiCommand(payload: IpcEventPayload<"ui.command">): void {
  const ui = useUi.getState();
  switch (payload.command) {
    case "open-settings":
      ui.openSettings();
      break;
    case "close-settings":
      ui.closeSettings();
      break;
    case "command-palette":
      ui.toggleCommandPalette();
      break;
    case "toggle-sidebar":
      void toggleLayout("sidebarCollapsed");
      break;
    case "toggle-explorer":
      useExplorer.getState().toggleCollapsed();
      break;
    case "new-session": {
      ui.closeSettings();
      const projectId = payload.projectId ?? useProjects.getState().activeId;
      if (payload.projectId) {
        useProjects.getState().setActive(payload.projectId);
      }
      // Without a directory this is the menu item, which lands on the empty
      // new-session state the session pane shows and lets the composer decide
      // the mode. With one it is Settings' `New chat in this worktree`, and
      // the thread starts in that worktree straight away.
      if (!projectId || !payload.cwd) {
        useSessions.getState().setActive(null);
        return;
      }
      void useSessions
        .getState()
        .start({ projectId, cwd: payload.cwd, gitMode: "worktree" })
        .catch((error: unknown) => {
          console.error("[ui] could not start a session", error);
        });
      break;
    }
    case "open-review": {
      // The files-changed pill: open (or focus) the Review tab, and the
      // explorer if it was closed. P3 gives the tab its body.
      const explorer = useExplorer.getState();
      const existing = explorer.tabs.find((tab) => tab.kind === "review");
      if (existing) {
        explorer.show();
        explorer.setActive(existing.id);
      } else {
        explorer.open("review");
      }
      break;
    }
  }
}

function toggleLayout(key: "sidebarCollapsed") {
  const { settings, setLayout } = useSettings.getState();
  if (!settings) {
    return Promise.resolve();
  }
  return setLayout({ [key]: !settings.layout[key] });
}

/** First read of everything the shell needs. */
export async function hydrate(): Promise<void> {
  await Promise.all([
    useSettings.getState().load(),
    useProjects.getState().load(),
    useSessions.getState().load(),
    useUpdates.getState().load(),
    useAgents.getState().load(),
  ]);
  // The explorer's strip follows the active project, which the subscription
  // in `subscribeToMain` picks up as soon as `useProjects.load` resolves.
  await useExplorer.getState().bindProject(useProjects.getState().activeId);
}
