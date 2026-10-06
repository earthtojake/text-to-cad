// The production provider: one Vercel Sandbox (a Firecracker microVM) per job, started from
// the snapshot scripts/cloud/prepare-sandbox.mjs made (Python, the released cadgen, its
// headless browser and the runner). The VM has no network, holds no credentials, runs one
// job and is stopped whatever happens. Files go in and out through the SDK's file API.
import type { Sandbox } from '@vercel/sandbox';
import {
  SandboxError,
  checkCollected,
  filesToCollect,
  lineSplitter,
  parseRunnerLine,
  parseRunnerResult,
  requestJson,
  textTail,
  type SandboxJob,
  type SandboxProvider,
  type SandboxRunOptions,
} from './protocol.ts';

type CreateParams = Parameters<typeof Sandbox.create>[0];
type SandboxLike = Pick<Sandbox, 'writeFiles' | 'runCommand' | 'readFileToBuffer' | 'stop' | 'delete'>;

export interface VercelSandboxOptions {
  snapshotId: string;
  python: string;
  runner: string;
  jobRoot: string;
  credentials?: { teamId: string; projectId: string; token: string };
  /** Seconds the VM may outlive the job's own timeout (boot, uploads, collection). */
  vmGraceSeconds?: number;
  /** Injected in tests; defaults to `Sandbox.create` from @vercel/sandbox. */
  create?: (params: CreateParams) => Promise<SandboxLike>;
}

const WRITE_BATCH_BYTES = 8 * 1024 * 1024;

export function createVercelSandbox(options: VercelSandboxOptions): SandboxProvider {
  const create = options.create ?? (async (params: CreateParams) => {
    const { Sandbox } = await import('@vercel/sandbox');
    return Sandbox.create(params);
  });
  const root = options.jobRoot.replace(/\/+$/, '');
  return {
    kind: 'vercel',
    async run(job: SandboxJob, { onEvent, signal }: SandboxRunOptions = {}) {
      const started = Date.now();
      const grace = options.vmGraceSeconds ?? 180;
      let sandbox: SandboxLike;
      try {
        sandbox = await create({
          source: { type: 'snapshot', snapshotId: options.snapshotId },
          resources: { vcpus: job.vcpus },
          timeout: (job.timeoutSeconds + grace) * 1000,
          networkPolicy: 'deny-all',
          persistent: false,
          tags: { app: 'text-to-cad-cloud', kind: job.kind },
          signal,
          ...(options.credentials ?? {}),
        } as CreateParams);
      } catch (error) {
        throw new SandboxError(`could not start a sandbox: ${(error as Error).message}`);
      }
      let activeCpuMs: number | undefined;
      let outcome: { result: ReturnType<typeof parseRunnerResult>; files: Map<string, Uint8Array> };
      try {
        const inputs = [
          { path: `${root}/request.json`, content: new TextEncoder().encode(requestJson(job)) },
          ...job.files.map((file) => ({ path: `${root}/workspace/${file.path}`, content: file.bytes })),
        ];
        let batch: typeof inputs = [];
        let batchBytes = 0;
        for (const input of inputs) {
          if (batch.length && batchBytes + input.content.byteLength > WRITE_BATCH_BYTES) {
            await sandbox.writeFiles(batch, { signal });
            batch = [];
            batchBytes = 0;
          }
          batch.push(input);
          batchBytes += input.content.byteLength;
        }
        if (batch.length) await sandbox.writeFiles(batch, { signal });

        const stderr = textTail();
        const lines = lineSplitter((line) => {
          const event = parseRunnerLine(line);
          if (event) onEvent?.(event);
        });
        const command = await sandbox.runCommand({
          cmd: options.python,
          args: [options.runner, root],
          cwd: `${root}/workspace`,
          detached: true,
          timeoutMs: (job.timeoutSeconds + 30) * 1000,
          signal,
        });
        for await (const log of command.logs({ signal })) {
          if (log.stream === 'stdout') lines.push(log.data);
          else stderr.push(log.data);
        }
        lines.end();
        const finished = await command.wait({ signal });

        const resultBytes = await sandbox.readFileToBuffer({ path: `${root}/result.json` }, { signal });
        if (!resultBytes) throw new SandboxError(`the job left no result (runner exit code ${finished.exitCode})`, stderr.value);
        const result = parseRunnerResult(new TextDecoder().decode(resultBytes));
        const files = new Map<string, Uint8Array>();
        for (const file of filesToCollect(result, job.limits)) {
          const bytes = await sandbox.readFileToBuffer({ path: `${root}/${file.path}` }, { signal });
          if (!bytes) throw new SandboxError(`${file.path} is missing`);
          files.set(file.path, checkCollected(file, new Uint8Array(bytes)));
        }
        outcome = { result, files };
      } finally {
        // Always stopped, and deleted so a single-use VM leaves nothing behind.
        try {
          const stopped = await sandbox.stop();
          activeCpuMs = stopped?.activeCpuDurationMs;
        } catch {
          // a VM that already ended is fine
        }
        await sandbox.delete().catch(() => {});
      }
      return { ...outcome, usage: { wallMs: Date.now() - started, activeCpuMs } };
    },
  };
}
