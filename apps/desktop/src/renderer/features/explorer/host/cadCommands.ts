import type { CadCommands, CadCommandSource } from "@hardcore/ui/renderers/step";
import { useExplorer } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";

/** Borrow only requests for this active document; acknowledgement owns consumption. */
export function createDesktopCadCommands(projectId: string, root: ExplorerRoot, tabId: string): CadCommandSource & {
  acknowledge(kind: "selectReference" | "captureRequest", key: string | number): void;
} {
  let snapshot: CadCommands = { selectReference: null, captureRequest: null };
  return {
    subscribe: listener => useExplorer.subscribe(listener),
    getSnapshot() {
      const state = useExplorer.getState();
      const tab = state.tabs.find(tab => tab.id === tabId);
      const matches = (command: typeof state.cadCapture) => command && state.projectId === projectId
        && state.activeId === tabId && command.projectId === projectId && command.tabId === tabId
        && command.root === root && tab?.kind === "file" && tab.root === root && tab.path === command.path;
      const selection = matches(state.cadSelection) ? state.cadSelection : null;
      const capture = matches(state.cadCapture) ? state.cadCapture : null;
      if (snapshot.selectReference?.key !== selection?.nonce || snapshot.captureRequest?.key !== capture?.nonce) {
        snapshot = { selectReference: selection ? { selector: selection.selector, key: selection.nonce } : null,
          captureRequest: capture ? { key: capture.nonce } : null };
      }
      return snapshot;
    },
    acknowledge: (kind, key) => useExplorer.getState().acknowledgeCadCommand(kind, key),
  };
}
