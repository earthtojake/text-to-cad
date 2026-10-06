// The local provider: a temporary directory and a child process on THIS machine.
//
// It has no isolation at all: the uploaded code runs with the server's user, files and
// network. It exists so the whole flow runs on a laptop and in tests, and it refuses to
// run in production unless CLOUD_ALLOW_LOCAL_SANDBOX=1 says someone accepted that.
import { spawn } from 'node:child_process';
import { lstat, mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import {
  SandboxError,
  checkCollected,
  filesToCollect,
  isSafeRelativePath,
  lineSplitter,
  parseRunnerLine,
  parseRunnerResult,
  requestJson,
  textTail,
  type SandboxJob,
  type SandboxProvider,
  type SandboxRunOptions,
} from './protocol.ts';

export interface LocalSandboxOptions {
  python: string;
  runner: string;
  jobsDir?: string;
  production?: boolean;
  allowInProduction?: boolean;
  /** Seconds past the job's own timeout before the process group is killed. */
  killGraceSeconds?: number;
  env?: NodeJS.ProcessEnv;
  keepJobs?: boolean;
}

/** Environment the runner inherits: enough to find Python, Node and the snapshot browser, no secrets. */
function runnerEnv(source: NodeJS.ProcessEnv): Record<string, string> {
  const keep = ['PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'TMPDIR', 'TEMP', 'TMP', 'SYSTEMROOT', 'PLAYWRIGHT_BROWSERS_PATH', 'CADGEN_NODE', 'NODE'];
  const env: Record<string, string> = {};
  for (const name of keep) if (source[name]) env[name] = source[name] as string;
  env.LANG ??= 'C.UTF-8';
  return env;
}

export function createLocalSandbox(options: LocalSandboxOptions): SandboxProvider {
  return {
    kind: 'local',
    async run(job: SandboxJob, { onEvent, signal }: SandboxRunOptions = {}) {
      if (options.production && !options.allowInProduction) {
        throw new SandboxError('the local sandbox runs code without isolation and is refused in production (CLOUD_ALLOW_LOCAL_SANDBOX=1 overrides)');
      }
      const base = options.jobsDir ?? tmpdir();
      await mkdir(base, { recursive: true });
      const dir = await realpath(await mkdtemp(path.join(base, 't2c-job-')));
      const started = Date.now();
      try {
        const workspace = path.join(dir, 'workspace');
        await mkdir(workspace, { recursive: true });
        await writeFile(path.join(dir, 'request.json'), requestJson(job));
        for (const file of job.files) {
          if (!isSafeRelativePath(file.path)) throw new SandboxError(`unsafe input path ${file.path}`);
          const target = path.join(workspace, ...file.path.split('/'));
          await mkdir(path.dirname(target), { recursive: true });
          await writeFile(target, file.bytes);
        }

        const stderr = textTail();
        const child = spawn(options.python, [options.runner, dir], {
          cwd: workspace,
          env: runnerEnv(options.env ?? process.env),
          detached: true, // its own process group, so a timeout kills everything it started
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        const killGroup = () => {
          if (child.pid === undefined) return;
          try {
            process.kill(-child.pid, 'SIGKILL');
          } catch {
            try {
              child.kill('SIGKILL');
            } catch {
              // already gone
            }
          }
        };
        const lines = lineSplitter((line) => {
          const event = parseRunnerLine(line);
          if (event) onEvent?.(event);
        });
        child.stdout.setEncoding('utf8').on('data', (chunk: string) => lines.push(chunk));
        child.stderr.setEncoding('utf8').on('data', (chunk: string) => stderr.push(chunk));
        let killedFor: string | null = null;
        const timer = setTimeout(() => {
          killedFor = 'timeout';
          killGroup();
        }, (job.timeoutSeconds + (options.killGraceSeconds ?? 30)) * 1000);
        const onAbort = () => {
          killedFor = 'aborted';
          killGroup();
        };
        signal?.addEventListener('abort', onAbort, { once: true });
        const closed = new Promise<void>((resolve) => child.once('close', () => resolve()));
        const exitCode = await new Promise<number | null>((resolve, reject) => {
          child.once('error', reject);
          child.once('exit', (code) => resolve(code));
        }).finally(() => {
          clearTimeout(timer);
          signal?.removeEventListener('abort', onAbort);
          killGroup(); // anything the job left running in its group
        });
        // Let the last lines drain; a descendant that escaped the group cannot hold us here.
        await Promise.race([closed, new Promise((resolve) => setTimeout(resolve, 2000))]);
        lines.end();

        let resultText: string;
        try {
          resultText = await readFile(path.join(dir, 'result.json'), 'utf8');
        } catch {
          const why = killedFor === 'timeout' ? `it ran past its ${job.timeoutSeconds} s limit and was killed` : `the runner exited with code ${exitCode}`;
          throw new SandboxError(`the job left no result: ${why}`, stderr.value);
        }
        const result = parseRunnerResult(resultText);
        const files = new Map<string, Uint8Array>();
        for (const file of filesToCollect(result, job.limits)) {
          const target = path.join(dir, ...file.path.split('/'));
          const info = await lstat(target).catch(() => null);
          if (!info || !info.isFile()) throw new SandboxError(`${file.path} is not a regular file`);
          const real = await realpath(target);
          if (!real.startsWith(dir + path.sep)) throw new SandboxError(`${file.path} resolves outside the job`);
          files.set(file.path, checkCollected(file, new Uint8Array(await readFile(real))));
        }
        return { result, files, usage: { wallMs: Date.now() - started } };
      } finally {
        if (!options.keepJobs) await rm(dir, { recursive: true, force: true }).catch(() => {});
      }
    },
  };
}
