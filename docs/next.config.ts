import type { NextConfig } from "next";
import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(process.cwd(), "..");
const cadJsPackageRoot = path.join(repoRoot, "packages/cadjs/src");
const implicitJsRoot = path.join(repoRoot, "packages/implicitjs");

// cadjs re-exports implicitjs (cadjs/common/camera.js -> implicitjs/common/camera.js), so the
// docs build has to resolve it too -- and it has to resolve it THROUGH implicitjs's exports
// map, not as a directory. A directory alias silently gets the renames wrong:
// `implicitjs/headlessRenderEntry` is src/common/implicitHeadlessRenderEntry.js, which no
// path-joining rule would find. The same reason the bundle scripts use NODE_PATH rather than
// an --alias.
//
// Derived from that map rather than hand-listed, so a new subpath cadjs imports resolves
// without editing this file. Wildcard patterns ("./common/*") expand over the real directory
// because resolveAlias matches exact specifiers only.
function implicitJsAliases(): Record<string, string> {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(implicitJsRoot, "package.json"), "utf8"),
  ) as { exports?: Record<string, string | Record<string, string>> };
  // Targets are written relative to the docs project, like "./node_modules/three" above.
  // An absolute path is re-read as relative to the turbopack root and resolves to nonsense
  // ("./private/tmp/.../camera.js").
  const fromDocs = (absolute: string) => {
    const relative = path.relative(process.cwd(), absolute);
    return relative.startsWith(".") ? relative : `./${relative}`;
  };
  const aliases: Record<string, string> = {};
  for (const [entry, target] of Object.entries(manifest.exports ?? {})) {
    const resolved = typeof target === "string" ? target : target.default;
    if (!resolved) continue;
    const specifier = entry === "." ? "implicitjs" : `implicitjs/${entry.slice(2)}`;
    if (!entry.includes("*")) {
      aliases[specifier] = fromDocs(path.join(implicitJsRoot, resolved));
      continue;
    }
    const [specifierPrefix] = specifier.split("*");
    const targetDir = path.join(implicitJsRoot, resolved.split("*")[0]);
    if (!fs.existsSync(targetDir)) continue;
    for (const file of fs.readdirSync(targetDir)) {
      if (!file.endsWith(".js")) continue;
      aliases[`${specifierPrefix}${file}`] = fromDocs(path.join(targetDir, file));
    }
  }
  return aliases;
}
const docsThreeRoot = "./node_modules/three";
const docsThreeExamplesRoot = "./node_modules/three/examples";
const docsMeshoptimizer = "./node_modules/meshoptimizer";
const threeExample = (subpath: string) =>
  `./node_modules/three/examples/jsm/${subpath}`;

// Every bare specifier cadjs imports needs an entry here, and each deep subpath needs its
// OWN entry -- the "three/examples" alias above does not cover paths beneath it, which is
// why GLTFLoader was already listed individually.
//
// The reason aliases are load-bearing rather than a convenience: these imports live in
// packages/cadjs/src, outside docs/, so Node resolution walks up from THERE --
// packages/cadjs/node_modules, packages/node_modules, <repo>/node_modules -- and never
// reaches docs/node_modules. In a dev checkout packages/cadjs/node_modules exists and the
// build works by accident; on Vercel only docs/ is installed and it fails. Reproduce that
// locally by moving packages/{cadjs,implicitjs}/node_modules aside before building.
const cadJsBareImports = {
  ...implicitJsAliases(),
  meshoptimizer: docsMeshoptimizer,
  "three/examples/jsm/loaders/GLTFLoader.js": threeExample(
    "loaders/GLTFLoader.js",
  ),
  "three/examples/jsm/loaders/3MFLoader.js": threeExample(
    "loaders/3MFLoader.js",
  ),
  "three/examples/jsm/loaders/STLLoader.js": threeExample(
    "loaders/STLLoader.js",
  ),
  "three/examples/jsm/libs/fflate.module.js": threeExample(
    "libs/fflate.module.js",
  ),
  "three/examples/jsm/utils/BufferGeometryUtils.js": threeExample(
    "utils/BufferGeometryUtils.js",
  ),
};

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  experimental: {
    externalDir: true,
  },
  images: {
    remotePatterns: [
      {
        hostname: "www.skills.sh",
        protocol: "https",
      },
    ],
  },
  turbopack: {
    root: repoRoot,
    resolveAlias: {
      "cadjs": cadJsPackageRoot,
      three: docsThreeRoot,
      "three/examples": docsThreeExamplesRoot,
      ...cadJsBareImports,
    },
  },
};

export default nextConfig;
