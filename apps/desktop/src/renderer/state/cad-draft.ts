import { newSessionKey, useComposer } from "./composer";
import { useProjects } from "./projects";
import { useSessions } from "./sessions";

export class WorkspaceMismatch extends Error {}
export class DraftDestinationGone extends Error {}
export type DraftDestination = { key: string; projectId: string; projectPath: string; workspace: string; kind: "session" | "new" };

/** Bind while the action still owns its user-selected destination, before encoding. */
export function bindDraftDestination(projectId: string, root: string | null): DraftDestination {
  const projects = useProjects.getState();
  const project = projects.projects.find(item => item.id === projectId);
  if (!project || projects.activeId !== projectId) throw new Error("Open this model's project first.");
  const workspace = root ?? project.path;
  const { activeId, sessions } = useSessions.getState();
  if (activeId) {
    const session = sessions.find(item => item.id === activeId);
    if (!session) throw new Error("Wait for this chat to load before adding a reference or capture.");
    if (session.projectId !== projectId || session.cwd !== workspace) throw new WorkspaceMismatch("Choose a chat in this model's workspace, or start a new chat, to add its reference or capture.");
    return { key: activeId, projectId, projectPath: project.path, workspace, kind: "session" };
  }
  const key = newSessionKey(projectId);
  const existingRoot = useComposer.getState().draftRoots[key];
  if (existingRoot && existingRoot !== workspace) throw new WorkspaceMismatch("This draft already references another workspace. Clear it or use a chat in this model's workspace.");
  return { key, projectId, projectPath: project.path, workspace, kind: "new" };
}

/** A changed active chat never redirects a bound action; deletion invalidates it. */
export function validateDraftDestination(destination: DraftDestination): void {
  const project = useProjects.getState().projects.find(item => item.id === destination.projectId);
  if (!project || project.path !== destination.projectPath) throw new DraftDestinationGone("This context's project is no longer available.");
  if (destination.kind === "session") {
    const session = useSessions.getState().sessions.find(item => item.id === destination.key);
    if (!session) throw new DraftDestinationGone("The destination chat was deleted before this context was ready.");
    if (session.projectId !== destination.projectId || session.cwd !== destination.workspace) throw new WorkspaceMismatch("The destination chat no longer belongs to this context's workspace.");
  } else {
    const root = useComposer.getState().draftRoots[destination.key];
    if (root && root !== destination.workspace) throw new WorkspaceMismatch("The destination draft now belongs to another workspace.");
  }
}

export function draftDestinationIsCurrent(destination: DraftDestination): boolean {
  return useProjects.getState().activeId === destination.projectId &&
    useSessions.getState().activeId === (destination.kind === "session" ? destination.key : null);
}
