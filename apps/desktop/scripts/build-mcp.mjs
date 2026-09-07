/**
 * Bundle the Hardcore MCP server for shipping.
 *
 * `resources/hardcore-mcp/server.mjs` is the source: it imports
 * `@modelcontextprotocol/sdk` and `zod`, which a checkout resolves from
 * `apps/desktop/node_modules`. The agent that spawns the server in a packaged
 * app runs it by absolute path from beside the asar (electron-builder.yml
 * unpacks `out/hardcore-mcp/**`), where there is no `node_modules` to resolve
 * anything from — so this writes one self-contained ESM file to
 * `out/hardcore-mcp/server.mjs`, plus a `VERSION` the server reports to the
 * agent. `src/main/cad/index.ts` points at the source in a checkout and at
 * the bundle when packaged.
 *
 * Part of `npm run build` (scripts/build.mjs). esbuild is what electron-vite
 * already uses underneath; it is pinned in devDependencies so this script
 * does not depend on a transitive copy.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

import { appVersion } from "./app-version.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export async function buildMcpServer({ out = path.join(appRoot, "out", "hardcore-mcp"), version = appVersion() } = {}) {
  fs.mkdirSync(out, { recursive: true });
  await build({
    entryPoints: [path.join(appRoot, "resources", "hardcore-mcp", "server.mjs")],
    outfile: path.join(out, "server.mjs"),
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node22",
    // `import.meta.url` is how the server finds its VERSION and decides it is
    // the entry point; both hold for the bundle too.
    banner: {
      js: "import { createRequire as __hardcoreCreateRequire } from 'node:module'; const require = __hardcoreCreateRequire(import.meta.url);",
    },
    logLevel: "warning",
  });
  fs.writeFileSync(path.join(out, "VERSION"), `${version}\n`);
  return { out, version };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await buildMcpServer();
  console.info(`bundled hardcore-mcp ${result.version} -> ${result.out}`);
}
