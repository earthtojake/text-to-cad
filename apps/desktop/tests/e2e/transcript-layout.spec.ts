import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { _electron as electron, expect, test } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";

declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const command = "PYTHONPATH=/Users/amy/code/text-to-cad-jake-desktop/packages/cadgen/src /Users/amy/code/text-to-cad/.venv/bin/python models/ferrari.py --preview --preserve-colors";
const longTitle = `Check the generated preview at /Users/amy/Downloads/Hardcore-Jake-Preview/models/${"ferrari-preview-".repeat(12)}build.log`;

test("long activity stays inside the transcript and full details remain accessible", async () => {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-transcript-layout-")));
  const project = path.join(base, "Preview project");
  fs.mkdirSync(project);
  // Replay only: these commands and paths are displayed, never executed.
  const updates = [
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "I’ll check the car preview and keep the body colors in the viewer." } },
    { sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "Check the generated files first." } },
    { sessionUpdate: "tool_call", toolCallId: "read", title: "Read car.py", kind: "read", status: "completed", locations: [{ path: "models/car.py" }] },
    { sessionUpdate: "tool_call", toolCallId: "build", title: command, kind: "execute", status: "failed", rawInput: { command }, rawOutput: { output: "STEP export failed: incompatible color writer." } },
    { sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "Inspect the compatibility helper." } },
    { sessionUpdate: "tool_call", toolCallId: "inspect", title: command, kind: "execute", status: "completed", rawInput: { command }, rawOutput: { output: `Preview artifact: ${"ferrari".repeat(100)}.step` } },
    { sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "Read the build log." } },
    { sessionUpdate: "tool_call", toolCallId: "log", title: longTitle, kind: "other", status: "completed", rawOutput: "Preview files checked." },
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "The geometry is built. The color exporter needs a compatibility fix before the preview is ready." } },
  ];
  const fixture = path.join(base, "layout.jsonl");
  fs.writeFileSync(fixture, [
    { dir: "out", msg: { id: 1, method: "session/prompt" } },
    ...updates.map(update => ({ dir: "in", msg: { method: "session/update", params: { sessionId: "recorded", update } } })),
    { dir: "in", msg: { id: 1, result: { stopReason: "end_turn" } } },
  ].map(frame => JSON.stringify(frame)).join("\n"));
  const agent = path.join(base, "agent.mjs");
  fs.writeFileSync(agent, `process.argv.push("--fixture", ${JSON.stringify(fixture)});\nawait import(${JSON.stringify(pathToFileURL(path.join(appRoot, "tests/fake-agent/index.mjs")).href)});\n`);
  const app = await electron.launch({
    args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${path.join(base, "profile")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: agent },
  });
  try {
    const page = await app.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1000, 760));
    const added = await page.evaluate(root => window.hardcore.projects.addPath({ path: root }), project);
    const session = await page.evaluate(projectId => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "none" }), added.id);
    await page.locator(`[data-session-row="${session.id}"]`).getByRole("button").first().click();
    await page.evaluate(id => window.hardcore.sessions.prompt({ id, content: [{ type: "text", text: "Check the car preview." }] }), session.id);
    await expect(page.locator('[data-role="agent"]')).toContainText("The geometry is built.");
    const group = page.locator("[data-activity-group]");
    await expect(group.locator("[data-activity-failures]")).toHaveText("1 failed");
    await page.mouse.move(0, 0);
    await page.screenshot({ path: test.info().outputPath("transcript-light.png"), animations: "disabled" });
    const transcript = page.locator("[data-transcript]");
    const overflow = await transcript.locator("div,button").evaluateAll(nodes => nodes.filter(node => node.scrollWidth > node.clientWidth + 1).map(node => ({ tag: node.tagName, className: node.className, overflow: node.scrollWidth - node.clientWidth })));
    expect(overflow).toEqual([]);
    const summary = group.getByRole("button").first();
    const label = summary.locator("span").nth(1);
    const textRight = await label.evaluate(el => {
      const range = el.ownerDocument.createRange();
      range.selectNodeContents(el);
      return range.getBoundingClientRect().right;
    });
    const badgeBox = await group.locator("[data-activity-failures]").boundingBox();
    expect(badgeBox!.x - textRight).toBeLessThanOrEqual(12);
    const inspect = page.locator('[data-activity-row="inspect"]');
    await inspect.getByRole("button").click();
    await expect(inspect.locator("[data-tool-detail]")).toContainText(command);
    const detail = inspect.locator("[data-tool-detail]");
    expect(await detail.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
    expect(await transcript.evaluate(el => el.firstElementChild!.scrollWidth - el.firstElementChild!.clientWidth)).toBeLessThanOrEqual(1);
    const output = detail.locator(".max-h-72");
    await expect(output).toHaveText(`Preview artifact: ${"ferrari".repeat(100)}.step`);
    await page.screenshot({ path: test.info().outputPath("transcript-expanded.png"), animations: "disabled" });
    await inspect.getByRole("button").first().click();
    await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
    await page.screenshot({ path: test.info().outputPath("transcript-dark.png"), animations: "disabled" });
  } finally {
    await app.close();
    fs.rmSync(base, { recursive: true, force: true });
  }
});
