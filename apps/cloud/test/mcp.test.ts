import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { afterEach, describe, expect, it } from 'vitest';
import { PNG, PUBLIC_URL, boxSource, fakeSandbox, successfulBuild, testServer, type TestServer } from './helpers.ts';

let server: TestServer | undefined;
let client: Client | undefined;
afterEach(async () => {
  await client?.close();
  await server?.close();
  client = undefined;
  server = undefined;
});

/** A real MCP client over the real Streamable HTTP endpoint, with the app as its network. */
async function connect(s: TestServer, headers: Record<string, string> = {}) {
  const transport = new StreamableHTTPClientTransport(new URL(`${PUBLIC_URL}/mcp`), {
    fetch: async (input, init) => s.app.fetch(new Request(input, init)),
    requestInit: { headers },
  });
  const mcp = new Client({ name: 'test', version: '1.0.0' });
  await mcp.connect(transport);
  return mcp;
}

describe('MCP', () => {
  it('lists six tools with titles and explicit annotations', async () => {
    server = await testServer();
    client = await connect(server);
    expect(client.getInstructions()).toContain('cad-cloud skill');
    const { tools } = await client.listTools();
    expect(tools.map((tool) => tool.name).sort()).toEqual(['cad_build', 'cad_builds', 'cad_files', 'cad_inspect', 'cad_snapshot', 'cad_status']);
    for (const tool of tools) {
      expect(tool.title, tool.name).toBeTruthy();
      expect(tool.annotations, tool.name).toMatchObject({ destructiveHint: false, openWorldHint: false });
      expect(tool.annotations?.readOnlyHint, tool.name).toBe(tool.name !== 'cad_build');
    }
  });

  it('builds through cad_build and answers with the link and the thumbnail', async () => {
    server = await testServer();
    client = await connect(server);
    const result = await client.callTool({ name: 'cad_build', arguments: { files: { 'src/box.py': boxSource() }, entry: 'src/box.py' } });
    const content = result.content as { type: string; text?: string; data?: string; mimeType?: string }[];
    expect(result.isError).toBe(false);
    expect(content[0].text).toMatch(/Build \w{16} \(box\) succeeded/);
    expect(content[0].text).toContain(`${PUBLIC_URL}/b/`);
    expect(content[1]).toMatchObject({ type: 'image', mimeType: 'image/png', data: Buffer.from(PNG).toString('base64') });
    const id = (result.structuredContent as { id: string }).id;

    const files = await client.callTool({ name: 'cad_files', arguments: { build: `${PUBLIC_URL}/b/${id}/STEP/box.step`, path: 'src/box.py' } });
    expect((files.content as { text: string }[])[0].text).toBe(boxSource());
    const builds = await client.callTool({ name: 'cad_builds', arguments: {} });
    expect((builds.content as { text: string }[])[0].text).toContain(id);
    const status = await client.callTool({ name: 'cad_status', arguments: { id, wait: 0 } });
    expect((status.structuredContent as { status: string }).status).toBe('succeeded');
  });

  it('reports a refused request as a tool error', async () => {
    server = await testServer({ sandbox: fakeSandbox(successfulBuild) });
    client = await connect(server);
    const result = await client.callTool({ name: 'cad_build', arguments: { files: { '../x.py': 'x' }, entry: '../x.py' } });
    expect(result.isError).toBe(true);
    expect((result.content as { text: string }[])[0].text).toMatch(/stay inside/);
  });

  it('lets hosts discover tools signed out, and asks them to sign in for a call', async () => {
    server = await testServer({ env: { CLOUD_AUTH: 'oauth', AUTH_ISSUER: 'https://auth.example' } });
    client = await connect(server);
    expect((await client.listTools()).tools).toHaveLength(6);
    const response = await server.request('/mcp', {
      method: 'POST',
      headers: { accept: 'application/json, text/event-stream' },
      json: { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'cad_builds', arguments: {} } },
    });
    expect(response.status).toBe(401);
    expect(response.headers.get('www-authenticate')).toBe(`Bearer resource_metadata="${PUBLIC_URL}/.well-known/oauth-protected-resource/mcp"`);
  });
});
