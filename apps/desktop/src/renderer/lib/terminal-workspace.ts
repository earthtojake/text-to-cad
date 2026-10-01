import type { Project, Session } from "@shared/types";

type TerminalProject = Pick<Project, "id" | "path">;
type TerminalSession = Pick<Session, "projectId" | "cwd" | "worktreePath">;
function comparisonPath(value: string) {
  const normalized = value.replace(/\\/g, "/").replace(/\/+$/, "") || "/";
  // Windows drive and UNC paths are case-insensitive. POSIX paths are not.
  return /^[a-z]:(?:\/|$)/i.test(normalized) || normalized.startsWith("//") ? normalized.toLowerCase() : normalized;
}
function contains(root: string, candidate: string) {
  return candidate === root || candidate.startsWith(root === "/" ? root : `${root}/`);
}

/** Attribute output to its workspace, not to a terminal's optional subdirectory. */
export function terminalPromptRoot(project: TerminalProject, cwd: string | null, sessions: readonly TerminalSession[]): string | null {
  if (!cwd) return null;
  const directory = comparisonPath(cwd), checkout = comparisonPath(project.path);
  if (directory === checkout) return null;
  const roots = sessions.filter(session => session.projectId === project.id)
    .map(session => session.worktreePath ?? session.cwd)
    .filter(root => comparisonPath(root) !== checkout && contains(comparisonPath(root), directory))
    .sort((a, b) => comparisonPath(b).length - comparisonPath(a).length);
  // Keep the actual recorded root spelling: prompt destinations use that identity.
  return roots[0] ?? (contains(checkout, directory) ? null : cwd);
}
