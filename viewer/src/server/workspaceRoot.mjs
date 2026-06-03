import path from "node:path";

import { pathIsInside } from "cadjs/lib/pathUtils.mjs";

export function resolveWorkspaceRoot({
  workspaceRoot = "",
  env = process.env,
  cwd = process.cwd(),
  appRoot = "",
  defaultWorkspaceRoot = "",
} = {}) {
  const explicitRoot = workspaceRoot || "";
  if (explicitRoot) {
    return path.resolve(cwd, explicitRoot);
  }

  const resolvedAppRoot = appRoot ? path.resolve(appRoot) : "";
  for (const candidate of [env.INIT_CWD, cwd]) {
    if (!candidate) {
      continue;
    }
    const resolvedCandidate = path.resolve(candidate);
    if (!resolvedAppRoot || (resolvedCandidate !== resolvedAppRoot && !pathIsInside(resolvedCandidate, resolvedAppRoot))) {
      return resolvedCandidate;
    }
  }

  return defaultWorkspaceRoot ? path.resolve(defaultWorkspaceRoot) : path.resolve(cwd);
}
