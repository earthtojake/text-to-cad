import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { type BrowserWindow, WebContentsView } from "electron";
import { browserMethodSchemas, type BrowserInput, type BrowserMethod, type BrowserTarget } from "../../shared/browser";
import { browserHarness } from "./harness";
import { browserPartition, browserScopeKey, type BrowserScope } from "./storage";

export { browserScopeKey, type BrowserScope };
type Target = {
  scope: BrowserScope; id: string; view: WebContentsView; harness: ReturnType<typeof browserHarness>;
  owner?: BrowserWindow; lease?: string; dropOwnerClosed?: () => void; generation: number; visible: boolean; ready: Promise<void>; logs: BrowserTarget["logs"];
  /** Last key or mouse press that reached the page, and last one an agent sent over CDP (ms). */
  userInputAt: number; automatedInputAt: number;
};
/** How recent a press must be for a download to count as the person's own. */
const USER_GESTURE_MS = 2_000;
export type BrowserBounds = { x: number; y: number; width: number; height: number };
export function browserURL(value: string) {
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:" && value !== "about:blank") {
    throw new Error("Browser pages must use an HTTP or HTTPS URL.");
  }
  return url.href;
}

/** A load that reached the network and failed (DNS, refused, TLS), in words the tab can show. */
export function navigationFailure(address: string, errorText: string) {
  let host = address;
  try { host = new URL(address).host || address; } catch { /* shown as typed */ }
  return Object.assign(new Error(`${host} could not be reached: ${errorText}`), { name: "BrowserNavigationError" });
}

