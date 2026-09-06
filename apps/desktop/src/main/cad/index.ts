/**
 * The CAD runtime this app is built around. **Filled by P5.**
 *
 * `runtime.ts` provisions the managed Python under
 * `userData/runtime/<version>/` and installs the bundled `cadgen` wheel;
 * `viewer.ts` spawns `cadgen viewer --api-only` per project root and hands the
 * origin to the file tab; `plugin.ts` installs the composed Hardcore plugin
 * into each agent; `mcp-server.ts` is the stdio server passed to every
 * `session/new`.
 *
 * The seam is already in place: `cad.viewerOrigin` is declared in
 * `src/shared/ipc/cad.ts`, answered with `{ origin: null, reason:
 * "runtime-not-ready" }` by `src/main/ipc/cad.ts`, and the file tab's CAD
 * renderer already draws both answers — the viewer surface for an origin, and
 * a "CAD runtime is not set up yet" card for a null. `viewer.ts` changes the
 * body of that handler and nothing else.
 */
export {};
