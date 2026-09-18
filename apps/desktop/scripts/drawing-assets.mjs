/** Desktop-owned Excalidraw assets: HTTP development and file:// production. */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const noticesRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../licenses/excalidraw");
export const DRAWING_ASSET_DIRECTORY = "excalidraw";
export const DRAWING_ASSET_BOOTSTRAP = "drawing-assets.js";
export const drawingAssetBootstrap = 'window.EXCALIDRAW_ASSET_PATH = new URL("./excalidraw/", document.baseURI).href;\n';

export function drawingAssetFiles() {
  const packageRoot = path.resolve(path.dirname(require.resolve("@excalidraw/excalidraw")), "../..");
  const sdk = JSON.parse(fs.readFileSync(path.join(packageRoot, "package.json"), "utf8"));
  if (sdk.version !== "0.18.1") {
    throw new Error("Review Excalidraw offline font loading and licenses before updating drawing-assets.mjs for a new SDK version");
  }
  const files = [{ fileName: DRAWING_ASSET_BOOTSTRAP, source: Buffer.from(drawingAssetBootstrap) }];
  const addTree = (root, prefix) => {
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
      const fullPath = path.join(root, entry.name);
      const fileName = `${prefix}/${entry.name}`;
      if (entry.isDirectory()) addTree(fullPath, fileName);
      else if (entry.isFile()) {
        // Excalidraw ships GPL Liberation 1.05. Use unmodified OFL 2.1.5
        // instead, preserving the upstream font name and binary metadata.
        if (fileName === "excalidraw/fonts/Liberation/LiberationSans-Regular.woff2") continue;
        files.push({ fileName, source: fs.readFileSync(fullPath) });
      }
      else throw new Error(`Drawing asset must be a regular file: ${fullPath}`);
    }
  };
  addTree(path.join(packageRoot, "dist/prod/fonts"), `${DRAWING_ASSET_DIRECTORY}/fonts`);
  const replacementRoot = path.dirname(require.resolve("@betteroffice/fonts/package.json"));
  const replacementPackage = JSON.parse(fs.readFileSync(path.join(replacementRoot, "package.json"), "utf8"));
  if (replacementPackage.version !== "0.2.0") throw new Error("Review the pinned Liberation Sans replacement before changing font assets");
  files.push({
    fileName: "excalidraw/fonts/Liberation/LiberationSans-Regular.ttf",
    source: fs.readFileSync(path.join(replacementRoot, "assets/LiberationSans-Regular.ttf")),
  });
  files.push({
    fileName: "excalidraw/licenses/Liberation-OFL.txt",
    source: fs.readFileSync(path.join(replacementRoot, "LICENSES/OFL-Liberation.txt")),
  });
  addTree(noticesRoot, `${DRAWING_ASSET_DIRECTORY}/licenses`);
  return files;
}

/** The SDK has no public switch for its CDN fallback; adapt bundled code only. */
export function localizeDrawingFontFallback(code) {
  if (!code.includes("ASSETS_FALLBACK_URL")) return null;
  const pattern = /"ASSETS_FALLBACK_URL",\s*`https:\/\/esm\.sh\/\$\{[^;]+?\/dist\/prod\/`/g;
  const matches = [...code.matchAll(pattern)];
  if (matches.length !== 1) throw new Error("Excalidraw font fallback changed; review offline asset adaptation");
  const fontUri = "./fonts/Liberation/LiberationSans-Regular.woff2";
  if (code.split(fontUri).length !== 2) throw new Error("Excalidraw Liberation font registration changed; review OFL replacement");
  const formatPattern = /format\('\$\{([\w$]+)\.pop\(\)\}'\)/g;
  if ([...code.matchAll(formatPattern)].length !== 1) throw new Error("Excalidraw font format hint changed; review OFL replacement");
  const fontFetchPattern = /((?:const|let)\s+([\w$]+)\s*=\s*await this\.fetchFont\(([\w$]+)\);)/g;
  if ([...code.matchAll(fontFetchPattern)].length !== 1) throw new Error("Excalidraw embedded font loading changed; review OFL replacement");
  return code
    .replace(pattern, '"ASSETS_FALLBACK_URL", new URL("./excalidraw/", document.baseURI).href')
    .replace(fontUri, "./fonts/Liberation/LiberationSans-Regular.ttf")
    .replace(formatPattern, (_match, parts) => `format('\${${parts}.pop().replace("ttf", "truetype")}')`)
    // WOFF2 subsetting cannot process the unmodified upstream TTF. Embed that
    // original font directly for SVG exports, retaining its OFL metadata.
    .replace(fontFetchPattern, (_match, statement, buffer) => `${statement}
      if (new DataView(${buffer}).getUint32(0) === 0x00010000) {
        return "data:font/ttf;base64," + btoa(Array.from(new Uint8Array(${buffer}), byte => String.fromCharCode(byte)).join(""));
      }`);
}

/** @returns {import("vite").Plugin} */
export function drawingAssetsPlugin() {
  let files;
  return {
    name: "hardcore-offline-drawing-assets",
    enforce: "pre",
    // Keep dependency optimization: SDK transitive CommonJS dependencies need
    // browser-compatible wrappers. Apply the same adaptation inside esbuild,
    // since optimizer output otherwise bypasses the ordinary Vite transform.
    config() {
      return {
        optimizeDeps: {
          esbuildOptions: {
            plugins: [{
              name: "hardcore-offline-drawing-fonts",
              setup(build) {
                build.onLoad({ filter: /@excalidraw[\\/]excalidraw[\\/]dist[\\/](dev|prod)[\\/][^\\/]+\.js$/ }, args => {
                  const code = fs.readFileSync(args.path, "utf8");
                  return {
                    contents: localizeDrawingFontFallback(code) ?? code,
                    loader: "js",
                    resolveDir: path.dirname(args.path),
                  };
                });
              },
            }],
          },
        },
      };
    },
    buildStart() { files = drawingAssetFiles(); },
    transform(code, id) {
      if (!/\/@excalidraw\/excalidraw\/dist\/(dev|prod)\/[^/]+\.js(?:\?|$)/.test(id.replaceAll("\\", "/"))) return null;
      const localized = localizeDrawingFontFallback(code);
      return localized === null ? null : { code: localized, map: null };
    },
    // A classic external script runs before every renderer module. CSP allows
    // self-hosted scripts and needs no unsafe-inline exception for this setup.
    transformIndexHtml: {
      order: "post",
      handler() {
        return [{ tag: "script", attrs: { src: `./${DRAWING_ASSET_BOOTSTRAP}` }, injectTo: "head-prepend" }];
      },
    },
    configureServer(server) {
      const assets = new Map(drawingAssetFiles().map(file => [`/${file.fileName}`, file]));
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
        const file = assets.get(pathname);
        if (!file) return next();
        response.setHeader("Content-Type", file.fileName.endsWith(".woff2") ? "font/woff2" : file.fileName.endsWith(".ttf") ? "font/ttf" : file.fileName.endsWith(".js") ? "application/javascript" : "text/plain; charset=utf-8");
        response.end(file.source);
      });
    },
    generateBundle() {
      for (const file of files ?? drawingAssetFiles()) this.emitFile({ type: "asset", ...file });
    },
  };
}
