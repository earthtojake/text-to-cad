import type { WebContents } from "electron";
import { bindDomains } from "./vendor/generated";

/** Native transport for Browser Use's pinned MIT domain bindings. No debug port. */
export function browserHarness(contents: WebContents) {
  return bindDomains({
    _call: async (method, params = {}) => {
      if (contents.isDestroyed()) throw new Error("This browser tab is closed.");
      if (!contents.debugger.isAttached()) contents.debugger.attach("1.3");
      return contents.debugger.sendCommand(method, params);
    },
  });
}
