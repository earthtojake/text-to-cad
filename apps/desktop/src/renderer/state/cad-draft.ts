import { useProjects } from "./projects";
import { useSessions } from "./sessions";

export class WorkspaceMismatch extends Error {}
export class DraftDestinationGone extends Error {}
export type DraftDestination = { key: string; projectId: string; projectPath: string; workspace: string };

/** A viewer tab always addresses its owning session, independent of UI selection. */
export function bindDraftDestination(projectId: string, root: string | null, sessionId: string): DraftDestination {
  const project = useProjects.getState().projects.find(item => item.id === projectId);
  if (!project) throw new DraftDestinationGone("This context's directory is no longer available.");
  const destination = { key: sessionId, projectId, projectPath: project.path, workspace: root ?? project.path };
  validateDraftDestination(destination);
  return destination;
}

/** Revalidate after asynchronous capture/encoding; never redirect to another chat. */
export function validateDraftDestination(destination: DraftDestination): void {
  const session = useSessions.getState().sessions.find(item => item.id === destination.key);
  if (!session || session.archived) throw new DraftDestinationGone("The destination chat was deleted or archived before this context was ready.");
  if (session.projectId !== destination.projectId || session.cwd !== destination.workspace) {
    throw new WorkspaceMismatch("This context does not belong to its owning chat's workspace.");
  }
}

export function draftDestinationIsCurrent(destination: DraftDestination): boolean {
  return useSessions.getState().activeId === destination.key;
}
