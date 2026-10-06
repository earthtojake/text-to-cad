import { afterEach, describe, expect, it } from 'vitest';
import { sha256Hex } from '../server/ids.ts';
import { pickPrimary } from '../server/service.ts';
import { objectKey } from '../server/store.ts';
import { PNG, boxSource, fakeSandbox, gate, successfulBuild, testClock, testServer, type TestServer } from './helpers.ts';

let server: TestServer | undefined;
afterEach(async () => {
  await server?.close();
  server = undefined;
});

const post = (s: TestServer, json: unknown, query = '?wait=5') => s.request(`/v1/builds${query}`, { method: 'POST', json });

describe('builds', () => {
  it('runs a build and stores its inputs, outputs, export and thumbnail', async () => {
    const sandbox = fakeSandbox(successfulBuild);
    server = await testServer({ sandbox });
    const response = await post(server, { files: { 'src/box.py': boxSource() }, entry: 'src/box.py', pythonpath: ['src'], title: 'A box' });
    expect(response.status).toBe(201);
    const build = await response.json();
    expect(build).toMatchObject({
      status: 'succeeded',
      title: 'A box',
      primary: 'STEP/box.step',
      outputs: ['STEP/box.step'],
      link: `http://cloud.test/b/${build.id}/STEP/box.step`,
      view: { available: true, error: null },
    });
    expect(build.id).toMatch(/^[0-9A-Za-z]{16}$/);
    expect(build.thumbnail).toBe(`http://cloud.test/o/${objectKey(sha256Hex(PNG))}`);
    expect(build.cost.vcpuSeconds).toBe(2);

    const job = sandbox.jobs[0];
    expect(job).toMatchObject({ kind: 'build', vcpus: 2, timeoutSeconds: 600, request: { entry: ['src/box.py'], pythonpath: ['src'], thumbnail: true } });
    expect(job.files.map((file) => file.path)).toEqual(['src/box.py']);

    const { store } = server.deps;
    expect(await store.exists(objectKey(sha256Hex(boxSource())))).toBe(true);
    expect(await store.exists(`b/${build.id}/export.json`)).toBe(true);
    expect(await store.exists(objectKey(sha256Hex('surf:box')))).toBe(true);

    const files = await (await server.request(`/v1/builds/${build.id}/files`)).json();
    expect(files.files.map((file: { path: string; kind: string }) => [file.path, file.kind])).toEqual([['STEP/box.step', 'output'], ['src/box.py', 'input']]);
    const source = await server.request(`/v1/builds/${build.id}/files/src/box.py`);
    expect(await source.text()).toBe(boxSource());
    const step = await server.request(`/v1/builds/${build.id}/files/STEP/box.step`);
    expect(step.status).toBe(302);
  });

  it('publishes the CAD files it is sent when there is no entry, and every viewable file gets a link', async () => {
    const sandbox = fakeSandbox(() => ({ result: { outputs: [], primary: 'parts/motor.step', thumbnail: 'out/thumbnail.png' }, files: { 'out/thumbnail.png': PNG } }));
    server = await testServer({ sandbox });
    const files = { 'parts/motor.step': 'ISO-10303-21;', 'robot/arm.urdf': '<robot name="arm"/>', 'notes.md': '# notes' };
    const build = await (await post(server, { files })).json();
    expect(build).toMatchObject({ status: 'succeeded', entry: [], outputs: [], primary: 'parts/motor.step', link: `http://cloud.test/b/${build.id}/parts/motor.step` });
    expect(build.views.map((view: { path: string }) => view.path)).toEqual(['parts/motor.step', 'robot/arm.urdf']);
    expect(sandbox.jobs[0].request.entry).toEqual([]);
    expect(await (await post(server, { files: { 'notes.md': 'x' } })).json()).toMatchObject({ error: { message: expect.stringMatching(/entry is optional when you do/) } });
  });

  it('opens the STEP named for the first entry, else the shallowest STEP, else the first viewable file', () => {
    expect(pickPrimary(['STEP/a.step', 'STEP/box.step', 'box.stl'], ['src/box.py'])).toBe('STEP/box.step');
    expect(pickPrimary(['deep/er/x.step', 'STEP/z.step', 'a.glb'], ['src/box.py'])).toBe('STEP/z.step');
    expect(pickPrimary(['src/box.py', 'meshes/b.stl', 'a.glb'], [])).toBe('a.glb');
    expect(pickPrimary(['src/box.py'], ['src/box.py'])).toBeNull();
  });

  it('returns the existing build for an identical request, and edits from a base', async () => {
    server = await testServer();
    const first = await (await post(server, { files: { 'src/box.py': boxSource(), 'src/util.py': 'X = 1\n' }, entry: 'src/box.py' })).json();
    const again = await post(server, { files: { 'src/util.py': 'X = 1\n', 'src/box.py': boxSource() }, entry: 'src/box.py' });
    expect(again.status).toBe(200);
    expect(await again.json()).toMatchObject({ id: first.id, deduped: true });

    const edit = await (await post(server, { base: first.id, files: { 'src/box.py': boxSource('box', 30) }, delete: ['src/util.py'] })).json();
    expect(edit.id).not.toBe(first.id);
    expect(edit).toMatchObject({ status: 'succeeded', base: first.id, entry: ['src/box.py'] });
    const files = await (await server.request(`/v1/builds/${edit.id}/files`)).json();
    expect(files.files.map((file: { path: string }) => file.path)).toEqual(['STEP/box.step', 'src/box.py']);
  });

  it('runs one build at a time per person', async () => {
    const hold = gate();
    server = await testServer({ sandbox: fakeSandbox(async (job) => (await hold.promise, successfulBuild(job))) });
    const first = await (await post(server, { files: { 'a.py': boxSource('a') }, entry: 'a.py' }, '')).json();
    expect(first.status).toMatch(/queued|running/);
    const second = await post(server, { files: { 'b.py': boxSource('b') }, entry: 'b.py' }, '');
    expect(second.status).toBe(409);
    expect((await second.json()).error).toMatchObject({ code: 'build_in_progress', build: first.id });
    hold.open();
    const done = await (await server.request(`/v1/builds/${first.id}?wait=5`)).json();
    expect(done.status).toBe('succeeded');
    expect((await post(server, { files: { 'b.py': boxSource('b') }, entry: 'b.py' })).status).toBe(201);
  });

  it('reports a model error with its file and line', async () => {
    server = await testServer({
      sandbox: fakeSandbox(() => ({
        result: {
          ok: false,
          exitCode: 1,
          error: { message: 'ValueError: boom', file: 'src/box.py', line: 8, kind: 'model' },
          log: '$ python src/box.py\n[python box.py] FAILED: ValueError: boom\n',
        },
      })),
    });
    const build = await (await post(server, { files: { 'src/box.py': boxSource() }, entry: 'src/box.py' })).json();
    expect(build).toMatchObject({ status: 'failed', error: { message: 'ValueError: boom', file: 'src/box.py', line: 8, kind: 'model' }, view: { available: false } });
    expect(build.log).toContain('FAILED');
    // A failed model is deterministic: the same request answers with the same failure.
    expect(await (await post(server, { files: { 'src/box.py': boxSource() }, entry: 'src/box.py' })).json()).toMatchObject({ id: build.id, deduped: true });
  });

  it('treats what a sandbox returns as untrusted', async () => {
    let attempt = 0;
    server = await testServer({
      sandbox: fakeSandbox((job) => {
        attempt += 1;
        const good = successfulBuild(job);
        if (attempt === 1) return { ...good, lies: { [`workspace/${good.result!.outputs![0]}`]: { sha256: '0'.repeat(64) } } };
        if (attempt === 2) return { rawResult: '{"ok": true, "kind": "build", "files": [{"path": "../../etc/passwd", "bytes": 1, "sha256": "' + '0'.repeat(64) + '"}]}' };
        const files = { ...good.files };
        const object = Object.keys(files).find((name) => name.startsWith('out/export/objects/'))!;
        files[object] = 'tampered';
        return { ...good, files, lies: { [object]: { sha256: sha256Hex('tampered') } } };
      }),
    });
    const changed = await (await post(server, { files: { 'a.py': boxSource('a') }, entry: 'a.py' })).json();
    expect(changed).toMatchObject({ status: 'failed', error: { kind: 'infra' } });
    expect(changed.error.message).toMatch(/changed after the job described it/);

    const escaped = await (await post(server, { files: { 'b.py': boxSource('b') }, entry: 'b.py' })).json();
    expect(escaped).toMatchObject({ status: 'failed', error: { kind: 'infra' } });
    expect(escaped.error.message).toMatch(/invalid result/);

    const exported = await (await post(server, { files: { 'c.py': boxSource('c') }, entry: 'c.py' })).json();
    expect(exported).toMatchObject({ status: 'succeeded', view: { available: false } });
    expect(exported.view.error).toMatch(/does not match its name/);
  });

  it('gives a job only what is left of the person\'s day, then refuses with the reset time', async () => {
    const sandbox = fakeSandbox((job) => ({ ...successfulBuild(job), wallMs: 90_000 }));
    server = await testServer({ sandbox, env: { CLOUD_USER_DAILY_VCPU_S: '300' } });
    await post(server, { files: { 'a.py': boxSource('a') }, entry: 'a.py' });
    expect(sandbox.jobs[0].timeoutSeconds).toBe(150); // 300 vCPU-s over 2 vCPUs
    await post(server, { files: { 'b.py': boxSource('b') }, entry: 'b.py' });
    expect(sandbox.jobs[1].timeoutSeconds).toBe(60); // 300 - 180 used
    const refused = await post(server, { files: { 'c.py': boxSource('c') }, entry: 'c.py' });
    expect(refused.status).toBe(429);
    const error = (await refused.json()).error;
    expect(error).toMatchObject({ code: 'daily_limit', cap: 'user_daily_vcpu_seconds', resetsAt: '2026-10-07T00:00:00.000Z' });
    expect(error.message).toMatch(/300 vCPU-seconds per person per day/);
    const me = await (await server.request('/v1/me')).json();
    expect(me.usage).toMatchObject({ vcpuSeconds: 360, reservedVcpuSeconds: 0, builds: 2 });
  });

  it('stops everyone when the daily budget is spent', async () => {
    server = await testServer({ env: { CLOUD_DAILY_BUDGET_USD: '0.01' } });
    const refused = await post(server, { files: { 'a.py': boxSource('a') }, entry: 'a.py' });
    expect(refused.status).toBe(429);
    expect((await refused.json()).error).toMatchObject({ code: 'budget_exhausted', cap: 'daily_budget_usd' });
    const me = await (await server.request('/v1/me')).json();
    expect(me.usage.reservedVcpuSeconds).toBe(0);
  });

  it('sweeps a build whose process died, and releases what it reserved', async () => {
    const clock = testClock();
    const hold = gate();
    server = await testServer({ clock, sandbox: fakeSandbox(async (job) => (await hold.promise, successfulBuild(job))) });
    const build = await (await post(server, { files: { 'a.py': boxSource('a') }, entry: 'a.py' }, '')).json();
    clock.advance((600 + 300 + 1) * 1000);
    expect(await server.service.sweep()).toEqual({ builds: 1, jobs: 0 });
    const swept = await (await server.request(`/v1/builds/${build.id}`)).json();
    expect(swept).toMatchObject({ status: 'failed', error: { kind: 'infra' } });
    const me = await (await server.request('/v1/me')).json();
    expect(me.usage).toMatchObject({ reservedVcpuSeconds: 0, vcpuSeconds: 1200 });
    // The late result of the dead job changes nothing.
    hold.open();
    await server.service.idle();
    expect((await (await server.request(`/v1/builds/${build.id}`)).json()).status).toBe('failed');
  });

  it('fails everything left running when a single-process server starts', async () => {
    const hold = gate();
    server = await testServer({ sandbox: fakeSandbox(async (job) => (await hold.promise, successfulBuild(job))) });
    const build = await (await post(server, { files: { 'a.py': boxSource('a') }, entry: 'a.py' }, '')).json();
    expect(await server.service.sweep({ all: true })).toEqual({ builds: 1, jobs: 0 });
    expect((await (await server.request(`/v1/builds/${build.id}`)).json()).error.message).toMatch(/server restarted/);
    hold.open();
  });

  it('refuses an oversized body before reading it', async () => {
    server = await testServer();
    const response = await server.request('/v1/builds', { method: 'POST', body: 'x'.repeat(33 * 1024 * 1024) });
    expect(response.status).toBe(413);
    expect((await response.json()).error.code).toBe('too_large');
  });
});

