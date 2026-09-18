import { z } from "zod";
export { z };
export const tabId = z.string().min(1);
export const path = z.string().min(1);
/** A serializable MCP contract shared by the server and the authenticated host bridge. */
export function tool(name, description, shape = {}, output = "json") {
  return { name, description, inputSchema: z.object(shape).strict(), output };
}
