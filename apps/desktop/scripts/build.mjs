/**
 * `npm run build`: everything a runnable `out/` needs, in order.
 *
 *   1. compose the app's skills into resources/skills (build-skills.mjs);
 *   2. electron-vite build — main, preload, renderer into out/;
 *   3. bundle the MCP server into out/hardcore-mcp (build-mcp.mjs), after
 *      electron-vite because it empties its output directories first.
 *
 * `scripts/package.mjs` runs this before electron-builder, so a packaged app
 * and the app the e2e suite launches are built the same way.
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";
import { buildMcpServer } from "./build-mcp.mjs";
import { buildSkills } from "./build-skills.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");

export function buildAll({ env = process.env } = {}) {
  const version = appVersion();

  const skills = buildSkills({ repoRoot, out: path.join(appRoot, "resources", "skills") });
  console.info(`composed ${skills.skills.length} skills -> resources/skills`);

  const npx = process.platform === "win32" ? "npx.cmd" : "npx";
  // Rollup holds the whole renderer graph in memory, and this renderer is a
  // large one — Monaco, three.js, shiki's grammars, the CAD Viewer's client.
  // A build peaks around 4.6 GB, which is over Node's default old-space cap on
  // a 64-bit host, so the bundler gets an explicit ceiling rather than the
  // implicit one it was quietly exceeding on CI ("Reached heap limit").
  // Whatever the caller already asked for wins.
  const heap = "--max-old-space-size=6144";
  const nodeOptions = env.NODE_OPTIONS ?? "";
  const result = spawnSync(npx, ["electron-vite", "build"], {
    cwd: appRoot,
    stdio: "inherit",
    env: {
      ...env,
      NODE_OPTIONS: nodeOptions.includes("--max-old-space-size")
        ? nodeOptions
        : `${nodeOptions} ${heap}`.trim(),
    },
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }

  return buildMcpServer({ version }).then((mcp) => {
    console.info(`bundled hardcore-mcp ${mcp.version} -> ${path.relative(appRoot, mcp.out)}`);
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildAll();
}
