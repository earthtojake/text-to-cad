import { useCallback } from "react";
import { toast } from "sonner";

import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project } from "@shared/types";

/**
 * `Open folder…`: the native chooser, and then that folder's new-session
 * screen.
 *
 * One action, four places — the project chip's menu, the empty state in the
 * session pane, the sidebar's card when there is no project at all, and the
 * command palette — so it is written once. It is a hook rather than an action
 * on the projects store because the second half of it belongs to the sessions
 * store, and `state/projects.ts` cannot import that one: `state/sessions.ts`
 * already imports it.
 *
 * Resolves to null when the chooser is cancelled, so a caller can tell "no
 * folder was picked" from "this one was".
 */
export function useOpenFolder(): () => Promise<Project | null> {
  const add = useProjects((state) => state.add);
  const setActiveSession = useSessions((state) => state.setActive);
  return useCallback(async () => {
    const project = await add();
    if (project) {
      // `add` has already made it the active project; this is the rest of
      // what picking a folder means — its new-session screen, not whatever
      // thread happened to be open.
      setActiveSession(null);
    }
    return project;
  }, [add, setActiveSession]);
}

/**
 * The same action for the places with no error line of their own: a chooser or
 * `projects.add` that rejects is said in a toast, and reads as a cancelled
 * chooser (null) to the caller. The welcome screen has its own line for it and
 * uses `useOpenFolder` directly.
 */
export function useOpenFolderOrToast(): () => Promise<Project | null> {
  const openFolder = useOpenFolder();
  return useCallback(
    () =>
      openFolder().catch((error: unknown) => {
        toast.error("Could not open that folder", {
          description: error instanceof Error ? error.message : String(error),
        });
        return null;
      }),
    [openFolder],
  );
}
