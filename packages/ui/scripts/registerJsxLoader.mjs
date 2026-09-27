// `node --test --import ./scripts/registerJsxLoader.mjs` installs the client
// JSX/alias module hooks; see scripts/jsxLoaderHooks.mjs.
import { register } from "node:module";

register("./jsxLoaderHooks.mjs", import.meta.url);
