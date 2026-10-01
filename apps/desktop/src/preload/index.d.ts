import type { TextToCadApi } from "../shared/ipc";

declare global {
  interface Window {
    /** The preload bridge. The renderer's only way off the page. */
    readonly textToCad: TextToCadApi;
  }
}

export {};
