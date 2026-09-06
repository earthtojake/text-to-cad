/**
 * Refreshes `src/renderer/assets/agents/*.svg` from the public ACP registry.
 *
 * The registry publishes one SVG per agent beside the JSON that describes it
 * (https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json, field
 * `icon`). The mapping from our provider ids to theirs is not written down
 * twice: it is read out of `src/main/agents/registry.ts`, whose `registryId`
 * column exists for exactly this. An agent with `registryId: null` has no icon
 * to fetch and keeps its letter mark.
 *
 * The files are committed. This script is how they are refreshed — a command
 * rather than a chore — and running it should produce either no diff or a diff
 * that is one vendor's new logo.
 *
 * Usage: `node scripts/fetch-agent-icons.mjs [--dry-run]`
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const registrySource = path.join(appRoot, "src", "main", "agents", "registry.ts");
const outDir = path.join(appRoot, "src", "renderer", "assets", "agents");
const REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json";

const dryRun = process.argv.includes("--dry-run");

/**
 * `[providerId, registryId | null]` for every row in the provider table.
 *
 * A regular expression rather than a TypeScript parse: the two fields are
 * literals a few lines apart in every row, and the alternative is compiling the
 * module in a script whose whole job is to download some pictures.
 */
function providers() {
  const source = fs.readFileSync(registrySource, "utf8");
  const rows = [...source.matchAll(/\bid: "([^"]+)",[\s\S]*?registryId: (?:"([^"]+)"|null),/g)];
  return rows.map((row) => [row[1], row[2] ?? null]);
}

/**
 * An SVG is a document that can carry script and can fetch. These are written
 * into the app's bundle, so anything that could execute or phone home is a
 * reason to refuse the file rather than to sanitise it.
 */
function assertInert(id, svg) {
  const suspicious = [/<script/i, /\son\w+\s*=/i, /<foreignObject/i, /href\s*=\s*["']?https?:/i];
  for (const pattern of suspicious) {
    if (pattern.test(svg)) {
      throw new Error(`${id}: the SVG contains ${pattern} — refusing to commit it`);
    }
  }
  if (!svg.trimStart().startsWith("<")) {
    throw new Error(`${id}: not an SVG`);
  }
}

async function main() {
  const response = await fetch(REGISTRY_URL);
  if (!response.ok) {
    throw new Error(`registry: HTTP ${response.status}`);
  }
  const registry = await response.json();
  const icons = new Map(registry.agents.map((agent) => [agent.id, agent.icon]));

  fs.mkdirSync(outDir, { recursive: true });
  const missing = [];
  let written = 0;

  for (const [providerId, registryId] of providers()) {
    const url = registryId ? icons.get(registryId) : undefined;
    if (!url) {
      missing.push(providerId);
      continue;
    }
    const svg = await fetch(url).then((answer) => {
      if (!answer.ok) {
        throw new Error(`${providerId}: HTTP ${answer.status} for ${url}`);
      }
      return answer.text();
    });
    assertInert(providerId, svg);
    if (!dryRun) {
      fs.writeFileSync(path.join(outDir, `${providerId}.svg`), svg.trimEnd() + "\n");
    }
    written += 1;
    console.info(`${providerId}  <-  ${url}`);
  }

  console.info(`\n${written} icons; no registry icon for: ${missing.join(", ") || "none"}`);
  console.info("Providers without an icon keep the letter mark (AgentMark).");
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
