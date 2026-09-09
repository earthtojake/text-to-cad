/**
 * The bridge between the Hardcore MCP server and main (plan §8).
 *
 * Every session gets a stdio MCP server (`resources/hardcore-mcp/server.mjs`)
 * that the *agent* spawns — so it runs in the agent's process tree, not ours,
 * and has no handle on Electron. What it has is an environment: the URL of
 * this bridge, a token that names one session, and that session's cwd. Each
 * tool call becomes one `POST /rpc` here, and main turns it into an explorer
 * action through `BridgeActions`.
 *
 * Local only: the listener is 127.0.0.1 on an OS-assigned port, and a request
 * without a live session's token is refused before its body is read. A token
 * is minted per session (`tokenFor`) and forgotten when the session is
 * deleted, so a server left running by a dead agent cannot act on a later one.
 */
import { randomBytes } from "node:crypto";
import http from "node:http";
import type { AddressInfo } from "node:net";

import type { McpServer } from "@agentclientprotocol/sdk";

export type BridgeSession = { sessionId: string; projectId: string; cwd: string };

/** What the MCP server asks for, by method name (the tool names, verbatim). */
export type BridgeActions = {
  open_file: (session: BridgeSession, params: { path: string }) => Promise<unknown>;
  reveal: (session: BridgeSession, params: { path: string }) => Promise<unknown>;
  open_url: (session: BridgeSession, params: { url: string }) => Promise<unknown>;
  list_open_tabs: (session: BridgeSession, params: Record<string, never>) => Promise<unknown>;
  viewer_state: (session: BridgeSession, params: Record<string, never>) => Promise<unknown>;
  attach_snapshot: (
    session: BridgeSession,
    params: { path: string },
  ) => Promise<{ path: string; mimeType: string; base64: string }>;
};

export type BridgeMethod = keyof BridgeActions;

export const BRIDGE_METHODS: readonly BridgeMethod[] = [
  "open_file",
  "reveal",
  "open_url",
  "list_open_tabs",
  "viewer_state",
  "attach_snapshot",
];

/** The environment the MCP server reads. One place, shared with server.mjs by name. */
export const BRIDGE_ENV = {
  url: "HARDCORE_BRIDGE_URL",
  token: "HARDCORE_BRIDGE_TOKEN",
  cwd: "HARDCORE_CWD",
  session: "HARDCORE_SESSION_ID",
} as const;

const MAX_BODY_BYTES = 64 * 1024;

export class McpBridge {
  private server: http.Server | null = null;
  private url: string | null = null;
  private readonly tokens = new Map<string, { token: string; session: BridgeSession }>();
  private readonly byToken = new Map<string, BridgeSession>();

  constructor(
    private readonly actions: BridgeActions,
    private readonly serverScript: () => { command: string; args: string[]; env: Record<string, string> },
  ) {}

  /** Listen. Idempotent. */
  async start(): Promise<string> {
    if (this.url) {
      return this.url;
    }
    const server = http.createServer((request, response) => void this.handle(request, response));
    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", () => {
        server.off("error", reject);
        resolve();
      });
    });
    const { port } = server.address() as AddressInfo;
    this.server = server;
    this.url = `http://127.0.0.1:${port}`;
    return this.url;
  }

  address(): string | null {
    return this.url;
  }

  async stop(): Promise<void> {
    const server = this.server;
    this.server = null;
    this.url = null;
    if (server) {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  }

  /** The token for a session, minted once. */
  tokenFor(session: BridgeSession): string {
    const existing = this.tokens.get(session.sessionId);
    if (existing) {
      // The cwd or project can change across a resume; the token does not.
      existing.session = session;
      this.byToken.set(existing.token, session);
      return existing.token;
    }
    const token = randomBytes(24).toString("base64url");
    this.tokens.set(session.sessionId, { token, session });
    this.byToken.set(token, session);
    return token;
  }

  revoke(sessionId: string): void {
    const entry = this.tokens.get(sessionId);
    if (entry) {
      this.tokens.delete(sessionId);
      this.byToken.delete(entry.token);
    }
  }

  /** The ACP `McpServer` entry for a session — what `session/new` carries. */
  serverFor(session: BridgeSession): McpServer {
    if (!this.url) {
      throw new Error("the MCP bridge is not listening");
    }
    const script = this.serverScript();
    const env = {
      ...script.env,
      [BRIDGE_ENV.url]: this.url,
      [BRIDGE_ENV.token]: this.tokenFor(session),
      [BRIDGE_ENV.cwd]: session.cwd,
      [BRIDGE_ENV.session]: session.sessionId,
    };
    // No `type` field on purpose: claude-agent-acp treats any entry that
    // carries one as http/sse and drops it unless the type matches, and
    // reads an entry without one as stdio. Codex-acp accepts either.
    return {
      name: "hardcore",
      command: script.command,
      args: script.args,
      env: Object.entries(env).map(([name, value]) => ({ name, value })),
    };
  }

  private async handle(request: http.IncomingMessage, response: http.ServerResponse) {
    const send = (status: number, body: unknown) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    };
    if (request.method !== "POST" || request.url !== "/rpc") {
      send(404, { ok: false, error: "not found" });
      return;
    }
    const auth = request.headers.authorization ?? "";
    const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
    const session = token ? this.byToken.get(token) : undefined;
    if (!session) {
      send(401, { ok: false, error: "unknown session token" });
      request.resume();
      return;
    }
    let raw = "";
    let overflow = false;
    for await (const chunk of request) {
      raw += chunk;
      if (raw.length > MAX_BODY_BYTES) {
        overflow = true;
        break;
      }
    }
    if (overflow) {
      send(413, { ok: false, error: "request too large" });
      return;
    }
    let parsed: { method?: unknown; params?: unknown };
    try {
      parsed = JSON.parse(raw || "{}") as typeof parsed;
    } catch {
      send(400, { ok: false, error: "malformed JSON" });
      return;
    }
    const method = parsed.method;
    if (typeof method !== "string" || !(BRIDGE_METHODS as readonly string[]).includes(method)) {
      send(400, { ok: false, error: `unknown method ${String(method)}` });
      return;
    }
    const params = (parsed.params && typeof parsed.params === "object" ? parsed.params : {}) as never;
    try {
      const result = await this.actions[method as BridgeMethod](session, params);
      send(200, { ok: true, result });
    } catch (error) {
      send(200, { ok: false, error: error instanceof Error ? error.message : String(error) });
    }
  }
}
