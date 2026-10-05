import path from "node:path";

// Development tooling and its tests consume the root workspace's compiled
// @text-to-cad/core export, just like the app.
import { pathIsInside } from "@text-to-cad/core/lib/pathUtils.mjs";

// The folder the dev backend starts in, which is only where a relative `?file=`
// resolves (`serverInfo.start`): where `npm run dev` was invoked (`INIT_CWD`),
// else the working directory, each only when it is outside the app, else the
// default.
export function resolveDirectoryRoot({
  env = process.env,
  cwd = process.cwd(),
  appRoot = "",
  defaultDirectoryRoot = "",
} = {}) {
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
