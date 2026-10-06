// The hosted MCP server at /mcp: stateless Streamable HTTP, a fresh server per request.
// Discovery (initialize, tools/list) works signed out; a tools/call without credentials
// answers 401 with the Protected Resource Metadata URL, which is how hosts know to sign in.
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js';
import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import type { Auth, User } from './auth.ts';
import { isCloudError } from './errors.ts';
import { isTextPath } from './mime.ts';
import { buildJson, buildText, buildTitle, jobJson, jobText } from './present.ts';
import type { Build, Job, Service } from './service.ts';
import { encodePath } from './service.ts';
import { parseBuildRef } from './validate.ts';
import pkg from '../package.json' with { type: 'json' };

export const INSTRUCTIONS = `Text-to-CAD Cloud builds CAD models from Python code (cadgen + build123d) in a single-use sandbox and returns a link that opens the result in the CAD viewer. Use the cad-cloud skill when it is available.

A model is a Python script with a parameterless function decorated with @step(out="../STEP/<name>.step") (from cadgen import step; from cadgen import build123d as bd) that returns a build123d shape, called under if __name__ == "__main__". Output paths are relative to the script. One model per entry script.

cad_build sends the files and runs the entry script(s); without an entry it publishes the CAD files it is sent (STEP, STL, 3MF, GLB, DXF, URDF, SDF). To change a build, pass base=<build id> with only the changed files. Links look like https://<host>/b/<id>/<path> and open in the CAD viewer; references copied from the viewer are those URLs plus #<selector>: inspect them with cad_inspect(build=<id>) and cadgen's read_scene("<path>"). Check your work with cad_snapshot, and give the person the link.`;

type Content = CallToolResult['content'];

const READ_ONLY = { readOnlyHint: true, destructiveHint: false, openWorldHint: false } as const;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

