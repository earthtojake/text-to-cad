import path from "node:path";

// Development tooling and its tests consume the root workspace's compiled
// @hardcore/core export, just like the app.
import { pathIsInside } from "@hardcore/core/lib/pathUtils.mjs";

export function resolveDirectoryRoot({
  directoryRoot = "",
  env = process.env,
  cwd = process.cwd(),
  appRoot = "",
  defaultDirectoryRoot = "",
} = {}) {
  const explicitRoot = directoryRoot || "";
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

  return defaultDirectoryRoot ? path.resolve(defaultDirectoryRoot) : path.resolve(cwd);
}
