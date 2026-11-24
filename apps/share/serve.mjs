#!/usr/bin/env node
// The share service on this computer: the real Worker (src/worker.mjs) over Node's http, with
// stand-ins for its R2 bucket, its static assets and its two rate limiters (src/local.mjs).
//
//   node apps/share/serve.mjs --port PORT --assets DIR [--store DIR] [--host HOST]
//
// --port   the port to listen on; 0 takes any free one
// --assets the viewer's built client (apps/web's build output), served as the static assets
// --store  keep shares as files under DIR (default: in memory, gone when it stops)
// --host   the address to listen on (default 127.0.0.1)
//
// When it is ready it prints its origin, and nothing else, on one line: http://127.0.0.1:PORT.
// Every share it keeps is sealed under the key its id derives, as the deployment's are. It allows
// every request (its limiters refuse none) and reads its limits (MAX_PACK_BYTES, MAX_MANIFEST_BYTES,
// MAX_SHARE_BYTES, EXPIRY_DAYS) from wrangler.jsonc's `vars`. It stops on SIGINT or SIGTERM.

import { statSync } from "node:fs";
import { parseArgs } from "node:util";

import { serve } from "./src/local.mjs";

const USAGE = "usage: node apps/share/serve.mjs --port PORT --assets DIR [--store DIR] [--host HOST]";

let options;
try {
  ({ values: options } = parseArgs({
    options: {
      port: { type: "string" },
      assets: { type: "string" },
      store: { type: "string" },
      host: { type: "string", default: "127.0.0.1" },
      help: { type: "boolean", short: "h" },
    },
    strict: true,
  }));
} catch (error) {
  console.error(`${error.message}\n${USAGE}`);
  process.exit(2);
}
if (options.help) {
  console.log(USAGE);
  process.exit(0);
}
if (options.port === undefined || !/^\d+$/.test(options.port) || Number(options.port) > 65535 || !options.assets) {
  console.error(USAGE);
  process.exit(2);
}

if (!statSync(options.assets, { throwIfNoEntry: false })?.isDirectory()) {
  console.error(`--assets ${options.assets} is not a folder (the viewer's built client)`);
  process.exit(2);
}

const server = await serve({ port: Number(options.port), host: options.host, assets: options.assets,
                             store: options.store ?? null });
console.log(server.origin);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, async () => {
    await server.close();
    process.exit(0);
  });
}
