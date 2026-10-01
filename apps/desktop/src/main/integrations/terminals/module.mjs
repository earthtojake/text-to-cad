import { tool, z, tabId } from "../definition.mjs";
export default { id: "terminals", description: "Read and operate app-owned terminals in this workspace.", skills: ["skills/terminals"], tools: [
  tool("create_terminal", "Create an app-owned terminal in this session's workspace and display its tab.", { cwd: z.string().optional() }),
  tool("read_terminal", "Read bounded terminal output after an optional sequence cursor. Includes exit and truncation metadata.", { tabId, after: z.number().int().nonnegative().optional(), limit: z.number().int().positive().max(100000).optional() }),
  tool("write_terminal", "Write to a terminal only when its observed output cursor matches and no user input has occurred since observation. Include a newline to execute a command.", { tabId, data: z.string().max(65536), expectedSequence: z.number().int().nonnegative(), expectedInputRevision: z.number().int().nonnegative() }),
  tool("stop_terminal", "Stop the app-owned terminal process, leaving its output available for review.", { tabId }),
] };
