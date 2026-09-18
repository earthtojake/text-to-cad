import { randomBytes, randomUUID } from "node:crypto";
import http from "node:http";
import type { AddressInfo } from "node:net";
import type { WebContents } from "electron";
import { WebSocket, WebSocketServer } from "ws";
import { type BrowserService, browserScopeKey, browserURL, type BrowserScope } from "./service";

type Params = Record<string, unknown>;
type Message = { id: number; method: string; params?: Params; sessionId?: string };
type PageSession = { tabId: string; contents: WebContents; nativeSession: string; root: boolean };
export interface BrowserTabLifecycle {
  open(url: string, signal: AbortSignal): Promise<string>;
  show(tabId: string, signal: AbortSignal): Promise<unknown>;
  close(tabId: string, signal: AbortSignal): Promise<unknown>;
}

/** A virtual CDP browser containing only one authorized workspace's native views.
 * Never enables Electron's process-wide debug port. Browser/Target commands are
 * implemented here; page-domain commands use only an owned WebContents debugger.
 */
export class ScopedBrowserCdp {
  private readonly server = http.createServer((_request, response) => { response.writeHead(404); response.end(); });
  private readonly sockets = new WebSocketServer({ noServer: true, maxPayload: 16 * 1024 * 1024 });
  private readonly secret = randomBytes(32).toString("base64url");
  private endpoint: string | null = null;
  private readonly lifetime = new AbortController();
  constructor(private readonly service: BrowserService, private readonly scope: BrowserScope, private readonly tabs: BrowserTabLifecycle) {
    this.server.on("upgrade", (request, socket, head) => {
      if (request.url !== `/${this.secret}` || request.headers.origin) { socket.destroy(); return; }
      this.sockets.handleUpgrade(request, socket, head, ws => this.connect(ws));
    });
  }
  async start() {
    this.lifetime.signal.throwIfAborted();
    if (this.endpoint) return this.endpoint;
    await new Promise<void>((resolve, reject) => { this.server.once("error", reject); this.server.listen(0, "127.0.0.1", resolve); });
    this.endpoint = `ws://127.0.0.1:${(this.server.address() as AddressInfo).port}/${this.secret}`;
    return this.endpoint;
  }
  async dispose() {
    if (this.lifetime.signal.aborted) return;
    this.lifetime.abort(new Error("Browser session authorization ended."));
    for (const socket of this.sockets.clients) socket.terminate();
    this.sockets.close();
    await new Promise<void>(resolve => this.server.close(() => resolve()));
    this.endpoint = null;
  }
  private connect(socket: WebSocket) {
    const sessions = new Map<string, PageSession>();
    const streams = new Map<string, { bytes: Buffer; offset: number }>();
    const cleanups = new Map<string, () => void>();
    let autoAttach = false, discover = false;
    const send = (value: unknown) => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(value)); };
    const event = (method: string, params: unknown, sessionId?: string) => send({ method, params, ...(sessionId ? { sessionId } : {}) });
    const targetIds = new Map<string, string>();
    const info = async (tabId: string) => {
      const target = this.service.metadata(this.scope, tabId);
      const contents = this.service.contents(this.scope, tabId);
      if (!contents.debugger.isAttached()) contents.debugger.attach("1.3");
      const { targetInfo } = await contents.debugger.sendCommand("Target.getTargetInfo");
      targetIds.set(targetInfo.targetId, tabId);
      return { targetId: targetInfo.targetId, browserContextId: "hardcore-workspace", type: "page", title: target.title, url: target.url || "about:blank", attached: true, canAccessOpener: false };
    };
    const attaching = new Map<string, Promise<string>>();
    const attachPage = async (tabId: string) => {
      const targetInfo = await info(tabId);
      if (socket.readyState !== WebSocket.OPEN) throw new Error("Browser connection closed");
      const existing = [...sessions].find(([, page]) => page.tabId === tabId && page.root);
      if (existing) return existing[0];
      const contents = this.service.contents(this.scope, tabId);
      if (!contents.debugger.isAttached()) contents.debugger.attach("1.3");
      const { sessionId: nativeSession } = await contents.debugger.sendCommand("Target.attachToTarget", { targetId: targetInfo.targetId, flatten: true });
      if (socket.readyState !== WebSocket.OPEN) {
        await contents.debugger.sendCommand("Target.detachFromTarget", { sessionId: nativeSession });
        throw new Error("Browser connection closed");
      }
      const sessionId = randomUUID();
      sessions.set(sessionId, { contents, tabId, nativeSession, root: true });
      const onMessage = (_event: Electron.Event, method: string, params: Params, nativeSession?: string) => {
        let destination: string;
        if (nativeSession) {
          const child = [...sessions].find(([, page]) => page.contents === contents && page.nativeSession === nativeSession);
          if (!child) return;
          destination = child[0];
        } else return;
        if (method === "Target.attachedToTarget") {
          const childId = randomUUID();
          sessions.set(childId, { contents, tabId, nativeSession: String(params.sessionId), root: false });
          event(method, { ...params, sessionId: childId }, destination);
        } else if (method === "Target.detachedFromTarget") {
          const child = [...sessions].find(([, page]) => page.contents === contents && page.nativeSession === params.sessionId);
          if (child) { sessions.delete(child[0]); event(method, { ...params, sessionId: child[0] }, destination); }
        } else event(method, params, destination);
      };
      const protocol = contents.debugger;
      protocol.on("message", onMessage);
      cleanups.set(sessionId, () => {
        protocol.off("message", onMessage);
        if (!contents.isDestroyed() && contents.debugger.isAttached())
          void contents.debugger.sendCommand("Target.detachFromTarget", { sessionId: nativeSession }).catch(() => {});
      });
      event("Target.attachedToTarget", { sessionId, targetInfo, waitingForDebugger: false });
      return sessionId;
    };
    const attach = (tabId: string) => {
      let pending = attaching.get(tabId);
      if (!pending) {
        pending = attachPage(tabId);
        attaching.set(tabId, pending);
        void pending.finally(() => { attaching.delete(tabId); }).catch(() => {});
      }
      return pending;
    };
    const onOpened = async (target: BrowserScope & { tabId: string }) => {
      if (browserScopeKey(target) !== browserScopeKey(this.scope)) return;
      if (discover) event("Target.targetCreated", { targetInfo: await info(target.tabId) });
      if (autoAttach) await attach(target.tabId);
    };
    const opened = (target: BrowserScope & { tabId: string }) => { void onOpened(target).catch(() => {}); };
    const closed = (target: BrowserScope & { tabId: string }) => {
      if (browserScopeKey(target) !== browserScopeKey(this.scope)) return;
      for (const [id, page] of sessions) if (page.tabId === target.tabId) {
        cleanups.get(id)?.(); cleanups.delete(id); sessions.delete(id);
        event("Target.detachedFromTarget", { sessionId: id, targetId: [...targetIds].find(([, id]) => id === target.tabId)?.[0] });
      }
      event("Target.targetDestroyed", { targetId: [...targetIds].find(([, id]) => id === target.tabId)?.[0] });
    };
    this.service.events.on("opened", opened);
    this.service.events.on("closed", closed);
    socket.once("close", () => {
      this.service.events.off("opened", opened); this.service.events.off("closed", closed);
      for (const cleanup of cleanups.values()) cleanup();
      cleanups.clear(); sessions.clear(); streams.clear();
    });
    const dispatch = async ({ method, params = {}, sessionId }: Message): Promise<unknown> => {
      this.lifetime.signal.throwIfAborted();
      const page = sessionId ? sessions.get(sessionId) : undefined;
      if (sessionId && !page) throw new Error("Unknown browser session");
      if (page) this.service.contents(this.scope, page.tabId); // Recheck ownership and lifetime.
      const targetId = () => {
        const id = params.targetId ? targetIds.get(String(params.targetId)) : page?.tabId;
        if (!id) throw new Error("Unknown browser target");
        this.service.contents(this.scope, id);
        return id;
      };
      if ((method === "IO.read" || method === "IO.close") && streams.has(String(params.handle))) {
        const stream = streams.get(String(params.handle))!;
        if (method === "IO.close") { streams.delete(String(params.handle)); return {}; }
        const offset = params.offset === undefined ? stream.offset : Number(params.offset);
        const size = Math.min(Number(params.size ?? 64 * 1024), 1024 * 1024);
        if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(size) || size < 1) throw new Error("Invalid PDF stream range");
        const data = stream.bytes.subarray(offset, offset + size);
        stream.offset = offset + data.length;
        return { data: data.toString("base64"), base64Encoded: true, eof: stream.offset >= stream.bytes.length };
      }
      switch (method) {
        case "Page.printToPDF": {
          if (!page || !page.root) throw new Error("PDF capture needs a top-level page");
          // Electron exposes printing through WebContents, not its CDP Page domain.
          const bytes = await page.contents.printToPDF({
            landscape: Boolean(params.landscape), displayHeaderFooter: Boolean(params.displayHeaderFooter),
            printBackground: Boolean(params.printBackground), scale: Number(params.scale ?? 1),
            pageSize: { width: Number(params.paperWidth ?? 8.5), height: Number(params.paperHeight ?? 11) },
            margins: { top: Number(params.marginTop ?? 0.4), bottom: Number(params.marginBottom ?? 0.4),
              left: Number(params.marginLeft ?? 0.4), right: Number(params.marginRight ?? 0.4) },
            pageRanges: String(params.pageRanges ?? ""), headerTemplate: String(params.headerTemplate ?? ""),
            footerTemplate: String(params.footerTemplate ?? ""), preferCSSPageSize: Boolean(params.preferCSSPageSize),
            generateTaggedPDF: Boolean(params.generateTaggedPDF), generateDocumentOutline: Boolean(params.generateDocumentOutline),
          });
          this.lifetime.signal.throwIfAborted();
          if (socket.readyState !== WebSocket.OPEN) throw new Error("Browser connection closed");
          if (bytes.length > 64 * 1024 * 1024 || streams.size >= 4) throw new Error("PDF capture exceeds the connection's memory limit");
          if (params.transferMode !== "ReturnAsStream") return { data: bytes.toString("base64") };
          const stream = `hardcore-pdf-${randomUUID()}`;
          streams.set(stream, { bytes, offset: 0 }); return { data: "", stream };
        }
        case "Browser.getVersion": return { protocolVersion: "1.3", product: `Chrome/${process.versions.chrome}`, revision: "", userAgent: `Mozilla/5.0 (${process.platform === "darwin" ? "Macintosh" : process.platform === "win32" ? "Windows" : "Linux"}) Chrome/${process.versions.chrome}`, jsVersion: process.versions.v8 };
        case "Target.getBrowserContexts": return { browserContextIds: [] };
        case "Target.getTargets": return { targetInfos: await Promise.all(this.service.list(this.scope).map(t => info(t.tabId))) };
        case "Target.getTargetInfo": return { targetInfo: !page && !params.targetId
          ? { targetId: "hardcore-browser", type: "browser", title: "Hardcore", url: "", attached: true, browserContextId: "hardcore-workspace" }
          : await info(targetId()) };
        case "Target.setDiscoverTargets":
          discover = Boolean(params.discover);
          if (discover) for (const tab of this.service.list(this.scope)) event("Target.targetCreated", { targetInfo: await info(tab.tabId) });
          return {};
        case "Target.setAutoAttach":
          if (page) return page.contents.debugger.sendCommand(method, params, page.nativeSession);
          autoAttach = Boolean(params.autoAttach);
          if (autoAttach) for (const tab of this.service.list(this.scope)) await attach(tab.tabId);
          return {};
        case "Target.attachToTarget": return { sessionId: await attach(targetId()) };
        case "Target.createTarget": {
          const id = await this.tabs.open(browserURL(String(params.url ?? "about:blank")), this.lifetime.signal);
          if (autoAttach) await attach(id);
          return { targetId: (await info(id)).targetId };
        }
        case "Page.bringToFront":
          if (!page) throw new Error("Unknown browser session");
          await this.tabs.show(page.tabId, this.lifetime.signal);
          return page.contents.debugger.sendCommand(method, params, page.nativeSession);
        case "Target.activateTarget": await this.tabs.show(targetId(), this.lifetime.signal); return {};
        case "Target.closeTarget": await this.tabs.close(targetId(), this.lifetime.signal); return { success: true };
        case "Target.detachFromTarget": {
          const id = String(params.sessionId); const owned = sessions.get(id);
          if (!owned) throw new Error("Unknown browser session");
          cleanups.get(id)?.(); cleanups.delete(id); sessions.delete(id); return {};
        }
        case "Browser.setDownloadBehavior": throw new Error("Download policy belongs to Hardcore's browser host.");
        case "Browser.getWindowForTarget": targetId(); return { windowId: 1, bounds: { left: 0, top: 0, width: 1000, height: 700, windowState: "normal" } };
        case "Browser.setWindowBounds": throw new Error("Hardcore owns the browser pane size; resize it in the app.");
        default:
          if (!page || /^(Browser|Target|Storage)\./.test(method)) throw new Error(`Unsupported scoped browser command: ${method}`);
          if (method === "Page.navigate") browserURL(String(params.url));
          return page.contents.debugger.sendCommand(method, params, page.nativeSession);
      }
    };
    socket.on("message", bytes => {
      let message: Message;
      try { message = JSON.parse(bytes.toString()); if (!Number.isInteger(message.id) || typeof message.method !== "string") throw new Error(); }
      catch { socket.close(1003, "Invalid CDP message"); return; }
      void dispatch(message).then(result => send({ id: message.id, result, ...(message.sessionId ? { sessionId: message.sessionId } : {}) }),
        error => send({ id: message.id, error: { code: -32000, message: error instanceof Error ? error.message : String(error) },
          ...(message.sessionId ? { sessionId: message.sessionId } : {}) }));
    });
  }
}
