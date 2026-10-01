import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import fsp from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { RendererCommands, createActions, resolveForSession } from "@main/integrations/actions";
import { BRIDGE_ENV, McpBridge, type BridgeSession } from "@main/integrations/mcp-bridge";
import type { IntegrationCommand } from "@shared/ipc/integrations";

// The full eight bytes: the source matches the whole signature, not its first four.
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
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

function recordingActions() {
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
    open_drawing: record("open_drawing"),
    list_open_tabs: record("list_open_tabs"),
    viewer_state: record("viewer_state"),
    attach_snapshot: async (session: BridgeSession, params: Record<string, unknown>) => {
      calls.push({ method: "attach_snapshot", session, params });
      return { path: params.path, mimeType: "image/png", base64: "" };
    },
  };
}

async function startBridge(recorded = recordingActions()) {
  const { calls: _calls, ...actions } = recorded;
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
  it("logs an error the listener reports after it started, rather than throwing it", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    try {
      const { bridge } = await startBridge();
      const server = (bridge as unknown as { server: http.Server }).server;
      expect(() => server.emit("error", new Error("EMFILE: too many open files"))).not.toThrow();
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("EMFILE: too many open files"));
    } finally {
      warn.mockRestore();
    }
  });

  it("listens on loopback and describes itself as a stdio MCP server per session", async () => {
    const { bridge, url } = await startBridge();
    expect(url).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
    const spec = bridge.serverFor(SESSION);
    expect(spec.name).toBe("text-to-cad-workspace");
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

  it("rejects non-object JSON and revokes an in-flight request", async () => {
    const actions = recordingActions();
    let began!: () => void;
    const started = new Promise<void>(resolve => { began = resolve; });
    actions.open_file = async (_session, _params, signal?: AbortSignal) => {
      began();
      await new Promise<void>((_resolve, reject) => signal!.addEventListener("abort", () => reject(signal!.reason), { once: true }));
      return { done: "open_file" };
    };
    const { bridge, url } = await startBridge(actions);
    const token = bridge.tokenFor(SESSION);
    for (const body of [null, [], "hello", 42]) expect((await rpc(url, token, body)).status).toBe(400);
    const pending = rpc(url, token, { method: "open_file", params: { path: "a.txt" } });
    await started;
    bridge.revoke(SESSION.sessionId);
    expect((await pending).body).toMatchObject({ ok: false, error: "Session authorization revoked" });
  });

  it("says an action applied when the session was revoked after the handler finished", async () => {
    const actions = recordingActions();
    let began!: () => void;
    const started = new Promise<void>(resolve => { began = resolve; });
    let finish!: () => void;
    // Ignores the signal, as write_terminal and edit_document do: it completes.
    actions.open_file = async () => {
      began();
      await new Promise<void>(resolve => { finish = resolve; });
      return { done: "open_file" };
    };
    const { bridge, url } = await startBridge(actions);
    const pending = rpc(url, bridge.tokenFor(SESSION), { method: "open_file", params: { path: "a.txt" } });
    await started;
    bridge.revoke(SESSION.sessionId);
    finish();
    expect((await pending).body).toMatchObject({ ok: false, error: expect.stringMatching(/applied/) });
  });

  it("says a relayed edit may have been applied when the session is revoked while the window holds it", async () => {
    const root = fs.realpathSync(tempDir("text-to-cad-proj-"));
    let sentCommand!: () => void;
    const sent = new Promise<void>(resolve => { sentCommand = resolve; });
    const deps = { sessionRoot: () => ({ directory: root, root: null }), send: () => sentCommand(), newId: () => "r" };
    const { bridge, url } = await startBridge(Object.assign(recordingActions(), createActions(deps, new RendererCommands(deps))));
    const pending = rpc(url, bridge.tokenFor({ ...SESSION, cwd: root }, "documents"), { method: "edit_document", params: { tabId: "t", expectedRevision: "r", content: "x" } });
    await sent;
    bridge.revoke(SESSION.sessionId);
    expect((await pending).body).toMatchObject({ ok: false, error: expect.stringMatching(/may already have been applied.*Session authorization revoked/) });
  });

  /** POST a body in two halves; `between` runs once the server has authorised the request and before the rest is sent. */
  async function slowRpc(bridge: McpBridge, url: string, token: string, body: unknown, between: () => void) {
    const byToken = (bridge as unknown as { byToken: Map<string, unknown> }).byToken;
    const get = byToken.get.bind(byToken);
    let authorised!: () => void;
    const seen = new Promise<void>(resolve => { authorised = resolve; });
    const spy = vi.spyOn(byToken, "get").mockImplementation((key: string) => { authorised(); return get(key); });
    const text = JSON.stringify(body);
    return new Promise<{ status: number; body: { ok: boolean; error?: string } }>((resolve, reject) => {
      const request = http.request(`${url}/rpc`, { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" } }, response => {
        const chunks: Buffer[] = [];
        response.on("data", chunk => chunks.push(chunk));
        response.on("end", () => { spy.mockRestore(); resolve({ status: response.statusCode!, body: JSON.parse(Buffer.concat(chunks).toString()) }); });
      });
      request.on("error", reject);
      request.write(text.slice(0, 10));
      void seen.then(() => { between(); request.end(text.slice(10)); });
    });
  }

  it("does not reject an upload because another serverFor re-recorded its token while the body was arriving", async () => {
    const { bridge, url } = await startBridge();
    const token = bridge.tokenFor(SESSION);
    const answer = await slowRpc(bridge, url, token, { method: "open_file", params: { path: "a.step" } },
      () => { bridge.serverFor({ ...SESSION }); });
    expect(answer).toMatchObject({ status: 200, body: { ok: true } });
  });

  it("still rejects an upload whose token was revoked, or whose workspace moved, while the body was arriving", async () => {
    const { bridge, url } = await startBridge();
    const revoked = await slowRpc(bridge, url, bridge.tokenFor(SESSION), { method: "open_file", params: { path: "a.step" } },
      () => bridge.revoke(SESSION.sessionId));
    expect(revoked).toMatchObject({ status: 401, body: { error: "session authorization changed" } });
    const moved = await slowRpc(bridge, url, bridge.tokenFor(SESSION), { method: "open_file", params: { path: "a.step" } },
      () => { bridge.tokenFor({ ...SESSION, cwd: "/elsewhere" }); });
    expect(moved).toMatchObject({ status: 401, body: { error: "session authorization changed" } });
  });

  it("disposes the session's pages when its workspace changes, and not when it is merely asked for again", async () => {
    const disposePages = vi.fn();
    const { calls: _calls, ...actions } = recordingActions();
    const bridge = new McpBridge(actions, () => ({ command: "/electron", args: ["/server.mjs"], env: {} }), { revoke: vi.fn(), disposePages, dispose: async () => {} });
    bridges.push(bridge);
    await bridge.start();
    bridge.tokenFor(SESSION);
    bridge.tokenFor({ ...SESSION });
    expect(disposePages).not.toHaveBeenCalled();
    bridge.tokenFor({ ...SESSION, cwd: "/elsewhere" });
    expect(disposePages).toHaveBeenCalledExactlyOnceWith({ ...SESSION, cwd: "/elsewhere" });
  });

  it("closes its listener even when disposing the resources rejects, and reports the rejection", async () => {
    const { calls: _calls, ...actions } = recordingActions();
    const bridge = new McpBridge(actions, () => ({ command: "/electron", args: ["/server.mjs"], env: {} }), {
      revoke: vi.fn(),
      dispose: async () => { throw new Error("pages would not close"); },
    });
    const url = await bridge.start();
    expect((await fetch(`${url}/rpc`, { method: "POST" })).status).toBeGreaterThan(0);
    await expect(bridge.stop()).rejects.toThrow("pages would not close");
    // Gone from the loopback, not just forgotten by the bridge.
    await expect(fetch(`${url}/rpc`, { method: "POST" })).rejects.toThrow();
  });

  it("takes the largest document edit_document's schema accepts, in its worst-case JSON", async () => {
    const edits: unknown[] = [];
    const recorded = Object.assign(recordingActions(), {
      edit_document: async (_session: BridgeSession, params: Record<string, unknown>) => { edits.push(params); return { ok: true }; },
    });
    const { bridge, url } = await startBridge(recorded);
    // Two million control characters: each one is six bytes of JSON (`\u0001`).
    const content = "\u0001".repeat(2 * 1024 * 1024);
    const answer = await rpc(url, bridge.tokenFor(SESSION, "documents"), { method: "edit_document", params: { tabId: "t", expectedRevision: "r", content } });
    expect(answer.status).toBe(200);
    expect(edits).toHaveLength(1);
  });

  it("dispatches each method to its action with the token's session", async () => {
    const actions = recordingActions();
    const { bridge, url } = await startBridge(actions);
    const token = bridge.tokenFor(SESSION);
    const answer = await rpc(url, token, { method: "open_file", params: { path: "a.step" } });
    expect(answer.body).toEqual({ ok: true, result: { done: "open_file" } });
    expect(actions.calls).toEqual([{ method: "open_file", session: SESSION, params: { path: "a.step" } }]);
    expect((await rpc(url, token, { method: "open_drawing", params: {} })).status).toBe(403);
    const drawings = bridge.tokenFor(SESSION, "drawings");
    expect(drawings).not.toBe(token);
    expect((await rpc(url, drawings, { method: "open_drawing", params: { title: "Plan" } })).body.ok).toBe(true);
    expect((await rpc(url, drawings, { method: "open_drawing", params: { path: "saved.excalidraw" } })).status).toBe(400);
    expect((await rpc(url, drawings, { method: "save_drawing", params: {} })).status).toBe(400);
    expect((await rpc(url, token, { method: "open_file", params: { path: 42 } })).status).toBe(400);
    bridge.revoke(SESSION.sessionId);
    expect((await rpc(url, drawings, { method: "open_drawing", params: {} })).status).toBe(401);
    expect((await rpc(url, token, { method: "not_a_tool" })).status).toBe(401);
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
    const sent: IntegrationCommand[] = [];
    let id = 0;
    const commands = new RendererCommands({ sessionRoot: () => ({ directory: "/proj", root: null }), send: (command) => sent.push(command), newId: () => `r${++id}` });
    const pending = commands.request({ sessionId: "s1", kind: "open-file", projectId: "p1", path: "a.step" });
    expect(sent).toEqual([{ sessionId: "s1", kind: "open-file", projectId: "p1", path: "a.step", requestId: "r1" }]);
    commands.reply({ requestId: "other", ok: true, result: 1 });
    commands.reply({ requestId: "r1", ok: true, result: { opened: "a.step" } });
    expect(await pending).toEqual({ opened: "a.step" });
  });

  it("rejects on a refusal and on a timeout", async () => {
    const commands = new RendererCommands({ sessionRoot: () => ({ directory: "/proj", root: null }), send: () => {}, newId: () => "r1", timeoutMs: 20 });
    const refused = commands.request({ sessionId: "s1", kind: "reveal", projectId: "p1", path: "x" });
    commands.reply({ requestId: "r1", ok: false, error: "no such tab" });
    await expect(refused).rejects.toThrow("no such tab");
    await expect(commands.request({ sessionId: "s1", kind: "list-tabs", projectId: "p1" })).rejects.toThrow("did not answer");
  });

  it("refuses at once, with no timer, when no window received the command", async () => {
    vi.useFakeTimers();
    try {
      const commands = new RendererCommands({ sessionRoot: () => ({ directory: "/proj", root: null }), send: () => 0, newId: () => "r1" });
      let refusal: string | undefined;
      commands.request({ sessionId: "s1", kind: "list-tabs", projectId: "p1" }).catch((error: Error) => {
        refusal = error.message;
      });
      // No clock advance: the refusal is immediate, not the 10 s timeout's.
      await vi.advanceTimersByTimeAsync(0);
      expect(refusal).toBe("no text-to-cad window is open; open one and retry");
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("names the timeout, says the command may still complete, and gives a save longer than a tab list", async () => {
    vi.useFakeTimers();
    try {
      const commands = new RendererCommands({ sessionRoot: () => ({ directory: "/proj", root: null }), send: () => {}, newId: () => "r1" });
      const list = commands.request({ sessionId: "s1", kind: "list-tabs", projectId: "p1" });
      const save = commands.request({ sessionId: "s1", kind: "document-save", projectId: "p1" });
      const listFailed = expect(list).rejects.toThrow(/within 10 s.*may still complete/);
      await vi.advanceTimersByTimeAsync(10_000);
      await listFailed;
      const outcome = await Promise.race([save.then(() => "answered", () => "rejected"), Promise.resolve("waiting")]);
      expect(outcome).toBe("waiting");
      const saveFailed = expect(save).rejects.toThrow(/within 30 s/);
      await vi.advanceTimersByTimeAsync(20_000);
      await saveFailed;
      await expect(save).rejects.toThrow(/did not answer within 30 s \(is one open\?\)/);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("RendererCommands and the viewer's own bound", () => {
  it("relays the viewer's 'did not finish' sentence when it answers at its ten seconds, not the relay's own timeout", async () => {
    vi.useFakeTimers();
    try {
      const commands = new RendererCommands({ sessionRoot: () => ({ directory: "/proj", root: null }), send: () => {}, newId: () => "r1" });
      const camera = commands.request({ sessionId: "s1", kind: "cad-camera", projectId: "p1" });
      const outcome = expect(camera).rejects.toThrow("The viewer did not finish applying this command.");
      await vi.advanceTimersByTimeAsync(10_000);
      commands.reply({ requestId: "r1", ok: false, error: "The viewer did not finish applying this command." });
      await outcome;
    } finally {
      vi.useRealTimers();
    }
  });

  // The viewer's own bound is ten seconds; the relay waits two more so its answer wins the race
  // (REPLY_TIMEOUT_MS / VIEWER_REPLY_TIMEOUT_MS in actions.ts). A kind left on the 10 s path would
  // time out the relay at the same instant as the viewer and report a window that DID answer as gone.
  it.each(["select-reference", "cad-clear-selection", "cad-camera", "cad-reset-camera", "cad-render-mode"] as const)(
    "gives %s twelve seconds: still waiting at 11.999, timed out at 12",
    async (kind) => {
      vi.useFakeTimers();
      try {
        const commands = new RendererCommands({ sessionRoot: () => ({ directory: "/proj", root: null }), send: () => {}, newId: () => "r1" });
        let settled: string | null = null;
        const pending = commands.request({ sessionId: "s1", kind, projectId: "p1" } as never);
        const outcome = expect(pending).rejects.toThrow(/did not answer within 12 s/);
        pending.then(() => { settled = "answered"; }, () => { settled = "rejected"; });
        await vi.advanceTimersByTimeAsync(11_999);
        expect(settled).toBeNull();
        await vi.advanceTimersByTimeAsync(1);
        await outcome;
        expect(settled).toBe("rejected");
      } finally {
        vi.useRealTimers();
      }
    },
  );
});

describe("the actions", () => {
  it("resolve paths against the session cwd, inside the project, and answer project-relative", async () => {
    const root = tempDir("text-to-cad-proj-");
    fs.mkdirSync(path.join(root, "STEP"));
    fs.writeFileSync(path.join(root, "STEP", "a.step"), "");
    const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: path.join(root, "STEP") };
    const deps = { sessionRoot: () => ({ directory: root, root: null }) };
    expect(await resolveForSession(deps, session, "a.step")).toMatchObject({ relative: "STEP/a.step", root: null });
    expect((await resolveForSession(deps, session, path.join(root, "STEP", "a.step"))).relative).toBe("STEP/a.step");
    await expect(resolveForSession(deps, session, "../../etc/passwd")).rejects.toThrow("outside the project");
    await expect(resolveForSession(deps, session, "missing.step")).rejects.toThrow("does not exist");
    await expect(resolveForSession({ sessionRoot: () => null }, session, "a.step")).rejects.toThrow("no longer open");
  });

  it("resolve a worktree session's paths against the worktree, and say which root", async () => {
    // The project and its worktree are siblings under a temp dir, the way
    // `~/.text-to-cad/worktrees/<project>/<slug>` is a sibling of nothing in the
    // checkout: a file in the worktree is outside the project directory and
    // must still open, and a file in the checkout must not resolve for a
    // session that cannot see it.
    const base = tempDir("text-to-cad-wt-");
    const project = path.join(base, "project");
    const worktree = path.join(base, "worktrees", "project", "model-the-wrist");
    fs.mkdirSync(path.join(project, "STEP"), { recursive: true });
    fs.mkdirSync(path.join(worktree, "STEP"), { recursive: true });
    fs.writeFileSync(path.join(project, "STEP", "old.step"), "");
    fs.writeFileSync(path.join(worktree, "STEP", "new.step"), "");
    const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: worktree };
    const deps = { sessionRoot: () => ({ directory: worktree, root: worktree }) };

    const resolved = await resolveForSession(deps, session, "STEP/new.step");
    expect(resolved.relative).toBe("STEP/new.step");
    expect(resolved.root).toBe(worktree);
    expect(resolved.absolute).toBe(fs.realpathSync(path.join(worktree, "STEP", "new.step")));
    await expect(resolveForSession(deps, session, path.join(project, "STEP", "old.step"))).rejects.toThrow("outside this session's worktree");

    // And the command the explorer gets names the worktree, so the tab opens there.
    const sent: IntegrationCommand[] = [];
    const commands = new RendererCommands({ ...deps, send: (command) => sent.push(command), newId: () => "r" });
    const actions = createActions({ ...deps, send: () => {}, newId: () => "r" }, commands);
    const opened = actions.open_file!(session, { path: "STEP/new.step" });
    while (sent.length < 1) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    commands.reply({ requestId: "r", ok: true, result: {} });
    await opened;
    expect(sent[0]).toMatchObject({ kind: "open-file", path: "STEP/new.step", root: worktree, projectId: "p" });
  });

  it("relay open_file and reveal with the resolved path, and answer attach_snapshot from disk", async () => {
    const root = tempDir("text-to-cad-proj-");
    fs.mkdirSync(path.join(root, "tmp"));
    fs.writeFileSync(path.join(root, "part.step"), "");
    fs.writeFileSync(path.join(root, "tmp", "review.png"), PNG_SIGNATURE);
    fs.writeFileSync(path.join(root, "notes.txt"), "text");
    const sent: IntegrationCommand[] = [];
    const sessionRoot = () => ({ directory: root, root: null });
    const commands = new RendererCommands({ sessionRoot, send: (command) => sent.push(command), newId: () => "r" });
    const actions = createActions({ sessionRoot, send: () => {}, newId: () => "r" }, commands);
    const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: root };

    // The action resolves the path before it asks the renderer, so the reply
    // has to wait for the command to have been sent.
    const sentCount = () => sent.length;
    const untilSent = async (count: number) => {
      while (sentCount() < count) {
        await new Promise((resolve) => setTimeout(resolve, 5));
      }
    };
    const opened = actions.open_file!(session, { path: "part.step" });
    await untilSent(1);
    commands.reply({ requestId: "r", ok: true, result: { opened: "part.step" } });
    expect(await opened).toEqual({ opened: "part.step" });
    expect(sent[0]).toMatchObject({ kind: "open-file", path: "part.step", root: null, projectId: "p" });

    await expect(actions.open_file!(session, { path: "tmp" })).rejects.toThrow("is a directory");

    const revealed = actions.reveal!(session, { path: "tmp" });
    await untilSent(2);
    commands.reply({ requestId: "r", ok: true, result: { revealed: "tmp" } });
    await revealed;
    expect(sent[1]).toMatchObject({ kind: "reveal", path: "tmp", directory: true });


    const snapshot = await actions.attach_snapshot!(session, { path: "tmp/review.png" });
    expect(snapshot).toEqual({ path: "tmp/review.png", mimeType: "image/png", base64: PNG_SIGNATURE.toString("base64") });
    await expect(actions.attach_snapshot!(session, { path: "notes.txt" })).rejects.toThrow("not a PNG");
  });

  it("refuses an attach_snapshot whose bytes are not the image its extension claims, or that is empty or over 5 MB", async () => {
    const root = tempDir("text-to-cad-proj-");
    const png = PNG_SIGNATURE;
    fs.writeFileSync(path.join(root, "page.png"), "<html><body>not an image</body></html>");
    fs.writeFileSync(path.join(root, "empty.png"), "");
    fs.writeFileSync(path.join(root, "big.png"), Buffer.concat([png, Buffer.alloc(6 * 1024 * 1024)]));
    // Under the raw 5 MiB but over 5 MB once base64'd, which is what the model measures.
    fs.writeFileSync(path.join(root, "encoded.png"), Buffer.concat([png, Buffer.alloc(4 * 1024 * 1024)]));
    fs.writeFileSync(path.join(root, "photo.jpg"), png);
    fs.writeFileSync(path.join(root, "ok.png"), png);
    const sessionRoot = () => ({ directory: root, root: null });
    const actions = createActions({ sessionRoot, send: () => {}, newId: () => "r" }, new RendererCommands({ sessionRoot, send: () => {}, newId: () => "r" }));
    const session: BridgeSession = { sessionId: "s", projectId: "p", cwd: root };
    await expect(actions.attach_snapshot!(session, { path: "page.png" })).rejects.toThrow(/not a PNG/);
    await expect(actions.attach_snapshot!(session, { path: "empty.png" })).rejects.toThrow(/empty/);
    await expect(actions.attach_snapshot!(session, { path: "big.png" })).rejects.toThrow(/5 MB/);
    await expect(actions.attach_snapshot!(session, { path: "encoded.png" })).rejects.toThrow(/5 MB/);
    await expect(actions.attach_snapshot!(session, { path: "photo.jpg" })).rejects.toThrow(/not a JPEG/);
    await expect(actions.attach_snapshot!(session, { path: "ok.png" })).resolves.toMatchObject({ mimeType: "image/png", base64: png.toString("base64") });
  });

  describe("attach_snapshot re-checks the handle against a fresh realpath", () => {
    const png = PNG_SIGNATURE;
    function actionsFor(root: string) {
      const sessionRoot = () => ({ directory: root, root: null });
      const commands = new RendererCommands({ sessionRoot, send: () => {}, newId: () => "r" });
      return createActions({ sessionRoot, send: () => {}, newId: () => "r" }, commands);
    }

    it("refuses a file that grew past what the stat said while it was read", async () => {
      const root = fs.realpathSync(tempDir("text-to-cad-proj-"));
      fs.writeFileSync(path.join(root, "a.png"), Buffer.concat([png, Buffer.alloc(100)]));
      const realOpen = fsp.open.bind(fsp);
      const spy = vi.spyOn(fsp, "open").mockImplementation((async (...args: Parameters<typeof fsp.open>) => {
        const real = await realOpen(...args);
        // A stat from before the writer appended: the read then finds more than the stat promised.
        const stat = async () => Object.assign(Object.create(await real.stat()) as object, { size: png.length }) as Awaited<ReturnType<typeof real.stat>>;
        return { stat, read: (...a: unknown[]) => (real.read as (...x: unknown[]) => unknown)(...a), close: () => real.close() };
      }) as unknown as typeof fsp.open);
      try {
        await expect(actionsFor(root).attach_snapshot!({ sessionId: "s", projectId: "p", cwd: root }, { path: "a.png" })).rejects.toThrow(/changed while/);
      } finally {
        spy.mockRestore();
      }
    });

    it("accepts a folder whose name only starts with dots", async () => {
      const root = fs.realpathSync(tempDir("text-to-cad-proj-"));
      fs.mkdirSync(path.join(root, "..keep"));
      fs.writeFileSync(path.join(root, "..keep", "a.png"), png);
      const snapshot = await actionsFor(root).attach_snapshot!({ sessionId: "s", projectId: "p", cwd: root }, { path: "..keep/a.png" });
      expect(snapshot).toMatchObject({ path: "..keep/a.png", base64: png.toString("base64") });
    });

    it.skipIf(process.platform === "win32")("refuses a path swapped for a link out of the root after the check", async () => {
      const root = fs.realpathSync(tempDir("text-to-cad-proj-"));
      const outside = fs.realpathSync(tempDir("text-to-cad-out-"));
      fs.writeFileSync(path.join(root, "a.png"), png);
      // A hard link, so the handle's device and inode still match the outside
      // path: only the containment half of the re-check can refuse this.
      fs.linkSync(path.join(root, "a.png"), path.join(outside, "a.png"));
      const realOpen = fsp.open.bind(fsp);
      const spy = vi.spyOn(fsp, "open").mockImplementation(async (...args: Parameters<typeof fsp.open>) => {
        fs.rmSync(path.join(root, "a.png"));
        fs.symlinkSync(path.join(outside, "a.png"), path.join(root, "a.png"));
        return realOpen(...args);
      });
      try {
        await expect(actionsFor(root).attach_snapshot!({ sessionId: "s", projectId: "p", cwd: root }, { path: "a.png" }))
          .rejects.toThrow("changed while it was being read");
      } finally {
        spy.mockRestore();
      }
    });
  });

  it.skipIf(process.platform === "win32")("names the session's recorded spelling of its directory beside the real path", async () => {
    const real = fs.realpathSync(tempDir("text-to-cad-proj-"));
    const link = path.join(tempDir("text-to-cad-link-"), "checkout");
    fs.symlinkSync(real, link);
    const sent: IntegrationCommand[] = [];
    const sessionRoot = () => ({ directory: link, root: null });
    const commands = new RendererCommands({ sessionRoot, send: (command) => sent.push(command), newId: () => "r" });
    const actions = createActions({ sessionRoot, send: () => {}, newId: () => "r" }, commands);
    const listed = actions.list_open_tabs!({ sessionId: "s", projectId: "p", cwd: link }, {});
    await vi.waitFor(() => expect(sent).toHaveLength(1));
    commands.reply({ requestId: "r", ok: true, result: { tabs: [] } });
    await listed;
    expect(sent[0]).toMatchObject({ kind: "list-tabs", rootDirectory: real, rootAliases: [link] });
  });

  it.skipIf(process.platform === "win32")("refuses a snapshot swapped for a link out of the workspace after its path was checked", async () => {
    const root = tempDir("text-to-cad-proj-");
    const outside = path.join(tempDir("text-to-cad-secret-"), "id_rsa");
    fs.writeFileSync(outside, "PRIVATE KEY");
    fs.writeFileSync(path.join(root, "x.png"), PNG_SIGNATURE);
    const sessionRoot = () => ({ directory: root, root: null });
    const actions = createActions({ sessionRoot, send: () => {}, newId: () => "r" }, new RendererCommands({ sessionRoot, send: () => {}, newId: () => "r" }));
    // The swap lands after the path was resolved and before the file is opened.
    const access = fsp.access.bind(fsp);
    vi.spyOn(fsp, "access").mockImplementationOnce(async (target, mode) => {
      await access(target, mode);
      fs.rmSync(path.join(root, "x.png"));
      fs.symlinkSync(outside, path.join(root, "x.png"));
    });
    await expect(actions.attach_snapshot!({ sessionId: "s", projectId: "p", cwd: root }, { path: "x.png" })).rejects.toThrow(/changed while it was being read/);
  });

  it("attaches a snapshot in a top-level folder whose name starts with two dots", async () => {
    const root = tempDir("text-to-cad-proj-");
    fs.mkdirSync(path.join(root, "..shots"));
    fs.writeFileSync(path.join(root, "..shots", "x.png"), PNG_SIGNATURE);
    const sessionRoot = () => ({ directory: root, root: null });
    const actions = createActions({ sessionRoot, send: () => {}, newId: () => "r" }, new RendererCommands({ sessionRoot, send: () => {}, newId: () => "r" }));
    await expect(actions.attach_snapshot!({ sessionId: "s", projectId: "p", cwd: root }, { path: "..shots/x.png" })).resolves.toMatchObject({ mimeType: "image/png" });
  });

  it.skipIf(process.platform === "win32")("refuses a snapshot that is a FIFO rather than blocking on it", { timeout: 2000 }, async () => {
    const root = tempDir("text-to-cad-proj-");
    const fifo = path.join(root, "stuck.png");
    execFileSync("mkfifo", [fifo]);
    const sessionRoot = () => ({ directory: root, root: null });
    const actions = createActions({ sessionRoot, send: () => {}, newId: () => "r" }, new RendererCommands({ sessionRoot, send: () => {}, newId: () => "r" }));
    try {
      await expect(actions.attach_snapshot!({ sessionId: "s", projectId: "p", cwd: root }, { path: "stuck.png" })).rejects.toThrow(/not a file/);
    } finally {
      // Release a reader that did block, so the pool thread it holds comes back.
      try {
        fs.closeSync(fs.openSync(fifo, fs.constants.O_WRONLY | fs.constants.O_NONBLOCK));
      } catch {
        // No reader waiting: the fix held.
      }
    }
  });
});