/** Owns live pages independently of whichever project or tab is painted. */
export class BrowserService {
  /** `opened` / `closed`, one listener pair per scoped CDP connection (they leave with it), so more than ten sessions' clients are ordinary. A finite cap, not 0: a listener leak past a hundred connections should still warn. */
  readonly events = new EventEmitter().setMaxListeners(100);
  private targets = new Map<string, Target>();
  /** App windows whose own reload/crash hides the pages they present. */
  private readonly watchedOwners = new WeakSet<BrowserWindow>();
  /** Storage partitions that already refuse downloads. */
  private readonly guardedPartitions = new WeakSet<Electron.Session>();
  private get(scope: BrowserScope, id: string) {
    const target = this.targets.get(id);
    if (!target || browserScopeKey(target.scope) !== browserScopeKey(scope) || target.view.webContents.isDestroyed()) {
      throw new Error("This browser tab is not available in this session's workspace.");
    }
    return target;
  }
  private info(target: Target, logs = true): BrowserTarget {
    const wc = target.view.webContents;
    return { tabId: target.id, ...target.scope, url: wc.getURL(), generation: target.generation, title: wc.getTitle(), loading: wc.isLoading(),
      canGoBack: wc.navigationHistory.canGoBack(), canGoForward: wc.navigationHistory.canGoForward(),
      visible: target.visible, logs: logs ? [...target.logs] : [], errors: target.logs.filter(line => line.level === "error").length };
  }
  private log(target: Target, level: BrowserTarget["logs"][number]["level"], message: string) {
    target.logs.push({ level, message: message.slice(0, 1000) });
    target.logs = target.logs.slice(-100);
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
    const partition = browserPartition(scope);
    const view = new WebContentsView({ webPreferences: {
      partition, nodeIntegration: false, contextIsolation: true, sandbox: true,
      webSecurity: true, backgroundThrottling: false, spellcheck: false,
    } });
    view.setBounds({ x: 0, y: 0, width: 1000, height: 700 });
    const target: Target = { id, scope: { ...scope }, view, harness: browserHarness(view.webContents), generation: 0, visible: false, ready: Promise.resolve(), logs: [], userInputAt: 0, automatedInputAt: 0 };
    this.targets.set(id, target);
    const wc = view.webContents;
    wc.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    wc.session.setPermissionCheckHandler(() => false);
    this.refuseDownloads(wc.session);
    // No unmanaged windows or privileged scheme navigations may escape the root.
    wc.setWindowOpenHandler(({ url: popupURL }) => {
      try { void wc.loadURL(browserURL(popupURL)).catch(() => {}); }
      catch { this.log(target, "error", `Only http and https addresses can be opened here: ${popupURL.slice(0, 200)} was not opened.`); }
      return { action: "deny" };
    });
    const guard = (event: Electron.Event, nextURL: string) => {
      try { browserURL(nextURL); } catch { event.preventDefault(); }
    };
    // A new document, not a pushState or fragment change: a single-page app
    // moving its own history keeps the generation "Add to prompt" captured.
    wc.on("did-start-navigation", details => { if (details.isMainFrame && !details.isSameDocument) target.generation += 1; });
    wc.on("before-input-event", (_event, input) => { if (input.type === "keyDown" || input.type === "rawKeyDown") target.userInputAt = Date.now(); });
    wc.on("before-mouse-event", (_event, mouse) => { if (mouse.type === "mouseDown") target.userInputAt = Date.now(); });
    wc.on("will-navigate", guard);
    wc.on("will-redirect", guard);
    // The event carries `level` ("info" | "warning" | "error" | "debug") and
    // `message`; the positional (numeric level, message) form is deprecated but
    // read as a fallback.
    wc.on("console-message", ((event: { level?: unknown; message?: unknown }, level?: number, message?: string) => {
      const severity = typeof event.level === "string" ? (event.level === "error" ? "error" : event.level === "warning" ? "warn" : "log")
        : (level ?? 0) >= 3 ? "error" : level === 2 ? "warn" : "log";
      this.log(target, severity, typeof event.message === "string" ? event.message : message ?? "");
    }) as never);
    // `close()` has already dropped the target, and the id may be a newer page's
    // by the time Chromium reports this one destroyed (archive, then a quick unarchive).
    wc.on("destroyed", () => {
      const current = this.targets.get(id);
      if (current && current !== target) return;
      this.targets.delete(id);
      this.events.emit("closed", { ...scope, tabId: id });
    });
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
        this.log(target, "error", error instanceof Error ? error.message : String(error));
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
      target.dropOwnerClosed?.();
      target.owner = owner;
      owner.contentView.addChildView(target.view);
      const onClosed = () => { if (this.targets.get(id) === target && target.owner === owner) this.close(scope, id); };
      owner.once("closed", onClosed);
      target.dropOwnerClosed = () => { owner.off("closed", onClosed); };
      this.watchOwner(owner);
    }
    const zoom = owner.webContents.getZoomFactor();
    target.view.setBounds({ x: Math.round(bounds.x * zoom), y: Math.round(bounds.y * zoom),
      width: Math.max(1, Math.round(bounds.width * zoom)), height: Math.max(1, Math.round(bounds.height * zoom)) });
    target.lease = lease;
    target.visible = true;
    target.view.setVisible(true);
  }
  /**
   * A reloaded or crashed app renderer has no browser tab mounted to hide its
   * pages, and a native view paints over whatever the new document shows. So
   * the owner's own reload hides every page it presented; the remounted tab
   * presents it again under a fresh lease. `did-navigate`, not
   * `did-start-loading`: loading starts before `beforeunload`, and a reload
   * the person cancels (unsaved drafts) must leave the pages where they are.
   */
  private watchOwner(owner: BrowserWindow) {
    if (this.watchedOwners.has(owner)) return;
    this.watchedOwners.add(owner);
    const hideAll = () => {
      for (const target of this.targets.values()) if (target.owner === owner) { target.lease = undefined; this.hide(target); }
    };
    owner.webContents.on("did-navigate", hideAll);
    // A reload that failed (a dev server that is down) commits an error page
    // without `did-navigate`. ERR_ABORTED (-3) is a superseded navigation, not a new page.
    owner.webContents.on("did-fail-load", (_event, errorCode, _description, _url, isMainFrame) => { if (isMainFrame && errorCode !== -3) hideAll(); });
    owner.webContents.on("render-process-gone", hideAll);
  }
  /**
   * A download the person starts — in the page that is shown, focused, in the
   * focused app window, within two seconds of a key or mouse press there that
   * no agent input accompanied — keeps the native save dialog. Anything else (an
   * agent's click in a background session, a page's own script while the
   * person works elsewhere) would open that dialog over whatever they are
   * doing, so it is cancelled and counted as an error in the page's console.
   */
  private refuseDownloads(partition: Electron.Session) {
    if (this.guardedPartitions.has(partition)) return;
    this.guardedPartitions.add(partition);
    partition.on("will-download", (event, item, contents) => {
      const target = [...this.targets.values()].find(candidate => candidate.view.webContents === contents);
      if (target && this.inForeground(target)) return;
      event.preventDefault();
      if (target) this.log(target, "error", `Downloads are not supported in this browser tab. Blocked: ${item.getFilename() || item.getURL()}.`);
    });
  }
  private inForeground(target: Target) {
    const owner = target.owner;
    const now = Date.now();
    return target.visible && !!owner && !owner.isDestroyed() && owner.isFocused()
      && !target.view.webContents.isDestroyed() && target.view.webContents.isFocused()
      // CDP input may reach the same hooks as a real press, so a page an agent
      // is driving never counts as the person's gesture.
      && now - target.userInputAt <= USER_GESTURE_MS && now - target.automatedInputAt > USER_GESTURE_MS;
  }
  /** An agent sent input to this page (CDP `Input.*`, or the app's own input method). */
  noteAutomatedInput(scope: BrowserScope, id: string) { this.get(scope, id).automatedInputAt = Date.now(); }
  private focusedTarget(owner?: BrowserWindow | null) {
    return [...this.targets.values()].find(candidate => candidate.visible && (!owner || candidate.owner === owner)
      && !candidate.view.webContents.isDestroyed() && candidate.view.webContents.isFocused());
  }
  /** Reload the embedded page that has keyboard focus. False when none has: then the key does nothing. */
  reloadFocused(owner?: BrowserWindow | null) {
    const target = this.focusedTarget(owner);
    if (!target) return false;
    target.view.webContents.reload();
    return true;
  }
  /**
   * Hand an app shortcut pressed inside the focused embedded page to the app's
   * own renderer, as the key it was: focus moves to the app, and its handlers
   * answer it the way they would have with the app focused. A page never sees
   * the app's keys, so without this the menu's accelerator is all that fires.
   * False when no page in `owner` has focus.
   */
  forwardFromFocused(owner: BrowserWindow, key: { keyCode: string; modifiers: Electron.InputEvent["modifiers"] }) {
    const target = this.focusedTarget(owner);
    if (!target || owner.isDestroyed()) return false;
    owner.webContents.focus();
    owner.webContents.sendInputEvent({ type: "keyDown", ...key });
    owner.webContents.sendInputEvent({ type: "keyUp", ...key });
    return true;
  }
  private hide(target: Target) {
    target.visible = false;
    if (target.view.webContents.isFocused() && target.owner && !target.owner.isDestroyed()) target.owner.webContents.focus();
    target.view.setVisible(false);
  }
  close(scope: BrowserScope, id: string) {
    const target = this.get(scope, id);
    this.targets.delete(id);
    target.dropOwnerClosed?.();
    if (target.owner && !target.owner.isDestroyed()) target.owner.contentView.removeChildView(target.view);
    target.view.webContents.close({ waitForBeforeUnload: false });
  }
  /** Close a session's pages; `keep` is a scope whose pages stay (the one its workspace still names). */
  disposeSession(sessionId: string, keep?: BrowserScope) {
    for (const target of [...this.targets.values()]) {
      if (target.scope.sessionId === sessionId && !(keep && browserScopeKey(target.scope) === browserScopeKey(keep))) this.close(target.scope, target.id);
    }
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
        if (result.errorText) throw navigationFailure(navigation.url, result.errorText);
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
  metadata(scope: BrowserScope, id: string, logs = true) { return this.info(this.get(scope, id), logs); }
  private async input(target: Target, input: BrowserInput) {
    target.automatedInputAt = Date.now();
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
