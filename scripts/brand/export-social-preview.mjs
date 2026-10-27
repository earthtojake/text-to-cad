// Manual authoring tool. Ordinary docs builds consume the committed PNG/MP4.
import { build } from "esbuild";
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const source = path.join(root, "scripts/brand/social-preview");
const publicDir = path.join(root, "apps/docs/public");
const stillOnly = process.argv.includes("--still");
const fps = 60;
const frameCount = 12 * fps;
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), "texttocad-social-"));
let browser;
try {
  await build({
    entryPoints: [path.join(source, "scene.ts")], bundle: true, format: "esm",
    outfile: path.join(scratch, "render.js"),
  });
  const html = (await fs.readFile(path.join(source, "index.html"), "utf8"))
    .replace("{{WORDMARK}}", await fs.readFile(path.join(publicDir, "brand/logo-texttocad-animated.svg"), "utf8"));
  browser = await chromium.launch({
    headless: true,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
  });
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error));
  // Route assets in-process: no local HTTP server or port is required.
  await page.route("http://preview.local/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/") {
      await route.fulfill({ body: html, contentType: "text/html; charset=utf-8" });
      return;
    }
    const file = pathname === "/render.js"
      ? path.join(scratch, "render.js")
      : pathname.startsWith("/hero/") ? path.resolve(publicDir, `.${pathname}`) : null;
    if (!file || (pathname !== "/render.js" && !file.startsWith(path.join(publicDir, "hero") + path.sep))) {
      await route.abort();
      return;
    }
    try {
      await route.fulfill({
        body: await fs.readFile(file),
        contentType: file.endsWith(".js") ? "text/javascript" : file.endsWith(".json") ? "application/json" : "application/octet-stream",
      });
    } catch {
      await route.abort();
    }
  });
  await page.goto("http://preview.local/");
  await page.waitForFunction(() => window.ready, {}, { timeout: 120000 });
  await page.evaluate(() => window.renderAt(8));
  const poster = path.join(scratch, "poster.png");
  await page.screenshot({ path: poster });
  if (!stillOnly) {
    for (let frame = 0; frame < frameCount; frame++) {
      await page.evaluate(time => window.renderAt(time), frame / fps);
      await page.screenshot({ path: path.join(scratch, `${String(frame).padStart(4, "0")}.png`) });
      if (frame % 120 === 0) console.log(`Frame ${frame}/${frameCount}`);
    }
    const video = path.join(scratch, "preview.mp4");
    execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-framerate", String(fps),
      "-i", path.join(scratch, "%04d.png"), "-c:v", "libx264", "-preset", "slow", "-crf", "22",
      "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", video], { stdio: "inherit" });
    execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-i", video, "-f", "null", "-"], { stdio: "inherit" });
    const { size } = await fs.stat(video);
    if (size >= 5 * 1024 * 1024) throw new Error(`Video exceeds the repository file limit: ${size} bytes`);
    if (pageErrors.length) throw pageErrors[0];
    await fs.copyFile(video, path.join(publicDir, "social-preview-products.mp4"));
    console.log(`MP4: ${size} bytes`);
  }
  if (pageErrors.length) throw pageErrors[0];
  await fs.copyFile(poster, path.join(publicDir, "social-preview-products.png"));
  console.log("Social preview saved.");
} finally {
  await browser?.close();
  await fs.rm(scratch, { recursive: true, force: true });
}
