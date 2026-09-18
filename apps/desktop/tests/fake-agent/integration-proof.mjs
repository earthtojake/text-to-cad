/** Opt-in Electron proof: real session-provided stdio MCP configs, never a model. */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

async function withServer(config, operation) {
  if (!config) throw new Error('Requested integration was not supplied on session/new.');
  const env = { ...process.env, ...Object.fromEntries((config.env ?? []).map(entry => [entry.name, entry.value])) };
  const transport = new StdioClientTransport({ command: config.command, args: config.args ?? [], env });
  const client = new Client({ name: 'hardcore-integration-proof', version: '1.0.0' });
  try { await client.connect(transport); return await operation(client); }
  finally { await client.close().catch(() => {}); await transport.close().catch(() => {}); }
}
export async function integrationProof(servers, request) {
  if (request.operation === 'catalog') {
    const catalog = [];
    for (const config of servers) catalog.push(await withServer(config, async client => ({ name: config.name, tools: (await client.listTools()).tools.map(tool => tool.name) })));
    return { catalog };
  }
  if (request.operation === 'isolation') {
    const config = servers.find(server => server.name === 'hardcore-pdf');
    const env = Object.fromEntries(config.env.map(entry => [entry.name, entry.value]));
    const response = await fetch(`${env.HARDCORE_BRIDGE_URL}/rpc`, { method: 'POST',
      headers: { authorization: `Bearer ${env.HARDCORE_BRIDGE_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({ method: 'read_document', params: { tabId: request.tabId } }) });
    return { status: response.status, body: await response.json() };
  }
  return withServer(servers.find(server => server.name === `hardcore-${request.domain}`), client => client.callTool({ name: request.name, arguments: request.args ?? {} }));
}
