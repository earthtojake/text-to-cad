/**
 * AGENTS.md: every IPC channel is declared once and handled through
 * `registerIpc` — no `ipcMain.handle` outside `src/main/ipc/register.ts` —
 * and a contract branch under `src/shared/ipc/` takes `invoke` from
 * `./define`, because importing the contract's index from a branch is a
 * load-time cycle.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const srcRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "src");
const REGISTER = path.join("main", "ipc", "register.ts");

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sources(full);
    return /\.(ts|tsx|mts|mjs|js)$/.test(entry.name) ? [full] : [];
  });
}

const code = (file: string) =>
  readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

it("calls ipcMain.handle only in src/main/ipc/register.ts", () => {
  const offenders = ["main", "preload"]
    .flatMap((dir) => sources(path.join(srcRoot, dir)))
    .filter((file) => path.relative(srcRoot, file) !== REGISTER && /\bipcMain\s*\.\s*handle(Once)?\s*\(/.test(code(file)))
    .map((file) => path.relative(srcRoot, file));
  expect(offenders.join("\n"), "files calling ipcMain.handle outside register.ts").toBe("");
  // The one that must have it still does: a rename would empty the rule.
  expect(code(path.join(srcRoot, REGISTER))).toMatch(/\bipcMain\.handle\(/);
});

it("gives every contract branch its invoke from ./define and never imports the contract index", () => {
  const dir = path.join(srcRoot, "shared", "ipc");
  const branches = readdirSync(dir).filter((name) => name.endsWith(".ts") && !["index.ts", "define.ts", "errors.ts"].includes(name));
  expect(branches.length).toBeGreaterThan(5);
  const offenders = branches.flatMap((name) => {
    const text = code(path.join(dir, name));
    const statements = [...text.matchAll(/(?:^|\n)\s*import\s+([^;]*?)\s+from\s+["']([^"']+)["']/g)].map((match) => ({
      clause: match[1]!,
      from: match[2]!,
    }));
    const problems: string[] = [];
    for (const { clause, from } of statements) {
      if (["..", "../ipc", "../ipc/index", ".", "./index"].includes(from)) problems.push(`${name} imports the contract index ("${from}")`);
      if (/[{,]\s*invoke\b/.test(clause) && from !== "./define") problems.push(`${name} takes invoke from "${from}"`);
    }
    if (!statements.some(({ clause, from }) => from === "./define" && /[{,]\s*invoke\b/.test(clause))) {
      problems.push(`${name} does not import invoke from "./define"`);
    }
    return problems;
  });
  expect(offenders.join("\n"), "contract branches that break the ./define rule").toBe("");
});
