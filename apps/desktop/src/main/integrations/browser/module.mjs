import { tool } from "../definition.mjs";

// The upstream runtime owns its tool catalog; only connection/bootstrap is app code.
export default {
  id: "browser", runtime: "playwright",
  description: "Playwright controls for the browser pages visible in text-to-cad.",
  skills: ["skills/text-to-cad-browser"], tools: [],
  hostTools: [tool("browser_connection", "Connect the browser server to this session's scoped native pages.")],
};
