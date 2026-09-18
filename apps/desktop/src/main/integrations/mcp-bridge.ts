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

/** App handlers share authenticated identity; each MCP gets its own allowed method set. */
export type BridgeActions = Record<string, (session: BridgeSession, params: Record<string, unknown>, signal?: AbortSignal) => Promise<unknown>>;
export type BridgeMethod = string;
import { integrations, integrationById, toolByName } from "./registry.mjs";
export const BRIDGE_METHODS: readonly string[] = integrations.flatMap(entry => [...entry.tools, ...(entry.hostTools ?? [])].map(tool => tool.name));

/** The environment the MCP server reads. One place, shared with server.mjs by name. */
export const BRIDGE_ENV = {
  url: "HARDCORE_BRIDGE_URL",
  token: "HARDCORE_BRIDGE_TOKEN",
  cwd: "HARDCORE_CWD",
  session: "HARDCORE_SESSION_ID",
} as const;

const MAX_BODY_BYTES = 3 * 1024 * 1024;

export class McpBridge {
  private server: http.Server | null = null;
  private url: string | null = null;
  private readonly tokens = new Map<string, { token: string; session: BridgeSession }>();
  private readonly inFlight = new Map<AbortController, BridgeSession>();
  private readonly byToken = new Map<string, { session: BridgeSession; integration: string }>();

  constructor(
    private readonly actions: BridgeActions,
    private readonly serverScript: () => { command: string; args: string[]; env: Record<string, string> },
    private readonly resources?: { revoke(sessionId: string): void; dispose(): Promise<void> },
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
    for (const controller of this.inFlight.keys()) controller.abort(new Error("Hardcore is shutting down"));
    this.tokens.clear();
    this.byToken.clear();
    await this.resources?.dispose();
    if (server) {
      await new Promise<void>((resolve) => { server.close(() => resolve()); server.closeAllConnections(); });
    }
  }

  /** The token for a session, minted once. */
  tokenFor(session: BridgeSession, integration = "workspace"): string {
    integrationById(integration);
    const key = `${session.sessionId}:${integration}`;
    const existing = this.tokens.get(key);
    if (existing) {
      // The cwd or project can change across a resume; the token does not.
      if (existing.session.cwd !== session.cwd || existing.session.projectId !== session.projectId) {
        this.resources?.revoke(session.sessionId);
        for (const [controller, active] of this.inFlight) if (active.sessionId === session.sessionId) controller.abort(new Error("Session workspace changed"));
      }
      existing.session = session;
      this.byToken.set(existing.token, { session, integration });
      return existing.token;
    }
    const token = randomBytes(24).toString("base64url");
    this.tokens.set(key, { token, session });
    this.byToken.set(token, { session, integration });
    return token;
  }

  revokeProject(projectId: string): void {
    for (const entry of [...this.tokens.values()]) if (entry.session.projectId === projectId) this.revoke(entry.session.sessionId);
  }

  revoke(sessionId: string): void {
    this.resources?.revoke(sessionId);
    for (const [controller, session] of this.inFlight) if (session.sessionId === sessionId) controller.abort(new Error("Session authorization revoked"));
    for (const [key, entry] of this.tokens) {
      if (entry.session.sessionId === sessionId) { this.tokens.delete(key); this.byToken.delete(entry.token); }
    }
  }

  /** The ACP `McpServer` entry for a session — what `session/new` carries. */
  serverFor(session: BridgeSession, integration = "workspace"): McpServer {
    integrationById(integration);
    if (!this.url) {
      throw new Error("the MCP bridge is not listening");
    }
    const script = this.serverScript();
    const env = {
      ...script.env,
      [BRIDGE_ENV.url]: this.url,
      [BRIDGE_ENV.token]: this.tokenFor(session, integration),
      HARDCORE_INTEGRATION: integration,
      [BRIDGE_ENV.cwd]: session.cwd,
      [BRIDGE_ENV.session]: session.sessionId,
    };
    // No `type` field on purpose: claude-agent-acp treats any entry that
    // carries one as http/sse and drops it unless the type matches, and
    // reads an entry without one as stdio. Codex-acp accepts either.
    return {
      name: `hardcore-${integration}`,
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
    const authorization = token ? this.byToken.get(token) : undefined;
    if (!authorization) {
      send(401, { ok: false, error: "unknown session token" });
      request.resume();
      return;
    }
    const { session, integration } = authorization;
    const chunks: Buffer[] = [];
    let size = 0;
    try {
      for await (const chunk of request) {
        const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        size += bytes.length;
        if (size > MAX_BODY_BYTES) { send(413, { ok: false, error: "request too large" }); return; }
        chunks.push(bytes);
      }
    } catch { if (!response.destroyed) send(400, { ok: false, error: "request interrupted" }); return; }
    let parsed: { method?: unknown; params?: unknown };
    try {
      const value: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("expected an object");
      parsed = value;
    } catch { send(400, { ok: false, error: "malformed JSON object" }); return; }
    // Revocation can happen while a client is still sending its body.
    if (this.byToken.get(token) !== authorization) { send(401, { ok: false, error: "session authorization changed" }); return; }
    const method = parsed.method;
    if (typeof method !== "string" || !(BRIDGE_METHODS as readonly string[]).includes(method)) {
      send(400, { ok: false, error: `unknown method ${String(method)}` });
      return;
    }
    const definition = toolByName(method);
    if (!definition || definition.integration.id !== integration) {
      send(403, { ok: false, error: "method is outside this integration" }); return;
    }
    const validated = definition.tool.inputSchema.safeParse(parsed.params ?? {});
    if (!validated.success) { send(400, { ok: false, error: validated.error.message }); return; }
    const controller = new AbortController();
    this.inFlight.set(controller, session);
    const disconnected = () => { if (!response.writableEnded) controller.abort(new Error("tool request cancelled")); };
    response.once("close", disconnected);
    try {
      const handler = this.actions[method];
      if (!handler) throw new Error(`Integration method is unavailable: ${method}`);
      const result = await handler(session, validated.data, controller.signal);
      controller.signal.throwIfAborted();
      if (!response.destroyed) send(200, { ok: true, result });
    } catch (error) {
      if (!response.destroyed) send(200, { ok: false, error: error instanceof Error ? error.message : String(error) });
    } finally { this.inFlight.delete(controller); response.off("close", disconnected); }

  }
}
