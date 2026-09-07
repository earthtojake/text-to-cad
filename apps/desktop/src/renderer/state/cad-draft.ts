import { newSessionKey, useComposer } from "./composer";
import { useProjects } from "./projects";
import { useSessions } from "./sessions";

/** References are relative to their model's root, never an arbitrary active chat. */
export function cadDraftKey(projectId: string, root: string | null): string {
  const projects = useProjects.getState();
  const project = projects.projects.find((item) => item.id === projectId);
  if (!project || projects.activeId !== projectId) throw new Error("Open this model's project first.");
  const workspace = root ?? project.path;
  const { activeId, sessions } = useSessions.getState();
  if (activeId) {
    const session = sessions.find((item) => item.id === activeId);
    if (!session) throw new Error("Wait for this chat to load before adding a reference or capture.");
    if (session.projectId !== projectId || session.cwd !== workspace) {
      throw new Error("Choose a chat in this model's workspace, or start a new chat, to add its reference or capture.");
    }
    return activeId;
  }
  const key = newSessionKey(projectId);
  const composer = useComposer.getState();
  if (composer.draftRoots[key] && composer.draftRoots[key] !== workspace) {
    throw new Error("This draft already references another workspace. Clear it or use a chat in this model's workspace.");
  }
  composer.setDraftRoot(key, workspace);
  return key;
}