describe('snapshot and inspection jobs', () => {
  it('snapshots a build output and returns the image', async () => {
    const sandbox = fakeSandbox((job) => (job.kind === 'build'
      ? successfulBuild(job)
      : { result: { images: ['out/snapshot.png'] }, files: { 'out/snapshot.png': PNG } }));
    server = await testServer({ sandbox });
    const build = await (await post(server, { files: { 'src/box.py': boxSource() }, entry: 'src/box.py' })).json();
    const response = await server.request(`/v1/builds/${build.id}/snapshot?wait=5`, { method: 'POST', json: { args: ['--display', 'render'] } });
    expect(response.status).toBe(201);
    const job = await response.json();
    expect(job).toMatchObject({ kind: 'snapshot', status: 'succeeded', images: [{ type: 'image/png', url: `http://cloud.test/o/${objectKey(sha256Hex(PNG))}` }] });
    expect(sandbox.jobs[1]).toMatchObject({ kind: 'snapshot', timeoutSeconds: 180, request: { file: 'STEP/box.step', format: 'png', args: ['--display', 'render'] } });
    expect(sandbox.jobs[1].files.map((file) => file.path)).toEqual(['STEP/box.step', 'src/box.py']);

    const refused = await server.request(`/v1/builds/${build.id}/snapshot`, { method: 'POST', json: { file: 'src/box.py' } });
    expect(refused.status).toBe(400);
  });

  it('runs an inspection script and keeps its output', async () => {
    server = await testServer({
      sandbox: fakeSandbox((job) => (job.kind === 'build'
        ? successfulBuild(job)
        : { result: { ok: false, exitCode: 1, stdout: 'area 200\n', error: { message: 'RuntimeError: no', file: 'inspect.py', line: 3, kind: 'model' }, flags: { network: true } } })),
    });
    const build = await (await post(server, { files: { 'src/box.py': boxSource() }, entry: 'src/box.py' })).json();
    const job = await (await server.request(`/v1/builds/${build.id}/inspect?wait=5`, { method: 'POST', json: { code: 'print("area", 200)' } })).json();
    expect(job).toMatchObject({ kind: 'inspect', status: 'failed', exitCode: 1, stdout: 'area 200\n', error: { file: 'inspect.py', line: 3 }, flags: { network: true } });
    const again = await (await server.request(`/v1/jobs/${job.id}`)).json();
    expect(again.id).toBe(job.id);
  });
});
