import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@renderer/app/App";
import { applyCachedTheme } from "@renderer/hooks/use-theme";
import { applyPlatformClass } from "@renderer/lib/platform";
import { trackTitlebarInset } from "@renderer/lib/titlebar";
import "@renderer/styles/globals.css";

// Before the first paint: the leftmost pane reserves room for macOS's traffic
// lights, and finding that out over IPC would shift the layout. The class is
// the platform; the inset is measured from Chromium's window-controls overlay
// and then followed, so a macOS that draws the buttons wider moves the app's
// own controls rather than sliding them under the lights.
applyPlatformClass();
trackTitlebarInset();
// ...and the colour scheme, for the same reason and more visibly: the settings
// row lives in main's sqlite, so React's first passive effect is the earliest
// it can be applied from — and the window is shown once the renderer has
// painted, which is one paint too late. The cached preference (localStorage,
// written by `useApplyTheme`) resolved against the OS is what the person had
// last time, and the IPC read that follows corrects it.
applyCachedTheme();

const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html is missing #root");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
