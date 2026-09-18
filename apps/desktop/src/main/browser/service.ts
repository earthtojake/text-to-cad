import { createHash, randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { type BrowserWindow, WebContentsView } from "electron";
import { browserMethodSchemas, type BrowserInput, type BrowserMethod, type BrowserTarget } from "../../shared/browser";
import { browserHarness } from "./harness";

export type BrowserScope = { projectId: string; root: string };
type Target = {
  scope: BrowserScope; id: string; view: WebContentsView; harness: ReturnType<typeof browserHarness>;
  owner?: BrowserWindow; lease?: string; generation: number; visible: boolean; ready: Promise<void>; logs: BrowserTarget["logs"];
};
export type BrowserBounds = { x: number; y: number; width: number; height: number };
export function browserScopeKey(scope: BrowserScope) { return JSON.stringify([scope.projectId, scope.root]); }
export function browserURL(value: string) {
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:" && value !== "about:blank") {
    throw new Error("Browser pages must use an HTTP or HTTPS URL.");
  }
  return url.href;
}

/** Owns live pages independently of whichever project or tab is painted. */
export class BrowserService {
  readonly events = new EventEmitter();
  private targets = new Map<string, Target>();
  private get(scope: BrowserScope, id: string) {
    const target = this.targets.get(id);
    if (!target || browserScopeKey(target.scope) !== browserScopeKey(scope) || target.view.webContents.isDestroyed()) {
      throw new Error("This browser tab is not available in this session's workspace.");
    }
    return target;
  }
  private info(target: Target): BrowserTarget {
    const wc = target.view.webContents;
    return { tabId: target.id, ...target.scope, url: wc.getURL(), generation: target.generation, title: wc.getTitle(), loading: wc.isLoading(),
      canGoBack: wc.navigationHistory.canGoBack(), canGoForward: wc.navigationHistory.canGoForward(),
      visible: target.visible, logs: [...target.logs] };
  }
  list(scope: BrowserScope) {
    return [...this.targets.values()].filter(t => browserScopeKey(t.scope) === browserScopeKey(scope)).map(t => this.info(t));
  }
  contents(scope: BrowserScope, id: string) { return this.get(scope, id).view.webContents; }
  async open(scope: BrowserScope, params: { tabId?: string; url?: string | null }) {
    const id = params.tabId ?? randomUUID();
    const existing = this.targets.get(id);
    if (existing) { const target = this.get(scope, id); await target.ready; return this.info(this.get(scope, id)); }
    const url = browserURL(params.url || "about:blank");
    const partition = `persist:browser-${createHash("sha256").update(browserScopeKey(scope)).digest("hex")}`;
    const view = new WebContentsView({ webPreferences: {
      partition, nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, backgroundThrottling: false, spellcheck: false,
    } });
    view.setBounds({ x: 0, y: 0, width: 1000, height: 700 });
    const target: Target = { id, scope: { ...scope }, view, harness: browserHarness(view.webContents), generation: 0, visible: false, ready: Promise.resolve(), logs: [] };
    this.targets.set(id, target);
    const wc = view.webContents;
    wc.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    wc.session.setPermissionCheckHandler(() => false);
    // No unmanaged windows or privileged scheme navigations may escape the root.
    wc.setWindowOpenHandler(({ url: popupURL }) => {
      try { void wc.loadURL(browserURL(popupURL)).catch(() => {}); } catch { /* blocked scheme */ }
      return { action: "deny" };
    });
    const guard = (event: Electron.Event, nextURL: string) => {
      try { browserURL(nextURL); } catch { event.preventDefault(); }
    };
    wc.on("did-start-navigation", (_event, _url, _inPlace, isMainFrame) => { if (isMainFrame) target.generation += 1; });
    wc.on("will-navigate", guard);
    wc.on("will-redirect", guard);
    wc.on("console-message", (_event, level, message) => {
      target.logs.push({ level: level >= 3 ? "error" : level === 2 ? "warn" : "log", message: message.slice(0, 1000) });
      target.logs = target.logs.slice(-100);
    });
    wc.on("destroyed", () => { this.targets.delete(id); this.events.emit("closed", { ...scope, tabId: id }); });
    this.events.emit("opened", { ...scope, tabId: id });
    target.ready = (async () => {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([
          wc.loadURL(url),
          new Promise<never>((_resolve, reject) => { timer = setTimeout(() => { if (!wc.isDestroyed()) wc.stop(); reject(new Error("Page loading timed out after 20 seconds.")); }, 20_000); }),
        ]);
      } catch (error) {
        // Keep Chromium's error page reachable and closeable after a failed navigation.
        if (wc.isDestroyed()) throw error;
        target.logs.push({ level: "error", message: error instanceof Error ? error.message : String(error) });
      } finally { clearTimeout(timer); }
    })();
    await target.ready;
    return this.info(target);
  }
  present(scope: BrowserScope, id: string, owner: BrowserWindow, lease: string, bounds: BrowserBounds | null) {
    const target = this.get(scope, id);
    if (!bounds) {
      if (target.lease === lease) this.hide(target);
      return;
    }
    for (const other of this.targets.values()) if (other.owner === owner && other !== target) this.hide(other);
    if (target.owner !== owner) {
      this.hide(target);
      target.owner = owner;
      owner.contentView.addChildView(target.view);
      owner.once("closed", () => { if (this.targets.get(id) === target && target.owner === owner) this.close(scope, id); });
    }
    const zoom = owner.webContents.getZoomFactor();
    target.view.setBounds({ x: Math.round(bounds.x * zoom), y: Math.round(bounds.y * zoom),
      width: Math.max(1, Math.round(bounds.width * zoom)), height: Math.max(1, Math.round(bounds.height * zoom)) });
    target.lease = lease;
    target.visible = true;
    target.view.setVisible(true);
  }
  private hide(target: Target) {
    target.visible = false;
    if (target.view.webContents.isFocused() && target.owner && !target.owner.isDestroyed()) target.owner.webContents.focus();
    target.view.setVisible(false);
  }
  close(scope: BrowserScope, id: string) {
    const target = this.get(scope, id);
    this.targets.delete(id);
    if (target.owner && !target.owner.isDestroyed()) target.owner.contentView.removeChildView(target.view);
    target.view.webContents.close({ waitForBeforeUnload: false });
  }
  disposeProject(projectId: string) {
    for (const target of [...this.targets.values()]) if (target.scope.projectId === projectId) this.close(target.scope, target.id);
  }
  dispose() { for (const target of [...this.targets.values()]) this.close(target.scope, target.id); }
  async invoke(method: BrowserMethod, scope: BrowserScope, raw: unknown): Promise<unknown> {
    const params = browserMethodSchemas[method].parse(raw);
    if (method === "list") return { tabs: this.list(scope) };
    if (method === "open") return this.open(scope, browserMethodSchemas.open.parse(params));
    const { tabId } = browserMethodSchemas.state.parse(params);
    const target = this.get(scope, tabId);
    const { harness, view } = target;
    if (method === "close") { this.close(scope, tabId); return { closed: true, tabId }; }
    if (method === "screenshot") {
      const capture = await harness.Page.captureScreenshot({ format: "png", captureBeyondViewport: false });
      return { tabId, mimeType: "image/png", data: capture.data };
    }
    if (method === "state") {
      const [tree, document] = await Promise.all([
        harness.Accessibility.getFullAXTree({}),
        harness.Runtime.evaluate({ expression: "JSON.stringify({text:document.body?.innerText?.slice(0,24000)??'',scrollX,scrollY,width:innerWidth,height:innerHeight})", returnByValue: true }),
      ]);
      const nodes = tree.nodes.filter(node => !node.ignored).slice(0, 1000).map(node => ({
        backendNodeId: node.backendDOMNodeId, role: node.role?.value, name: boundedAX(node.name?.value),
        value: boundedAX(node.value?.value), description: boundedAX(node.description?.value),
        properties: node.properties?.slice(0, 32).map(p => ({ name: p.name, value: boundedAX(p.value.value) })),
      }));
      return { ...this.info(target), document: JSON.parse(String(document.result.value ?? "{}")), nodes,
        truncated: tree.nodes.filter(node => !node.ignored).length > 1000, provenance: "untrusted-page-content" };
    }
    if (method === "navigate") {
      const navigation = browserMethodSchemas.navigate.parse(params);
      if (navigation.url) {
        const result = await harness.Page.navigate({ url: browserURL(navigation.url) });
        if (result.errorText) throw new Error(result.errorText);
      } else if (navigation.direction === "back" && view.webContents.navigationHistory.canGoBack()) view.webContents.navigationHistory.goBack();
      else if (navigation.direction === "forward" && view.webContents.navigationHistory.canGoForward()) view.webContents.navigationHistory.goForward();
      else if (navigation.direction === "reload") await harness.Page.reload({});
      else if (navigation.direction === "stop") await harness.Page.stopLoading();
      else throw new Error("Supply a URL or an available navigation direction.");
      return this.info(target);
    }
    if (method === "input") await this.input(target, browserMethodSchemas.input.parse(params).input);
    return this.info(target);
  }
  async captureContext(scope: BrowserScope, id: string, expected: { url: string; generation: number; kind: "selection" | "screenshot" }) {
    const target = this.get(scope, id);
    const check = () => {
      if (target.view.webContents.isDestroyed() || target.generation !== expected.generation || target.view.webContents.getURL() !== expected.url) throw new Error("The page changed while adding context. Read the page and try again.");
    };
    check();
    let base64: string;
    if (expected.kind === "screenshot") {
      base64 = (await target.harness.Page.captureScreenshot({ format: "png", captureBeyondViewport: false })).data;
    } else {
      const selected = await target.harness.Runtime.evaluate({ expression: "window.getSelection()?.toString().slice(0,100000) ?? ''", returnByValue: true });
      const text = String(selected.result.value ?? "");
      if (!text.trim()) throw new Error("Select text in the page before adding it to the prompt.");
      base64 = Buffer.from(text, "utf8").toString("base64");
    }
    check();
    return { base64, mimeType: expected.kind === "screenshot" ? "image/png" : "text/plain", url: expected.url, generation: expected.generation };
  }
  clearConsole(scope: BrowserScope, id: string) { this.get(scope, id).logs = []; }
  metadata(scope: BrowserScope, id: string) { return this.info(this.get(scope, id)); }
  private async input(target: Target, input: BrowserInput) {
    const h = target.harness;
    if (input.action === "click" || input.action === "point") {
      let x: number, y: number;
      if (input.action === "click") {
        await h.DOM.scrollIntoViewIfNeeded({ backendNodeId: input.backendNodeId });
        const { model } = await h.DOM.getBoxModel({ backendNodeId: input.backendNodeId });
        x = (model.content[0]! + model.content[4]!) / 2;
        y = (model.content[1]! + model.content[5]!) / 2;
      } else { x = input.x; y = input.y; }
      await h.Input.dispatchMouseEvent({ type: "mousePressed", x, y, button: "left", clickCount: 1 });
      await h.Input.dispatchMouseEvent({ type: "mouseReleased", x, y, button: "left", clickCount: 1 });
    } else if (input.action === "type") {
      if (input.backendNodeId) await h.DOM.focus({ backendNodeId: input.backendNodeId });
      if (input.clear) {
        await h.Input.dispatchKeyEvent({ type: "keyDown", key: "a", code: "KeyA", modifiers: process.platform === "darwin" ? 4 : 2, commands: ["selectAll"] });
        await h.Input.dispatchKeyEvent({ type: "keyUp", key: "a", code: "KeyA" });
      }
      await h.Input.insertText({ text: input.text });
    } else if (input.action === "key") {
      const codes: Record<string, number> = { Enter: 13, Tab: 9, Escape: 27, Backspace: 8, Delete: 46, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, Home: 36, End: 35, PageUp: 33, PageDown: 34 };
      const key = { key: input.key, code: input.key, windowsVirtualKeyCode: codes[input.key], modifiers: input.modifiers ?? 0 };
      await h.Input.dispatchKeyEvent({ type: "keyDown", ...key, ...(input.key === "Enter" ? { text: "\r" } : {}) });
      await h.Input.dispatchKeyEvent({ type: "keyUp", ...key });
    } else await h.Input.dispatchMouseEvent({ type: "mouseWheel", x: input.x, y: input.y, deltaX: input.deltaX, deltaY: input.deltaY });
  }
}
function boundedAX(value: unknown) { return typeof value === "string" ? value.slice(0, 2000) : typeof value === "number" || typeof value === "boolean" ? value : undefined; }
export const browserService = new BrowserService();
