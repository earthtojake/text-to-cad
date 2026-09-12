import type { HardcoreApi } from "../shared/ipc";

declare global {
  interface Window {
    /** The preload bridge. The renderer's only way off the page. */
    readonly hardcore: HardcoreApi;
  }
}

export {};
