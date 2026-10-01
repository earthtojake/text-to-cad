import type { McpServer } from "@agentclientprotocol/sdk";
import type { McpBridge, BridgeSession } from "./mcp-bridge";
import { integrations } from "./registry.mjs";
/** Independent server identity and capabilities; no domain owns another domain's tools. */
export function integrationServers(bridge: McpBridge, session: BridgeSession): McpServer[] {
  return integrations.map(integration => bridge.serverFor(session, integration.id));
}
