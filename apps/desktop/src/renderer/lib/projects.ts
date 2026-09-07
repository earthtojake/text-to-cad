/**
 * The project list in the order a person last used it, for the menus that
 * offer a folder to switch to (`Recent`, on the composer's project chip).
 *
 * A pure function over the index rather than a field on the project: there is
 * no `lastUsedAt` column, and there should not be one — the answer is already
 * in the sessions, and a second copy would be a second thing to keep true
 * every time a turn ends. `lib/sidebar.ts` makes the same argument about the
 * sections.
 */
import type { Project, Session } from "@shared/types";

/**
 * Projects most recently worked in first: a project's activity is the newest
 * `updatedAt` of any of its sessions (archived ones included — the folder was
 * still where the work happened). A project nobody has run a thread in has
 * none, so it keeps the project list's own order, which is the order projects
 * were added; that order is also the tiebreak, so the result is total and a
 * fresh index does not reshuffle the menu.
 */
export function recentProjects(
  projects: readonly Project[],
  sessions: readonly Session[],
): Project[] {
  const activity = new Map<string, number>();
  for (const session of sessions) {
    const seen = activity.get(session.projectId) ?? 0;
    if (session.updatedAt > seen) {
      activity.set(session.projectId, session.updatedAt);
    }
  }
  return projects
    .map((project, index) => ({ project, index, at: activity.get(project.id) ?? 0 }))
    .sort((a, b) => b.at - a.at || a.index - b.index)
    .map((entry) => entry.project);
}
