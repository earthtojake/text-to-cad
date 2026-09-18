import type { ExplorerRoot } from "@shared/types";
import { useSessions } from "./sessions";

/** Selected-session root for one project; a different project's session never applies. */
export function explorerRootFor(projectId: string | null): ExplorerRoot {
  if (!projectId) return null;
  const { activeId, sessions } = useSessions.getState();
  const session = sessions.find(candidate => candidate.id === activeId);
  return session && session.projectId === projectId ? (session.worktreePath ?? null) : null;
}