export function createMcpServer(service: Service, user: User | null): McpServer {
  const server = new McpServer({ name: 'text-to-cad-cloud', title: 'Text-to-CAD Cloud', version: pkg.version }, { instructions: INSTRUCTIONS });
  const wait = service.config.limits.toolWaitSeconds;

  async function guarded(run: (user: User) => Promise<CallToolResult>): Promise<CallToolResult> {
    if (!user) return { content: [{ type: 'text', text: 'Sign in first: this tool needs an account.' }], isError: true };
    try {
      return await run(user);
    } catch (error) {
      if (isCloudError(error)) return { content: [{ type: 'text', text: error.message }], isError: true };
      throw error;
    }
  }

  /** An image as tool content; one too large for hosts to accept stays a link (in the text). */
  async function imageContent(key: string, type = 'image/png'): Promise<Content> {
    const object = await service.readObject(key);
    if (!object || object.bytes.byteLength > MAX_IMAGE_BYTES) return [];
    return [{ type: 'image', data: Buffer.from(object.bytes).toString('base64'), mimeType: type }];
  }

  async function buildResult(build: Build, deduped = false): Promise<CallToolResult> {
    const content: Content = [{ type: 'text', text: buildText(service, build, { deduped }) }];
    if (build.status === 'succeeded' && build.thumbnailKey) content.push(...(await imageContent(build.thumbnailKey)));
    return { content, structuredContent: buildJson(service, build, deduped ? { deduped } : {}), isError: build.status === 'failed' };
  }

  async function jobResult(job: Job): Promise<CallToolResult> {
    const content: Content = [{ type: 'text', text: jobText(service, job) }];
    for (const image of job.result?.images ?? []) {
      if (image.type === 'image/svg+xml') {
        const object = await service.readObject(image.key);
        if (object && object.bytes.byteLength <= 200_000) content.push({ type: 'text', text: new TextDecoder().decode(object.bytes) });
      } else {
        content.push(...(await imageContent(image.key, image.type)));
      }
    }
    return { content, structuredContent: jobJson(service, job), isError: job.status === 'failed' };
  }

  server.registerTool('cad_build', {
    title: 'Build a CAD model',
    description:
      'Run CAD model code (Python with cadgen and build123d) in a fresh sandbox and get a link that opens the result in the CAD viewer. ' +
      'Send every file the model needs in files: text, or {"base64": "..."} for binary files such as a vendor STEP. entry names the script(s) to run; ' +
      'it is optional: without it nothing runs and the CAD files sent (STEP, STL, 3MF, GLB, DXF, URDF, SRDF, SDF) are published as they are. ' +
      'Every CAD file of the build, sent or written, opens in the viewer. ' +
      'To change an existing build, pass base=<its id> with only the changed files (and delete for removed ones); entry then defaults to the base build\'s. ' +
      `Waits up to ${wait} s: a longer build returns its id and status, then call cad_status.`,
    inputSchema: {
      files: z.record(z.string(), z.union([z.string(), z.object({ base64: z.string() })])).optional()
        .describe('Path (relative, e.g. "src/bracket.py") to content: text, or {"base64": "..."} for binary files.'),
      entry: z.union([z.string(), z.array(z.string())]).optional()
        .describe('Optional. The model script(s) to run, e.g. "src/bracket.py". Omit it (or pass []) to publish the CAD files sent without running code.'),
      base: z.string().optional().describe('A build id (or link) whose files this build starts from.'),
      delete: z.array(z.string()).optional().describe('Paths of the base build to leave out.'),
      title: z.string().optional().describe('A short title for the link.'),
      pythonpath: z.array(z.string()).optional().describe('Folders (relative) to put on PYTHONPATH, e.g. ["src"].'),
    },
    annotations: { title: 'Build a CAD model', readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, (args) => guarded(async (signedIn) => {
    const { build, deduped } = await service.createBuild(signedIn, args);
    const settled = (await service.waitBuild(build.id, wait)) ?? build;
    return buildResult(settled, deduped);
  }));

  server.registerTool('cad_status', {
    title: 'Check a build or job',
    description: `The state of a build (or a snapshot/inspection job) by id: its link, outputs, error with file and line, and log. Waits up to wait seconds (default ${wait}) for it to finish.`,
    inputSchema: {
      id: z.string().describe('A build id, a build link, or a job id.'),
      wait: z.number().min(0).max(wait).optional().describe(`Seconds to wait for a running build or job (0 to ${wait}).`),
    },
    annotations: { title: 'Check a build or job', ...READ_ONLY },
  }, (args) => guarded(async (signedIn) => {
    const seconds = args.wait ?? wait;
    const ref = (() => {
      try {
        return parseBuildRef(args.id);
      } catch {
        return null;
      }
    })();
    const build = ref ? await service.waitBuild(ref.id, seconds) : null;
    if (build) return buildResult(build);
    const job = await service.getJob(String(args.id).trim());
    if (!job || job.userId !== signedIn.id) return { content: [{ type: 'text', text: `There is no build or job ${args.id}.` }], isError: true };
    return jobResult((await service.waitJob(job.id, seconds)) ?? job);
  }));

  server.registerTool('cad_snapshot', {
    title: 'Render a snapshot',
    description:
      'Render an image of a CAD file in a build with cadgen snapshot (in a sandbox). file defaults to the build\'s main output; a build link names the file too. ' +
      'args pass snapshot flags, e.g. ["--display", "render", "--camera", "iso"], ["--mode", "section", "--section", "XZ:10"] (with format "svg"), ["--focus", "o1.2"].',
    inputSchema: {
      build: z.string().describe('A build id or link.'),
      file: z.string().optional().describe('The CAD file in the build, e.g. "STEP/bracket.step".'),
      args: z.array(z.string()).optional().describe('cadgen snapshot flags: --display, --camera, --mode, --section, --focus, --hide, --kinematics, --animation, --time, --joint-values, --width, --height, --size-profile, --view-labels.'),
      format: z.enum(['png', 'svg']).optional().describe('png (default), or svg for a STEP section.'),
    },
    annotations: { title: 'Render a snapshot', ...READ_ONLY },
  }, (args) => guarded(async (signedIn) => {
    const job = await service.createJob(signedIn, 'snapshot', args);
    return jobResult((await service.waitJob(job.id, wait)) ?? job);
  }));

  server.registerTool('cad_inspect', {
    title: 'Inspect a build with Python',
    description:
      'Run a Python script against a build\'s files and outputs in a sandbox (working directory: the build root), e.g. ' +
      '`from cadgen import read_scene; scene = read_scene("STEP/bracket.step"); print(scene.resolve("STEP/bracket.step#f3").shape().area)`. ' +
      'Returns stdout, stderr and the exit code; PNG/SVG/JPEG images the script writes under tmp/ come back too.',
    inputSchema: {
      build: z.string().describe('A build id or link.'),
      code: z.string().describe('The Python script to run.'),
    },
    annotations: { title: 'Inspect a build with Python', ...READ_ONLY },
  }, (args) => guarded(async (signedIn) => {
    const job = await service.createJob(signedIn, 'inspect', args);
    return jobResult((await service.waitJob(job.id, wait)) ?? job);
  }));

  server.registerTool('cad_files', {
    title: 'List or read a build\'s files',
    description: 'Without path: every file of a build (sources and outputs). With path: that text file\'s content, or a download link for a binary file.',
    inputSchema: {
      build: z.string().describe('A build id or link.'),
      path: z.string().optional().describe('A file in the build, e.g. "src/bracket.py".'),
    },
    annotations: { title: 'List or read a build\'s files', ...READ_ONLY },
  }, (args) => guarded(async () => {
    const ref = parseBuildRef(args.build);
    const build = await service.getBuild(ref.id);
    if (!build) return { content: [{ type: 'text', text: `There is no build ${ref.id}.` }], isError: true };
    const fileUrl = (path: string) => `${service.config.publicUrl}/v1/builds/${build.id}/files/${encodePath(path)}`;
    const path = args.path ?? null;
    if (!path) {
      const files = service.buildFiles(build);
      const text = [`Build ${build.id} (${buildTitle(build)}): ${files.length} files`, ...files.map((file) => `${file.kind === 'output' ? 'out' : 'src'}  ${file.path}  (${file.bytes} bytes)`)].join('\n');
      return { content: [{ type: 'text', text }], structuredContent: { build: build.id, files: files.map((file) => ({ path: file.path, kind: file.kind, bytes: file.bytes, url: fileUrl(file.path) })) } };
    }
    const { file, bytes } = await service.readFile(build, path);
    if (!isTextPath(file.path) || bytes.byteLength > 256 * 1024) {
      return { content: [{ type: 'text', text: `${file.path} (${file.bytes} bytes) is not shown as text. Download: ${fileUrl(file.path)}` }] };
    }
    return { content: [{ type: 'text', text: new TextDecoder().decode(bytes) }] };
  }));

  server.registerTool('cad_builds', {
    title: 'List your builds',
    description: 'Your most recent builds, newest first, with their links.',
    inputSchema: { limit: z.number().int().min(1).max(50).optional().describe('How many (default 10).') },
    annotations: { title: 'List your builds', ...READ_ONLY },
  }, (args) => guarded(async (signedIn) => {
    const builds = await service.listBuilds(signedIn, args.limit ?? 10);
    if (!builds.length) return { content: [{ type: 'text', text: 'You have no builds yet. Start one with cad_build.' }] };
    const text = builds.map((build) => `${build.id}  ${build.status.padEnd(9)}  ${buildTitle(build)}  ${service.buildLink(build)}`).join('\n');
    return { content: [{ type: 'text', text }], structuredContent: { builds: builds.map((build) => buildJson(service, build)) } };
  }));

  return server;
}

const MAX_BODY = 32 * 1024 * 1024;

function jsonRpcError(status: number, code: number, message: string, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify({ jsonrpc: '2.0', error: { code, message }, id: null }), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

export async function handleMcp(request: Request, service: Service, auth: Auth): Promise<Response> {
  const metadata = `${service.config.publicUrl}/.well-known/oauth-protected-resource/mcp`;
  if (request.method !== 'POST') return jsonRpcError(405, -32000, 'This server is stateless: POST JSON-RPC messages to /mcp.', { allow: 'POST' });
  const length = Number(request.headers.get('content-length') ?? 0);
  if (length > MAX_BODY) return jsonRpcError(413, -32000, `The request is larger than ${MAX_BODY} bytes.`);
  const text = await request.text();
  if (text.length > MAX_BODY) return jsonRpcError(413, -32000, `The request is larger than ${MAX_BODY} bytes.`);
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return jsonRpcError(400, -32700, 'Parse error: the body is not JSON.');
  }
  const messages = Array.isArray(body) ? body : [body];
  const calls = messages.some((message) => message && typeof message === 'object' && (message as { method?: unknown }).method === 'tools/call');

  const result = await auth.authenticate(request);
  let user: User | null = null;
  if (result.ok) user = result.user;
  else if (result.reason === 'invalid' || calls) {
    return new Response(JSON.stringify({ error: result.reason === 'invalid' ? 'invalid_token' : 'unauthorized', error_description: result.message }), {
      status: 401,
      headers: {
        'content-type': 'application/json',
        'www-authenticate': auth.challenge(metadata, result.reason === 'invalid' ? 'invalid_token' : undefined),
      },
    });
  }

  const server = createMcpServer(service, user);
  const transport = new WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  await server.connect(transport);
  try {
    return await transport.handleRequest(request, { parsedBody: body });
  } finally {
    // Stateless: nothing outlives the request. The JSON response is complete by now.
    void transport.close().catch(() => {});
    void server.close().catch(() => {});
  }
}
