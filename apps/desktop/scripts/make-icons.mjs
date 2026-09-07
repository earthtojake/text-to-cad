/**
 * Writes `build/icon.png`, the app's one icon source, from the docs site's
 * favicon (`apps/docs/public/favicon.png`): the same mark the product shows
 * everywhere else. electron-builder derives the macOS .icns and the Windows
 * .ico from this PNG at package time, so nothing else is generated or
 * committed. Run `npm run icons` after the favicon changes.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.resolve(appRoot, "..", "docs", "public", "favicon.png");
const target = path.join(appRoot, "build", "icon.png");

if (!fs.existsSync(source)) {
  console.error(`make-icons: favicon not found at ${source}`);
  process.exit(1);
}
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.copyFileSync(source, target);
console.log(`make-icons: wrote ${path.relative(appRoot, target)} from ${path.relative(appRoot, source)}`);
