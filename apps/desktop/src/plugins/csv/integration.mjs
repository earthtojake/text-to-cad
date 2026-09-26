/** Step 2: the agent tools (main's half). Each one's name is a key of the manifest's `commands`. */
import { tool, tabId } from "../../main/integrations/definition.mjs";
import manifest from "./manifest.mjs";

export default { id: manifest.id, description: manifest.description, skills: [...manifest.skills], rendererCommands: manifest.commands, tools: [
  tool("csv_state", "Read the open CSV/TSV table's shape: its header, row count, column count and first rows.", { tabId }),
] };
