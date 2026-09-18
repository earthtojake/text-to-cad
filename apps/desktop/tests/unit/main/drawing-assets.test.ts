import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import vm from "node:vm";
import { build } from "esbuild";

import { describe, expect, it } from "vitest";

import {
  drawingAssetBootstrap,
  drawingAssetFiles,
  drawingAssetsPlugin,
  localizeDrawingFontFallback,
} from "../../../scripts/drawing-assets.mjs";

const require = createRequire(import.meta.url);
const packageRoot = path.resolve(path.dirname(require.resolve("@excalidraw/excalidraw")), "../..");

function fontChunks(flavor: string) {
  const root = path.join(packageRoot, "dist", flavor);
  return fs.readdirSync(root)
    .filter(name => name.endsWith(".js"))
    .map(name => ({ id: path.join(root, name), code: fs.readFileSync(path.join(root, name), "utf8") }))
    .filter(file => file.code.includes("ASSETS_FALLBACK_URL"));
}

describe("offline desktop drawing assets", () => {
  it.each([
    ["http://127.0.0.1:5273/index.html", "http://127.0.0.1:5273/excalidraw/"],
    ["file:///Applications/Hardcore.app/Contents/Resources/app.asar/out/renderer/index.html", "file:///Applications/Hardcore.app/Contents/Resources/app.asar/out/renderer/excalidraw/"],
    ["file:///tmp/Hardcore%20test/out/renderer/index.html", "file:///tmp/Hardcore%20test/out/renderer/excalidraw/"],
  ])("sets an absolute font directory before importing the SDK at %s", (baseURI, expected) => {
    const window: { EXCALIDRAW_ASSET_PATH?: string } = {};
    vm.runInNewContext(drawingAssetBootstrap, { window, document: { baseURI }, URL });
    expect(window.EXCALIDRAW_ASSET_PATH).toBe(expected);
  });

  it("ships every installed font and its separate license notice", () => {
    const files = drawingAssetFiles();
    const byName = new Map(files.map(file => [file.fileName, file.source]));
    const fonts = files.filter(file => /\.(woff2|ttf)$/.test(file.fileName));
    expect(fonts).toHaveLength(234);
    const families = new Set(fonts.map(file => file.fileName.split("/")[2]));
    expect(families.size).toBe(9);
    for (const family of families) {
      expect(files.some(file => file.fileName.startsWith(`excalidraw/licenses/${family}-`))).toBe(true);
    }
    expect(byName.get("excalidraw/licenses/Excalidraw-MIT.txt")?.toString()).toContain("Copyright (c) 2020 Excalidraw");
    expect(byName.get("excalidraw/licenses/Liberation-OFL.txt")?.toString()).toContain("SIL OPEN FONT LICENSE");
    expect(files.some(file => /GPL|font-exception/.test(file.fileName))).toBe(false);
    expect(byName.has("excalidraw/fonts/Liberation/LiberationSans-Regular.woff2")).toBe(false);
    const replacementRoot = path.dirname(require.resolve("@betteroffice/fonts/package.json"));
    expect(byName.get("excalidraw/fonts/Liberation/LiberationSans-Regular.ttf")).toEqual(
      fs.readFileSync(path.join(replacementRoot, "assets/LiberationSans-Regular.ttf")),
    );
    // Byte-identical to the official liberation-fonts-ttf-2.1.5 release:
    // https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz
    expect(createHash("sha256").update(byName.get("excalidraw/fonts/Liberation/LiberationSans-Regular.ttf")!).digest("hex"))
      .toBe("76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8");
    expect(createHash("sha256").update(byName.get("excalidraw/licenses/Liberation-OFL.txt")!).digest("hex"))
      .toBe("93fed46019c38bbe566b479d22148e2e8a1e85ada614accb0211c37b2c61c19b");
    for (const flavor of ["dev", "prod"]) {
      for (const { code } of fontChunks(flavor)) {
        const references = [...localizeDrawingFontFallback(code)!.matchAll(/"\.\/fonts\/([^"\n]+\.(?:woff2|ttf))"/g)];
        expect(references.length).toBeGreaterThan(200);
        for (const [, font] of references) expect(byName.has(`excalidraw/fonts/${font}`)).toBe(true);
      }
    }
  });

  it.each(["dev", "prod"])("replaces the installed %s SDK's CDN fallback without modifying node_modules", async flavor => {
    const chunks = fontChunks(flavor);
    expect(chunks).toHaveLength(1);
    for (const { code, id } of chunks) {
      const localized = localizeDrawingFontFallback(code)!;
      expect(localized).toContain('new URL("./excalidraw/", document.baseURI).href');
      expect(localized).not.toContain("https://esm.sh/");
      expect(localized).toContain("./fonts/Liberation/LiberationSans-Regular.ttf");
      expect(localized).not.toContain("./fonts/Liberation/LiberationSans-Regular.woff2");
      expect(localized).toContain('.pop().replace("ttf", "truetype")');
      const getFormat = localized.slice(localized.indexOf("static getFormat("), localized.indexOf("static normalizeBaseUrl("));
      const formats = vm.runInNewContext(`(class { ${getFormat} })`, { URL }) as { getFormat: (url: URL) => string };
      expect(formats.getFormat(new URL("file:///app/excalidraw/fonts/Liberation/LiberationSans-Regular.ttf"))).toBe("format('truetype')");
      expect(formats.getFormat(new URL("file:///app/excalidraw/fonts/Virgil/Virgil-Regular.woff2"))).toBe("format('woff2')");
      const contentMethod = localized.match(/async getContent\([\s\S]+?\}(?=\s*fetchFont\()/)?.[0];
      expect(contentMethod).toBeDefined();
      const Font = vm.runInNewContext(`(class { ${contentMethod} })`, { URL, DataView, Uint8Array, btoa, console }) as new () => {
        urls: URL[]; fetchFont: () => Promise<ArrayBuffer>; getContent: (codePoints: number[]) => Promise<string>;
      };
      const font = new Font();
      const rawFont = drawingAssetFiles().find(file => file.fileName.endsWith("LiberationSans-Regular.ttf"))!.source;
      font.urls = [new URL("file:///app/excalidraw/fonts/Liberation/LiberationSans-Regular.ttf")];
      font.fetchFont = async () => rawFont.buffer.slice(rawFont.byteOffset, rawFont.byteOffset + rawFont.byteLength) as ArrayBuffer;
      expect(await font.getContent([65])).toBe(`data:font/ttf;base64,${rawFont.toString("base64")}`);
      const transform = drawingAssetsPlugin().transform;
      expect(typeof transform).toBe("function");
      if (typeof transform === "function") {
        const result = transform.call({} as never, code, id);
        expect(result).toEqual({ code: localized, map: null });
      }
      expect(fs.readFileSync(id, "utf8")).toBe(code);
    }
  });

  it("fails review when the upstream fallback changes", () => {
    expect(() => localizeDrawingFontFallback('const ASSETS_FALLBACK_URL = "https://different.example/fonts"')).toThrow("review offline asset adaptation");
    expect(localizeDrawingFontFallback("export const unrelated = true")).toBeNull();
  });

  it("adapts optimized SDK modules while preserving CommonJS dependency optimization", async () => {
    const config = drawingAssetsPlugin().config;
    if (typeof config !== "function") throw new Error("Drawing assets must configure the development optimizer");
    const options = await config.call({} as never, {}, { command: "serve", mode: "development" });
    expect(options?.optimizeDeps?.exclude ?? []).not.toContain("@excalidraw/excalidraw");
    const plugins = options?.optimizeDeps?.esbuildOptions?.plugins;
    expect(plugins).toHaveLength(1);
    const chunk = fontChunks("dev")[0]!;
    const result = await build({ entryPoints: [chunk.id], bundle: false, write: false, plugins });
    const output = result.outputFiles![0]!.text;
    expect(output).not.toContain("https://esm.sh/");
    expect(output).toContain("./fonts/Liberation/LiberationSans-Regular.ttf");
    expect(output).toContain('new URL("./excalidraw/", document.baseURI).href');
  });
});
