/**
 * The CAD runtime this app is built around. **Filled by P4 and P5.**
 *
 * `runtime.ts` provisions the managed Python under
 * `userData/runtime/<version>/` and installs the bundled `cadgen` wheel;
 * `viewer.ts` spawns `cadgen viewer --api-only` per project root and hands the
 * origin to the file tab; `plugin.ts` installs the composed Hardcore plugin
 * into each agent; `mcp-server.ts` is the stdio server passed to every
 * `session/new`.
 */
export {};
