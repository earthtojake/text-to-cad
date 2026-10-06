import { mkdtemp, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { sha256Hex } from '../server/ids.ts';
import { createLocalSandbox } from '../server/sandbox/local.ts';
import type { SandboxJob } from '../server/sandbox/protocol.ts';
import { createVercelSandbox } from '../server/sandbox/vercel.ts';
import { createFsStore, createR2Store } from '../server/store.ts';

let dir: string;
beforeEach(async () => {
  dir = await mkdtemp(path.join(tmpdir(), 't2c-providers-'));
});
afterEach(async () => {
  await rm(dir, { recursive: true, force: true });
});

const job = (request: Record<string, unknown> = {}, timeoutSeconds = 30): SandboxJob => ({
  id: 'job',
  kind: 'build',
  request,
  files: [{ path: 'src/a.py', bytes: new TextEncoder().encode('print(1)\n') }],
  timeoutSeconds,
  vcpus: 2,
  limits: { maxCollectBytes: 1024 * 1024, maxCollectFiles: 10 },
});

const RESULT = { ok: true, kind: 'build', exitCode: 0, wallMs: 1, error: null, log: '', stdout: '', stderr: '', outputs: ['out.txt'], dropped: [], primary: null, export: null, exportError: null, thumbnail: null, images: [], flags: { network: false }, cadgen: null };

describe('object stores', () => {
  it('fs: stores immutable objects by key and refuses keys that escape', async () => {
    const store = createFsStore(path.join(dir, 'store'));
    await store.put('o/abc', new TextEncoder().encode('hi'), 'text/plain');
    expect(await store.exists('o/abc')).toBe(true);
    expect(await store.get('o/abc')).toEqual({ bytes: new TextEncoder().encode('hi'), type: 'text/plain' });
    expect(await store.get('o/missing')).toBeNull();
    expect(store.publicUrl('o/abc')).toBe('/o/o/abc');
    await expect(store.put('../x', new Uint8Array(), 'x')).rejects.toThrow(/invalid object key/);
  });

  it('r2: signs S3 requests and marks objects immutable', async () => {
    const requests: Request[] = [];
    const store = createR2Store({
      endpoint: 'https://acct.r2.cloudflarestorage.com',
      bucket: 'cad',
      accessKeyId: 'AKID',
      secretAccessKey: 'secret',
      publicBaseUrl: 'https://files.example',
      fetch: (async (request: Request) => {
        requests.push(request);
        return request.method === 'PUT' ? new Response(null, { status: 200 }) : new Response(null, { status: 404 });
      }) as typeof fetch,
    });
    await store.put('o/abc', new TextEncoder().encode('hi'), 'model/step');
    expect(requests[0].method).toBe('PUT');
    expect(requests[0].url).toBe('https://acct.r2.cloudflarestorage.com/cad/o/abc');
    expect(requests[0].headers.get('authorization')).toMatch(/^AWS4-HMAC-SHA256 Credential=AKID\//);
    expect(requests[0].headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
    expect(await store.get('o/missing')).toBeNull();
    expect(await store.exists('o/missing')).toBe(false);
    expect(store.publicUrl('o/abc')).toBe('https://files.example/o/abc');
  });
});

describe('vercel sandbox', () => {
  function fakeVm(result: object | null, files: Record<string, string> = {}) {
    const calls = { created: [] as any[], written: [] as string[], commands: [] as any[], stopped: 0, deleted: 0 };
    const vm = {
      async writeFiles(list: { path: string }[]) {
        calls.written.push(...list.map((file) => file.path));
      },
      async runCommand(params: any) {
        calls.commands.push(params);
        return {
          async *logs() {
            yield { stream: 'stdout', data: '{"type":"progress","state":"building","phase":"Building geometry"}\n' };
            yield { stream: 'stderr', data: 'noise\n' };
          },
          async wait() {
            return { exitCode: 0 };
          },
        };
      },
      async readFileToBuffer({ path: name }: { path: string }) {
        if (name.endsWith('/result.json')) return result ? Buffer.from(JSON.stringify(result)) : null;
        const key = Object.keys(files).find((candidate) => name.endsWith(`/${candidate}`));
        return key ? Buffer.from(files[key]) : null;
      },
      async stop() {
        calls.stopped += 1;
        return { activeCpuDurationMs: 1234 };
      },
      async delete() {
        calls.deleted += 1;
      },
    };
    const create = async (params: any) => {
      calls.created.push(params);
      return vm as any;
    };
    return { calls, create };
  }

  it('runs the runner in a deny-all VM from the snapshot and always stops it', async () => {
    const output = 'STEP';
    const { calls, create } = fakeVm({ ...RESULT, files: [{ path: 'workspace/out.txt', bytes: 4, sha256: sha256Hex(output) }] }, { 'workspace/out.txt': output });
    const provider = createVercelSandbox({ snapshotId: 'snap_1', python: '/vercel/sandbox/venv/bin/python', runner: '/vercel/sandbox/runner/run.py', jobRoot: '/vercel/sandbox/job', create });
    const events: unknown[] = [];
    const run = await provider.run(job(), { onEvent: (event) => events.push(event) });
    expect(calls.created[0]).toMatchObject({
      source: { type: 'snapshot', snapshotId: 'snap_1' },
      resources: { vcpus: 2 },
      networkPolicy: 'deny-all',
      persistent: false,
      timeout: (30 + 180) * 1000,
    });
    expect(calls.written).toEqual(['/vercel/sandbox/job/request.json', '/vercel/sandbox/job/workspace/src/a.py']);
    expect(calls.commands[0]).toMatchObject({ cmd: '/vercel/sandbox/venv/bin/python', args: ['/vercel/sandbox/runner/run.py', '/vercel/sandbox/job'], cwd: '/vercel/sandbox/job/workspace' });
    expect(events).toEqual([expect.objectContaining({ type: 'progress', phase: 'Building geometry' })]);
    expect(new TextDecoder().decode(run.files.get('workspace/out.txt'))).toBe('STEP');
    expect(run.usage.activeCpuMs).toBe(1234);
    expect([calls.stopped, calls.deleted]).toEqual([1, 1]);
  });

  it('stops the VM when the job leaves no result', async () => {
    const { calls, create } = fakeVm(null);
    const provider = createVercelSandbox({ snapshotId: 'snap_1', python: 'python', runner: 'run.py', jobRoot: '/job', create });
    await expect(provider.run(job())).rejects.toThrow(/left no result/);
    expect([calls.stopped, calls.deleted]).toEqual([1, 1]);
  });
});

describe('local sandbox', () => {
  // A stand-in runner in Node: the provider's process handling is what is under test.
  async function runner(body: string) {
    const file = path.join(dir, 'runner.mjs');
    await writeFile(file, `import fs from 'node:fs'; import path from 'node:path';
const job = process.argv[2];
const request = JSON.parse(fs.readFileSync(path.join(job, 'request.json'), 'utf8'));
const write = (name, text) => { fs.mkdirSync(path.dirname(path.join(job, name)), { recursive: true }); fs.writeFileSync(path.join(job, name), text); };
const finish = (result) => fs.writeFileSync(path.join(job, 'result.json'), JSON.stringify(result));
${body}`);
    return createLocalSandbox({ python: process.execPath, runner: file, jobsDir: path.join(dir, 'jobs'), env: { PATH: process.env.PATH, HOME: process.env.HOME, SECRET_TOKEN: 'leak' }, killGraceSeconds: 0 });
  }

  it('runs the job in a fresh folder without the server\'s secrets, then removes it', async () => {
    const provider = await runner(`
console.log(JSON.stringify({ type: 'progress', state: 'building', phase: 'Saving STEP' }));
const env = JSON.stringify(Object.keys(process.env));
write('workspace/out.txt', env);
const sha = (await import('node:crypto')).createHash('sha256').update(env).digest('hex');
finish({ ...${JSON.stringify(RESULT)}, kind: request.kind, files: [{ path: 'workspace/out.txt', bytes: Buffer.byteLength(env), sha256: sha }] });`);
    const events: unknown[] = [];
    const run = await provider.run(job(), { onEvent: (event) => events.push(event) });
    const env = JSON.parse(new TextDecoder().decode(run.files.get('workspace/out.txt')));
    expect(env).toContain('PATH');
    expect(env).not.toContain('SECRET_TOKEN');
    expect(events).toEqual([expect.objectContaining({ phase: 'Saving STEP' })]);
    expect(await readdir(path.join(dir, 'jobs'))).toEqual([]);
  });

  it('refuses a collected file that is a symlink out of the job', async () => {
    const outside = path.join(dir, 'secret.txt');
    await writeFile(outside, 'secret');
    const provider = await runner(`
fs.mkdirSync(path.join(job, 'workspace'), { recursive: true });
fs.symlinkSync(${JSON.stringify(outside)}, path.join(job, 'workspace/out.txt'));
finish({ ...${JSON.stringify(RESULT)}, files: [{ path: 'workspace/out.txt', bytes: 6, sha256: '${sha256Hex('secret')}' }] });`);
    await expect(provider.run(job())).rejects.toThrow(/not a regular file/);
  });

  it('kills a job that runs past its timeout', async () => {
    const provider = await runner('setInterval(() => {}, 1000);');
    await expect(provider.run(job({}, 1))).rejects.toThrow(/ran past its 1 s limit and was killed/);
  });

  it('refuses to run in production unless allowed', async () => {
    const provider = createLocalSandbox({ python: process.execPath, runner: 'x', production: true });
    await expect(provider.run(job())).rejects.toThrow(/refused in production/);
  });
});
