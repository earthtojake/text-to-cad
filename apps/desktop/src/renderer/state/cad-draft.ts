import { toast } from "sonner";
import type { DraftContext } from "./composer";
import { newSessionKey, useComposer } from "./composer";
import { useProjects } from "./projects";
import { useSessions } from "./sessions";

class WorkspaceMismatch extends Error {}

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
      throw new WorkspaceMismatch("Choose a chat in this model's workspace, or start a new chat, to add its reference or capture.");
    }
    return activeId;
  }
  const key = newSessionKey(projectId);
  const composer = useComposer.getState();
  if (composer.draftRoots[key] && composer.draftRoots[key] !== workspace) {
    throw new WorkspaceMismatch("This draft already references another workspace. Clear it or use a chat in this model's workspace.");
  }
  composer.setDraftRoot(key, workspace);
  return key;
}

/** Keep references, images and revision text together in one workspace's draft. */
export function addToDraft(projectId: string, root: string | null, context: DraftContext): void {
  try {
    useComposer.getState().addContext(cadDraftKey(projectId, root), context);
  } catch (error) {
    if (!(error instanceof WorkspaceMismatch)) {
      toast.error(error instanceof Error ? error.message : String(error));
      return;
    }
    const project = useProjects.getState().projects.find((item) => item.id === projectId);
    if (!project) return;
    let starting = false;
    const offer = () => toast.error("This context belongs to another workspace.", {
      description: root ?? project.path,
      duration: Infinity,
      action: {
        label: "Start chat here",
        onClick: () => {
          if (starting) return;
          starting = true;
          void useSessions.getState().start({ projectId, cwd: root ?? project.path }).then((session) => {
            useProjects.getState().setActive(projectId);
            useComposer.getState().addContext(session.id, context);
          }).catch((caught: unknown) => {
            starting = false;
            toast.error(caught instanceof Error ? caught.message : String(caught));
            offer();
          });
        },
      },
    });
    offer();
  }
}
