import { z, tool, path, tabId } from "../definition.mjs";
export default { rendererCommands: {"list_open_tabs": "list-tabs", "show_tab": "show-tab", "close_tab": "close-tab"}, id: "workspace", description: "Open, reveal and navigate this workspace's tabs.", skills: [], tools: [
  tool("open_file", "Open a workspace file in Hardcore's registered renderer. Use the generated artifact, after it exists; do not launch another viewer.", { path }),
  tool("reveal", "Reveal a workspace file or directory without changing the file being viewed.", { path }),
  tool("list_open_tabs", "List tabs belonging to the calling session's project and root, including background tabs."),
  tool("show_tab", "Focus an existing tab in this session's workspace.", { tabId }),
  tool("close_tab", "Close a tab. Temporary drawings are discarded; terminal tabs stop their app-owned process. Dirty documents must be saved or explicitly discarded first.", { tabId }),
  tool("attach_snapshot", "Read an existing workspace image into this tool result so the agent and user can inspect it.", { path }, "image"),
  tool("list_skills", "List the focused skills supplied to this session."),
  tool("read_skill", "Read a supplied skill or a file within it.", { name: z.string().min(1), path: z.string().optional() }),
] };
