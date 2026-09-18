import { create } from "zustand";
import type { BrowserTarget } from "@shared/browser";
import { useExplorer } from "./explorer";

type BrowserBinding = { sessionId: string; projectId: string; root: string | null; tabId: string };
type BrowserState = {
  targets: Record<string, BrowserTarget>;
  errors: Record<string, string | undefined>;
  mount: (binding: BrowserBinding, url: string | null, element: HTMLElement) => () => void;
  navigate: (binding: BrowserBinding, navigation: { url?: string; direction?: "back" | "forward" | "reload" | "stop" }) => Promise<void>;
  clearConsole: (tabId: string) => void;
  contextAttachment: (binding: BrowserBinding, target: BrowserTarget, kind: "selection" | "screenshot") => Promise<Blob>;
};

/** Renderer chrome borrows a page; unmount hides it and never destroys its document. */
export const useBrowser = create<BrowserState>((set, get) => {
  const accept = (target: BrowserTarget) => {
    set(state => ({ targets: { ...state.targets, [target.tabId]: target }, errors: { ...state.errors, [target.tabId]: undefined } }));
    const explorer = useExplorer.getState();
    const tab = explorer.tabs.find(tab => tab.id === target.tabId);
    if (explorer.sessionId === target.sessionId && explorer.projectId === target.projectId && tab?.kind === "browser" && target.url && target.url !== "about:blank" && tab.url !== target.url) {
      explorer.update(tab.id, { url: target.url });
    }
  };
  const failed = (tabId: string, error: unknown) => set(state => ({ errors: { ...state.errors, [tabId]: error instanceof Error ? error.message : String(error) } }));
  return {
    targets: {}, errors: {},
    mount: (binding, url, element) => {
      const lease = crypto.randomUUID();
      let disposed = false, ready = false, pending = false;
      let previousBox = "";
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
        void window.hardcore.browser.present({ ...binding, lease, bounds }).catch(error => failed(binding.tabId, error));
      };
      const poll = async () => {
        if (disposed || !ready || pending) return;
        pending = true;
        try { const target = await window.hardcore.browser.metadata(binding); if (!disposed) { accept(target); present(); } }
        catch (error) { if (!disposed) failed(binding.tabId, error); }
        finally { pending = false; }
      };
      void window.hardcore.browser.ensure({ ...binding, url }).then(target => {
        if (disposed) return;
        ready = true;
        accept(target);
        present();
      }).catch(error => { if (!disposed) failed(binding.tabId, error); });
      const resize = new ResizeObserver(present);
      resize.observe(element);
      const overlays = new MutationObserver(present);
      overlays.observe(document.body, { childList: true, subtree: true });
      window.addEventListener("resize", present);
      // A sibling pane moving changes our origin even when this element's size is unchanged.
      const timer = window.setInterval(() => { present(); void poll(); }, 500);
      return () => {
        disposed = true;
        resize.disconnect(); overlays.disconnect(); window.removeEventListener("resize", present); clearInterval(timer);
        void window.hardcore.browser.present({ ...binding, lease, bounds: null }).catch(() => {});
      };
    },
    navigate: async (binding, navigation) => {
      try { accept(await window.hardcore.browser.navigate({ ...binding, ...navigation })); }
      catch (error) { failed(binding.tabId, error); }
    },
    contextAttachment: async (binding, target, kind) => {
      const captured = await window.hardcore.browser.capture({ ...binding, url: target.url, generation: target.generation, kind });
      return new Blob([Uint8Array.from(atob(captured.base64), character => character.charCodeAt(0))], { type: captured.mimeType });
    },
    clearConsole: tabId => set(state => {
      const target = state.targets[tabId];
      if (target) void window.hardcore.browser.clearConsole({ sessionId: target.sessionId, projectId: target.projectId, root: target.root, tabId }).catch(() => {});
      return target ? { targets: { ...state.targets, [tabId]: { ...target, logs: [] } } } : {};
    }),
  };
});
