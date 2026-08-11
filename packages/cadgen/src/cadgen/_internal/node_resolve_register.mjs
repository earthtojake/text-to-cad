/**
 * `node --import <this>` installs `node_resolve_hooks.mjs` for the builder child.
 *
 * Separate from the hook module on purpose: `module.register` loads the hooks on their own
 * thread, so a self-registering file would re-run its own `register()` call there.
 */

import { register } from "node:module";

register("./node_resolve_hooks.mjs", import.meta.url);
