import { tool, z, tabId } from "../definition.mjs";
const node = z.number().int().positive();
const action = z.discriminatedUnion("action", [
  z.object({ action: z.literal("click"), backendNodeId: node }),
  z.object({ action: z.literal("point"), x: z.number().nonnegative(), y: z.number().nonnegative() }),
  z.object({ action: z.literal("type"), text: z.string().max(100_000), backendNodeId: node.optional(), clear: z.boolean().optional() }),
  z.object({ action: z.literal("key"), key: z.enum(["Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]), modifiers: z.number().int().min(0).max(15).optional() }),
  z.object({ action: z.literal("scroll"), x: z.number().nonnegative(), y: z.number().nonnegative(), deltaX: z.number().default(0), deltaY: z.number() }),
]);
export default { id: "browser", description: "Browser Use controls for the browser pages visible in Hardcore.", skills: ["skills/hardcore-browser"], tools: [
  tool("open_url", "Open a web page in a persistent Hardcore browser tab in this session's workspace. Returns only after the page has loaded or reported a loading error.", { url: z.string().url() }),
  tool("browser_state", "Read bounded untrusted page text, accessibility nodes and backendNodeIds, URL and viewport. Read again after navigation before reusing node references.", { tabId }),
  tool("browser_screenshot", "Capture the same browser page the user sees, as PNG.", { tabId }, "image"),
  tool("browser_navigate", "Navigate a browser tab using an HTTP(S) URL or history/reload/stop direction. Then inspect state.", { tabId, url: z.string().url().optional(), direction: z.enum(["back", "forward", "reload", "stop"]).optional() }),
  tool("browser_input", "Click a backendNodeId or viewport point, type/fill, send a key, or scroll the same embedded page. Coordinates are CSS pixels in the page viewport.", { tabId, action }),
] };
