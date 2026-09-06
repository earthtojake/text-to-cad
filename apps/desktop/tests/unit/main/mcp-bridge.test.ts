import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { RendererCommands, createActions, resolveForSession } from "@main/cad/actions";
import { BRIDGE_ENV, McpBridge, type BridgeActions, type BridgeSession } from "@main/cad/mcp-bridge";
import type { CadCommand } from "@shared/ipc/cad";

const temps: string[] = [];
function tempDir(prefix: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  temps.push(dir);
  return dir;
}
const bridges: McpBridge[] = [];
afterEach(async () => {
  for (const bridge of bridges.splice(0)) {
    await bridge.stop();
  }
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

const SESSION: BridgeSession = { sessionId: "s1", projectId: "p1", cwd: "/proj" };

function recordingActions(): BridgeActions & { calls: Array<{ method: string; session: BridgeSession; params: unknown }> } {
  const calls: Array<{ method: string; session: BridgeSession; params: unknown }> = [];
  const record = (method: string) => async (session: BridgeSession, params: unknown) => {
    calls.push({ method, session, params });
    return { done: method };
  };
  return {
    calls,
    open_file: record("open_file"),
    reveal: record("reveal"),
    open_url: record("open_url"),
    list_open_tabs: record("list_open_tabs"),
    viewer_state: record("viewer_state"),
    attach_snapshot: async (session, params) => {
      calls.push({ method: "attach_snapshot", session, params });
      return { path: params.path, mimeType: "image/png", base64: "" };
    },
  };
}

async function startBridge(actions: BridgeActions = recordingActions()) {
  const bridge = new McpBridge(actions, () => ({ command: "/electron", args: ["/server.mjs"], env: { ELECTRON_RUN_AS_NODE: "1" } }));
  bridges.push(bridge);
  const url = await bridge.start();
  return { bridge, url };
}

async function rpc(url: string, token: string | null, body: unknown) {
  const response = await fetch(`${url}/rpc`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  return { status: response.status, body: (await response.json()) as { ok: boolean; result?: unknown; error?: string } };
}

describe("McpBridge", () => {
  it("listens on loopback and describes itself as a stdio MCP server per session", async () => {
    const { bridge, url } = await startBridge();
    expect(url).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
    const spec = bridge.serverFor(SESSION);
    expect(spec.name).toBe("hardcore");
    expect(spec).not.toHaveProperty("type");
    expect((spec as { command: string }).command).toBe("/electron");
    expect((spec as { args: string[] }).args).toEqual(["/server.mjs"]);
    const env = Object.fromEntries((spec as { env: Array<{ name: string; value: string }> }).env.map((entry) => [entry.name, entry.value]));
    expect(env.ELECTRON_RUN_AS_NODE).toBe("1");
    expect(env[BRIDGE_ENV.url]).toBe(url);
    expect(env[BRIDGE_ENV.cwd]).toBe("/proj");
    expect(env[BRIDGE_ENV.session]).toBe("s1");
    expect(env[BRIDGE_ENV.token]).toBe(bridge.tokenFor(SESSION));
    // One token per session, stable across calls.
    expect(bridge.tokenFor(SESSION)).toBe(bridge.tokenFor({ ...SESSION, cwd: "/proj/moved" }));
    expect(bridge.tokenFor({ ...SESSION, sessionId: "s2" })).not.toBe(bridge.tokenFor(SESSION));
  });

  it("refuses requests without a live session token", async () => {
    const { bridge, url } = await startBridge();
    expect((await rpc(url, null, { method: "list_open_tabs" })).status).toBe(401);
    expect((await rpc(url, "nope", { method: "list_open_tabs" })).status).toBe(401);
    const token = bridge.tokenFor(SESSION);
    expect((await rpc(url, token, { method: "list_open_tabs" })).status).toBe(200);
    bridge.revoke("s1");
    expect((await rpc(url, token, { method: "list_open_tabs" })).status).toBe(401);
  });

  it("dispatches each method to its action with the token's session", async () => {
    const actions = recordingActions();
    const { bridge, url } = await startBridge(actions);
    const token = bridge.tokenFor(SESSION);
    const answer = await rpc(url, token, { method: "open_file", params: { path: "a.step" } });
    expect(answer.body).toEqual({ ok: true, result: { done: "open_file" } });
    expect(actions.calls).toEqual([{ method: "open_file", session: SESSION, params: { path: "a.step" } }]);
    expect((await rpc(url, token, { method: "not_a_tool" })).status).toBe(400);
  });

  it("returns an action's refusal as ok:false with its message", async () => {
    const actions = recordingActions();
    actions.open_file = async () => {
      throw new Error("a.step is outside the project");
    };
    const { bridge, url } = await startBridge(actions);
    const answer = await rpc(url, bridge.tokenFor(SESSION), { method: "open_file", params: { path: "a.step" } });
    expect(answer.status).toBe(200);
    expect(answer.body).toEqual({ ok: false, error: "a.step is outside the project" });
  });
});

describe("RendererCommands", () => {
  it("pushes a command with a request id and resolves on the matching reply", async () => {
    const sent: CadCommand[] = [];
    let id = 0;
    const commands = new RendererCommands({ projectRoot: () => "/proj", send: (command) => sent.push(command), newId: () => `r${++id}` });
    const pending = commands.request({ kind: "open-file", projectId: "p1", path: "a.step" });
    expect(sent).toEqual([{ kind: "open-file", projectId: "p1", path: "a.step", requestId: "r1" }]);
    commands.reply({ requestId: "other", ok: true, result: 1 });
    commands.reply({ requestId: "r1", ok: true, result: { opened: "a.step" } });
    expect(await pending).toEqual({ opened: "a.step" });
  });

  it("rejects on a refusal and on a timeout", async () => {
    const commands = new RendererCommands({ projectRoot: () => "/proj", send: () => {}, newId: () => "r1", timeoutMs: 20 });
    const refused = commands.request({ kind: "reveal", projectId: "p1", path: "x" });
    commands.reply({ requestId: "r1", ok: false, error: "no such tab" });
    await expect(refused).rejects.toThrow("no such tab");
    await expect(commands.request({ kind: "list-tabs", projectId: "p1" })).rejects.toThrow("did not answer");
  });
});

describe("the actions", () => {
  it("resolve paths against the session cwd, inside the project, and answer project-relative", async () => {
    const root = tempDir("hardcore-proj-");
    fs.mkdirSync(path.join(root, "STEP"));
    fs.writeFileSync(path.join(root, "STEP", "a.step"), "");
    const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: path.join(root, "STEP") };
    const deps = { projectRoot: () => root };
    expect((await resolveForSession(deps, session, "a.step")).relative).toBe("STEP/a.step");
    expect((await resolveForSession(deps, session, path.join(root, "STEP", "a.step"))).relative).toBe("STEP/a.step");
    await expect(resolveForSession(deps, session, "../../etc/passwd")).rejects.toThrow("outside the project");
    await expect(resolveForSession(deps, session, "missing.step")).rejects.toThrow("does not exist");
    await expect(resolveForSession({ projectRoot: () => null }, session, "a.step")).rejects.toThrow("no longer open");
  });

  it("relay open_file and reveal with the resolved path, and answer attach_snapshot from disk", async () => {
    const root = tempDir("hardcore-proj-");
    fs.mkdirSync(path.join(root, "tmp"));
    fs.writeFileSync(path.join(root, "part.step"), "");
    fs.writeFileSync(path.join(root, "tmp", "review.png"), Buffer.from([0x89, 0x50, 0x4e, 0x47]));
    fs.writeFileSync(path.join(root, "notes.txt"), "text");
    const sent: CadCommand[] = [];
    const commands = new RendererCommands({ projectRoot: () => root, send: (command) => sent.push(command), newId: () => "r" });
    const actions = createActions({ projectRoot: () => root, send: () => {}, newId: () => "r" }, commands);
    const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: root };

    // The action resolves the path before it asks the renderer, so the reply
    // has to wait for the command to have been sent.
    const sentCount = () => sent.length;
    const untilSent = async (count: number) => {
      while (sentCount() < count) {
        await new Promise((resolve) => setTimeout(resolve, 5));
      }
    };
    const opened = actions.open_file(session, { path: "part.step" });
    await untilSent(1);
    commands.reply({ requestId: "r", ok: true, result: { opened: "part.step" } });
    expect(await opened).toEqual({ opened: "part.step" });
    expect(sent[0]).toMatchObject({ kind: "open-file", path: "part.step", projectId: "p" });

    await expect(actions.open_file(session, { path: "tmp" })).rejects.toThrow("is a directory");

    const revealed = actions.reveal(session, { path: "tmp" });
    await untilSent(2);
    commands.reply({ requestId: "r", ok: true, result: { revealed: "tmp" } });
    await revealed;
    expect(sent[1]).toMatchObject({ kind: "reveal", path: "tmp", directory: true });

    await expect(actions.open_url(session, { url: "file:///etc/passwd" })).rejects.toThrow("http(s)");

    const snapshot = await actions.attach_snapshot(session, { path: "tmp/review.png" });
    expect(snapshot).toEqual({ path: "tmp/review.png", mimeType: "image/png", base64: Buffer.from([0x89, 0x50, 0x4e, 0x47]).toString("base64") });
    await expect(actions.attach_snapshot(session, { path: "notes.txt" })).rejects.toThrow("not a PNG");
  });
});
