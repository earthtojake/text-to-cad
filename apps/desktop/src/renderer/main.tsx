import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@renderer/app/App";
import { applyPlatformClass } from "@renderer/lib/platform";
import "@renderer/styles/globals.css";

// Before the first paint: the sidebar's top strip reserves room for macOS's
// traffic lights, and finding that out over IPC would shift the layout.
applyPlatformClass();

const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html is missing #root");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
