/**
 * One place where main's pushes land in the stores.
 *
 * Components subscribe to stores, never to IPC. That keeps the event listeners
 * out of React's lifecycle — a `projects.changed` listener mounted per row
 * would be re-registered on every render of the sidebar — and it means a
 * change made from the app menu updates the same state a click would.
 */
import { useExplorer } from "./explorer";
import { useProjects } from "./projects";
import { useSessions } from "./sessions";
import { useSettings } from "./settings";
import { useUi } from "./ui";

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
    window.hardcore.on("files.changed", ({ projectId, changes }) => {
      useExplorer.getState().receiveChanges(
        projectId,
        changes.map((change) => change.path),
      );
    }),
    window.hardcore.on("ui.command", ({ command }) => {
      const ui = useUi.getState();
      switch (command) {
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
          void toggleLayout("explorerCollapsed");
          break;
        case "new-session":
          // P1 owns session creation. Until then the menu item lands on the
          // new-session state the session pane already shows.
          useSessions.getState().setActive(null);
          useUi.getState().closeSettings();
          break;
      }
    }),
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

function toggleLayout(key: "sidebarCollapsed" | "explorerCollapsed") {
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
  ]);
  // The explorer's strip follows the active project, which the subscription
  // in `subscribeToMain` picks up as soon as `useProjects.load` resolves.
  await useExplorer.getState().bindProject(useProjects.getState().activeId);
}
