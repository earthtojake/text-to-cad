import path from "node:path";

// By path, not by the bare "cadjs" specifier. This module runs from the shipped CAD Viewer
// runtime, which vendors packages/cadjs but has no node_modules to resolve a package name
// through. viewer/packages/cadjs is a symlink in development and a real directory once
// bundled, so the same relative path works in both.
import { pathIsInside } from "../packages/cadjs/src/lib/pathUtils.mjs";

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
