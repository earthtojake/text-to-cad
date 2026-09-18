import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, expect, it } from "vitest";
import { emptyDrawingDocument } from "@hardcore/core/drawing";
import { createActions, RendererCommands } from "@main/cad/actions";
import type { BridgeSession } from "@main/cad/mcp-bridge";
import type { CadCommand } from "@shared/ipc/cad";

const temps: string[] = [];
afterEach(() => { for (const dir of temps.splice(0)) fs.rmSync(dir, { recursive: true, force: true }); });

function fixture(rootIsWorktree = false) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-drawing-"));
  temps.push(directory);
  const root = rootIsWorktree ? directory : null;
  const sent: CadCommand[] = [];
  const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: directory };
  const scene = JSON.stringify(emptyDrawingDocument());
  let reply: unknown = { scene };
  let refusal: string | null = null;
  let id = 0;
  const deps = {
    sessionRoot: () => ({ directory, root }), newId: () => `r${++id}`,
    send: (command: CadCommand) => {
      sent.push(command);
      commands.reply(refusal ? { requestId: command.requestId, ok: false, error: refusal }
        : { requestId: command.requestId, ok: true, result: reply });
    },
  };
  const commands = new RendererCommands(deps);
  return { directory, root, sent, session, scene, actions: createActions(deps, commands),
    setReply: (value: unknown) => { reply = value; }, setRefusal: (value: string) => { refusal = value; } };
}

it("opens blank and explicitly loaded drawings in the session root", async () => {
  const f = fixture(true);
  await f.actions.open_drawing(f.session, { title: "Sketch" });
  expect(f.sent[0]).toMatchObject({ kind: "open-drawing", projectId: "p", root: f.root, title: "Sketch" });
  expect(f.sent[0]).not.toHaveProperty("scene");
  fs.writeFileSync(path.join(f.directory, "plan.excalidraw"), f.scene);
  await f.actions.open_drawing(f.session, { path: "plan.excalidraw" });
  expect(f.sent[1]).toMatchObject({ kind: "open-drawing", path: "plan.excalidraw", title: "plan", scene: f.scene });
  fs.writeFileSync(path.join(f.directory, "invalid.excalidraw"), "{}");
  await expect(f.actions.open_drawing(f.session, { path: "invalid.excalidraw" })).rejects.toThrow();
  expect(f.sent).toHaveLength(2);
});

it("saves atomically, refuses an existing file by default, and replaces it only explicitly", async () => {
  const f = fixture();
  const result = await f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" });
  expect(result).toEqual({ saved: "plan.excalidraw", root: null, tabId: "drawing", ephemeral: true });
  expect(f.sent[0]).toMatchObject({ kind: "drawing-scene", projectId: "p", root: null, tabId: "drawing" });
  expect(fs.readFileSync(path.join(f.directory, "plan.excalidraw"), "utf8")).toBe(f.scene);
  fs.writeFileSync(path.join(f.directory, "plan.excalidraw"), "keep this");
  await expect(f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" })).rejects.toThrow("already exists");
  expect(fs.readFileSync(path.join(f.directory, "plan.excalidraw"), "utf8")).toBe("keep this");
  await f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw", overwrite: true });
  expect(fs.readFileSync(path.join(f.directory, "plan.excalidraw"), "utf8")).toBe(f.scene);
  expect(fs.readdirSync(f.directory)).toEqual(["plan.excalidraw"]);
});

it("refuses traversal and symlinks outside a session root, including new files", async () => {
  const f = fixture(true);
  const other = fixture();
  fs.writeFileSync(path.join(other.directory, "plan.excalidraw"), f.scene);
  fs.symlinkSync(other.directory, path.join(f.directory, "outside"), "dir");
  await expect(f.actions.open_drawing(f.session, { path: "outside/plan.excalidraw" })).rejects.toThrow("outside this session's worktree");
  await expect(f.actions.save_drawing(f.session, { tabId: "drawing", path: "../outside.excalidraw" })).rejects.toThrow("outside");
  await expect(f.actions.save_drawing(f.session, { tabId: "drawing", path: "outside/new.excalidraw" })).rejects.toThrow("outside");
  expect(f.sent).toEqual([]);
  expect(fs.existsSync(path.join(other.directory, "new.excalidraw"))).toBe(false);
});

it("never replaces a concurrent exclusive save to the same destination", async () => {
  const f = fixture();
  const result = await Promise.allSettled([
    f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" }),
    f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" }),
  ]);
  expect(result.filter(answer => answer.status === "fulfilled")).toHaveLength(1);
  expect(result.filter(answer => answer.status === "rejected")).toHaveLength(1);
  expect(fs.readFileSync(path.join(f.directory, "plan.excalidraw"), "utf8")).toBe(f.scene);
  expect(fs.readdirSync(f.directory)).toEqual(["plan.excalidraw"]);
});

it("does not write invalid, oversized or refused renderer scenes", async () => {
  const f = fixture();
  f.setReply({ scene: "{}" });
  await expect(f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" })).rejects.toThrow();
  f.setReply({ scene: " ".repeat(20 * 1024 * 1024 + 1) });
  await expect(f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" })).rejects.toThrow("20 MiB");
  fs.writeFileSync(path.join(f.directory, "large.excalidraw"), " ".repeat(20 * 1024 * 1024 + 1));
  await expect(f.actions.open_drawing(f.session, { path: "large.excalidraw" })).rejects.toThrow("20 MiB");
  f.setRefusal("that drawing belongs to another workspace root");
  await expect(f.actions.save_drawing(f.session, { tabId: "drawing", path: "plan.excalidraw" })).rejects.toThrow("another workspace root");
  expect(fs.existsSync(path.join(f.directory, "plan.excalidraw"))).toBe(false);
});
