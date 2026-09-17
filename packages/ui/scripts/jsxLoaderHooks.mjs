// Module hooks that let `node --test` import the client's JSX sources.
// UI sources use JSX inside `.js` and extensionless relative imports.
// Node tests resolve those relative paths and transform JSX with Vite's Oxc
// compiler. Workspace imports still resolve compiled package exports.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const CLIENT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src");
const CANDIDATE_SUFFIXES = ["", ".js", ".jsx", "/index.js", "/index.jsx"];
// Every JSX element closes, so a file with neither a closing nor a
// self-closing tag has no JSX in it and Node can read it as written. Most test
// files import nothing but plain modules, and paying for Vite's import in each
// of those processes cost more than the whole suite.
const JSX_MARKER = /<\/|\/>/u;

let transform = null;

// Vite 8 transforms with Oxc: `transformWithEsbuild` is deprecated and now
// needs esbuild installed separately, which the app no longer depends on.
// `lang` replaces esbuild's `loader`, and the JSX runtime is an object.
async function transformJsx(source, file) {
  if (!transform) ({ transformWithOxc: transform } = await import("vite"));
  const transformed = await transform(source, file, {
    lang: "jsx",
    jsx: { runtime: "automatic" },
  });
  return transformed.code;
}

function resolveClientFile(base) {
  for (const suffix of CANDIDATE_SUFFIXES) {
    const candidate = `${base}${suffix}`;
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }
  return "";
}

function clientResolution(file) {
  return file ? { url: pathToFileURL(file).href, format: "module", shortCircuit: true } : null;
}

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && context.parentURL?.startsWith("file:")) {
    const parentDir = path.dirname(fileURLToPath(context.parentURL));
    if (parentDir.startsWith(CLIENT_ROOT)) {
      const resolved = clientResolution(resolveClientFile(path.resolve(parentDir, specifier)));
      if (resolved) return resolved;
    }
  }
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (!url.startsWith("file:") || !/\.jsx?$/u.test(url)) {
    return nextLoad(url, context);
  }
  const file = fileURLToPath(url);
  if (!file.startsWith(CLIENT_ROOT)) {
    return nextLoad(url, context);
  }
  const source = fs.readFileSync(file, "utf8");
  if (!JSX_MARKER.test(source)) {
    return { format: "module", source, shortCircuit: true };
  }
  return { format: "module", source: await transformJsx(source, file), shortCircuit: true };
}
