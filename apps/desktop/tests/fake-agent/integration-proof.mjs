/** Opt-in Electron proof: real session-provided stdio MCP configs, never a model. */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

/**
 * One client per server for the life of the agent process, the way a real agent keeps the MCP
 * servers `session/new` gave it for the whole session: started on first use with exactly the
 * command and environment the app sent, never restarted per call, and ended with the process.
 */
const clients = new Map();

async function withServer(config, operation) {
  if (!config) throw new Error('Requested integration was not supplied on session/new.');
  let client = clients.get(config.name);
  if (!client) {
    const env = { ...process.env, ...Object.fromEntries((config.env ?? []).map(entry => [entry.name, entry.value])) };
    const transport = new StdioClientTransport({ command: config.command, args: config.args ?? [], env });
    client = new Client({ name: 'text-to-cad-integration-proof', version: '1.0.0' });
    await client.connect(transport);
    clients.set(config.name, client);
  }
  return operation(client);
}
export async function integrationProof(servers, request) {
  if (request.operation === 'catalog') {
    const catalog = await Promise.all(servers.map(config => withServer(config, async client => ({ name: config.name, tools: (await client.listTools()).tools.map(tool => tool.name) }))));
    return { catalog };
  }
  if (request.operation === 'isolation') {
    const config = servers.find(server => server.name === 'text-to-cad-pdf');
    const env = Object.fromEntries(config.env.map(entry => [entry.name, entry.value]));
    const response = await fetch(`${env.TEXT_TO_CAD_BRIDGE_URL}/rpc`, { method: 'POST',
      headers: { authorization: `Bearer ${env.TEXT_TO_CAD_BRIDGE_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({ method: 'read_document', params: { tabId: request.tabId } }) });
    return { status: response.status, body: await response.json() };
  }
  if (request.operation === 'batch') return withServer(servers.find(server => server.name === `text-to-cad-${request.domain}`), async client => {
    const results = [];
    for (const call of request.calls) results.push(await client.callTool({ name: call.name, arguments: call.args ?? {} }));
    return results;
  });
  return withServer(servers.find(server => server.name === `text-to-cad-${request.domain}`), client => client.callTool({ name: request.name, arguments: request.args ?? {} }));
}
