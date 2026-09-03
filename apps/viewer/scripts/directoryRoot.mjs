import path from "node:path";

// By name: this module runs only in development (vite.config.mjs and its tests),
// where node_modules links cadgen-js through the package.json `file:` dependency.
import { pathIsInside } from "cadgen-js/lib/pathUtils.mjs";

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
