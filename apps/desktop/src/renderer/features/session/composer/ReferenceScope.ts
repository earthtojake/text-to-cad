import { createContext } from "react";

import { useExplorer } from "@renderer/state/explorer";
import { isCadFile, type CadReference } from "@shared/cad-refs";
import type { ExplorerRoot } from "@shared/types";

export type ReferenceScope = { projectId: string; root: ExplorerRoot };
export const ReferenceScopeContext = createContext<ReferenceScope | null>(null);

/** A chip names a file in its draft's workspace, even when another tab is visible. */
export function openComposerReference(scope: ReferenceScope, reference: CadReference): void {
  const explorer = useExplorer.getState();
  if (explorer.projectId !== scope.projectId || !explorer.ready) {
    throw new Error("Open this reference’s project first.");
  }
  const current = explorer.tabs.find((tab) => tab.id === explorer.activeId);
  const file = reference.file || (current?.kind === "file" && current.root === scope.root && current.path && isCadFile(current.path)
    ? current.path : "");
  if (!file) {
    throw new Error("Open the model in this chat’s workspace to view this reference.");
  }
  const tab = explorer.openFile(file, scope.root);
  if (tab && reference.selector) explorer.selectCadReference(tab.id, reference.selector);
}
