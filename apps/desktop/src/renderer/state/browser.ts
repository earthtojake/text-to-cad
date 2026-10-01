import { create } from "zustand";
import type { BrowserTarget } from "@shared/browser";
import { errorMessage } from "@shared/ipc/errors";
import { useExplorer } from "./explorer";

type BrowserBinding = { sessionId: string; projectId: string; root: string | null; tabId: string };
type BrowserState = {
  targets: Record<string, BrowserTarget>;
  errors: Record<string, string | undefined>;
  /** Tabs whose console panel is open: only those poll for console lines. */
  consoles: Record<string, boolean | undefined>;
  setConsoleOpen: (tabId: string, open: boolean) => void;
  mount: (binding: BrowserBinding, url: string | null, element: HTMLElement) => () => void;
  navigate: (binding: BrowserBinding, navigation: { url?: string; direction?: "back" | "forward" | "reload" | "stop" }) => Promise<void>;
  clearConsole: (tabId: string) => void;
  contextAttachment: (binding: BrowserBinding, target: BrowserTarget, kind: "selection" | "screenshot") => Promise<Blob>;
};

/** Renderer chrome borrows a page; unmount hides it and never destroys its document. */
export const useBrowser = create<BrowserState>((set, get) => {
  /** Wakes a mounted tab's poll now (the console was just opened). */
  const wakers = new Map<string, () => void>();
  /** Tabs whose shown error is a refused navigation: only the next successful navigation clears it, not a metadata poll. */
  const navigationFailures = new Set<string>();
  const accept = (incoming: BrowserTarget, withLogs = true, navigated = false) => {
    const state = get();
    if (navigated) navigationFailures.delete(incoming.tabId);
    const keepError = navigationFailures.has(incoming.tabId);
    const previous = state.targets[incoming.tabId];
    // A poll without console lines keeps the lines already shown.
    const target = withLogs ? incoming : { ...incoming, logs: previous?.logs ?? [] };
    if (!previous || !sameTarget(previous, target) || (!keepError && state.errors[target.tabId] !== undefined)) {
      set(current => ({ targets: { ...current.targets, [target.tabId]: target }, errors: keepError ? current.errors : { ...current.errors, [target.tabId]: undefined } }));
    }
    const explorer = useExplorer.getState();
    const tab = explorer.tabs.find(tab => tab.id === target.tabId);
    if (explorer.sessionId === target.sessionId && explorer.projectId === target.projectId && tab?.kind === "browser" && target.url && target.url !== "about:blank" && tab.url !== target.url) {
      explorer.update(tab.id, { url: target.url });
    }
  };
  const failed = (tabId: string, error: unknown, fromNavigation = false) => {
    if (fromNavigation) navigationFailures.add(tabId); else navigationFailures.delete(tabId);
    const message = errorMessage(error);
    // The same failure again is not a change: no new state, no re-render.
    if (get().errors[tabId] !== message) set(state => ({ errors: { ...state.errors, [tabId]: message } }));
  };
  return {
    targets: {}, errors: {}, consoles: {},
    setConsoleOpen: (tabId, open) => {
      if (Boolean(get().consoles[tabId]) === open) return;
      set(state => ({ consoles: { ...state.consoles, [tabId]: open } }));
      if (open) wakers.get(tabId)?.();
    },
    mount: (binding, url, element) => {
      const lease = crypto.randomUUID();
      // `stopped`: the workspace refused this tab (archived, deleted, its
      // worktree removed). Every later poll would fail the same way.
      let disposed = false, ready = false, pending = false, stopped = false;
      let previousBox = "";
      let frame = 0;
      const present = () => {
        if (disposed || !ready) return;
        const rect = element.getBoundingClientRect();
        const pageURL = get().targets[binding.tabId]?.url;
        const occluded = !!document.querySelector('[role="dialog"], [role="menu"], [data-radix-popper-content-wrapper], [data-sonner-toast]');
        const bounds = !occluded && pageURL && pageURL !== "about:blank" && rect.width > 0 && rect.height > 0
          ? { x: Math.max(0, rect.x), y: Math.max(0, rect.y), width: rect.width, height: rect.height } : null;
        const key = JSON.stringify(bounds);
        if (key === previousBox) return;
        previousBox = key;
        void window.textToCad.browser.present({ ...binding, lease, bounds }).catch(error => failed(binding.tabId, error));
      };
      // Layout and overlays are read at most once per frame, however many
      // mutations a streamed transcript makes in it.
      const schedule = () => {
        if (disposed || frame) return;
        frame = requestAnimationFrame(() => { frame = 0; present(); });
      };
      const poll = async () => {
        if (disposed || !ready || pending || stopped) return;
        pending = true;
        const logs = Boolean(get().consoles[binding.tabId]);
        try { const target = await window.textToCad.browser.metadata({ ...binding, logs }); if (!disposed) { accept(target, logs); schedule(); } }
        catch (error) {
          // A workspace refusal will not change by asking again; anything else
          // (a transient failure) keeps polling.
          if (!disposed) { if (isScopeRefusal(error)) stopped = true; failed(binding.tabId, error); }
        } finally { pending = false; }
      };
      const wake = () => { stopped = false; void poll(); };
      wakers.set(binding.tabId, wake);
      void window.textToCad.browser.ensure({ ...binding, url }).then(target => {
        if (disposed) return;
        ready = true;
        accept(target);
        present();
      }).catch(error => { if (!disposed) failed(binding.tabId, error); });
      const resize = new ResizeObserver(schedule);
      resize.observe(element);
      const overlays = new MutationObserver(schedule);
      overlays.observe(document.body, { childList: true, subtree: true });
      window.addEventListener("resize", schedule);
      // A sibling pane moving changes our origin even when this element's size is unchanged.
      const timer = window.setInterval(() => { schedule(); void poll(); }, 500);
      return () => {
        disposed = true;
        if (wakers.get(binding.tabId) === wake) wakers.delete(binding.tabId);
        if (frame) cancelAnimationFrame(frame);
        resize.disconnect(); overlays.disconnect(); window.removeEventListener("resize", schedule); clearInterval(timer);
        void window.textToCad.browser.present({ ...binding, lease, bounds: null }).catch(() => {});
      };
    },
    navigate: async (binding, navigation) => {
      try { accept(await window.textToCad.browser.navigate({ ...binding, ...navigation }), true, true); wakers.get(binding.tabId)?.(); }
      catch (error) { failed(binding.tabId, error, true); }
    },
    contextAttachment: async (binding, target, kind) => {
      const captured = await window.textToCad.browser.capture({ ...binding, url: target.url, generation: target.generation, kind });
      return new Blob([Uint8Array.from(atob(captured.base64), character => character.charCodeAt(0))], { type: captured.mimeType });
    },
    clearConsole: tabId => set(state => {
      const target = state.targets[tabId];
      if (target) void window.textToCad.browser.clearConsole({ sessionId: target.sessionId, projectId: target.projectId, root: target.root, tabId }).catch(() => {});
      return target ? { targets: { ...state.targets, [tabId]: { ...target, logs: [], errors: 0 } } } : {};
    }),
  };
});

/**
 * Refusals asking again cannot change: the scope checks in
 * `src/main/ipc/browser.ts`, `rootOf`'s closed project, and the service's
 * closed or destroyed tab.
 */
const SCOPE_REFUSALS = [
  "This session is no longer active.", "This session's workspace is missing.", "This browser belongs to a different session workspace.",
  "that project is no longer open", "This browser tab is not available in this session's workspace.",
];
function isScopeRefusal(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return SCOPE_REFUSALS.some(refusal => message.includes(refusal));
}

function sameTarget(a: BrowserTarget, b: BrowserTarget): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)] as (keyof BrowserTarget)[]);
  for (const key of keys) if (key !== "logs" && a[key] !== b[key]) return false;
  return a.logs.length === b.logs.length && a.logs.every((line, index) => line.level === b.logs[index]!.level && line.message === b.logs[index]!.message);
}
