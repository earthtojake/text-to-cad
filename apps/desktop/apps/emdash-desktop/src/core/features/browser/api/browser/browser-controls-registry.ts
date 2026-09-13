import type { BrowserWebviewAdapter } from '../../browser/browser-webview-types';

export type BrowserControls = {
  adapter: BrowserWebviewAdapter | null;
  focusUrl(): void;
};

class BrowserControlsRegistry {
  private readonly controls = new Map<string, BrowserControls>();

  register(browserId: string, controls: BrowserControls): () => void {
    this.controls.set(browserId, controls);
    return () => {
      if (this.controls.get(browserId) === controls) {
        this.controls.delete(browserId);
      }
    };
  }

  get(browserId: string): BrowserControls | undefined {
    return this.controls.get(browserId);
  }

  clear(): void {
    this.controls.clear();
  }
}

export const browserControlsRegistry = new BrowserControlsRegistry();
