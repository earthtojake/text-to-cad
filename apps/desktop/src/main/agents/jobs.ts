/**
 * Long-running agent jobs — an install script, a login flow — run in a pty
 * so the user sees exactly what a terminal would show (progress bars, the
 * device-code URL, a password prompt) and can type into it.
 *
 * The pty factory is injected: main hands in node-pty, the tests hand in a
 * fake. Nothing else here knows which it got.
 */
import { randomUUID } from "node:crypto";

import type { AgentJobOutput } from "../../shared/agents";
import type { Env } from "./shell-env";

/** The slice of a node-pty `IPty` a job uses. */
export interface JobPty {
  readonly pid: number;
  write(data: string): void;
  kill(signal?: string): void;
  onData(listener: (data: string) => void): { dispose(): void };
  onExit(listener: (event: { exitCode: number; signal?: number }) => void): { dispose(): void };
}

export type SpawnJobPty = (options: {
  file: string;
  args: string[];
  cwd: string;
  env: Env;
}) => JobPty;

export type Job = {
  id: string;
  agentId: string;
  kind: AgentJobOutput["kind"];
  pty: JobPty;
  exitCode: number | null;
};

export class JobRunner {
  private readonly jobs = new Map<string, Job>();

  constructor(
    private readonly spawn: SpawnJobPty,
    private readonly onOutput: (chunk: AgentJobOutput) => void,
    private readonly onExit: (job: Job) => void = () => {},
  ) {}

  start(
    agentId: string,
    kind: AgentJobOutput["kind"],
    command: { file: string; args: string[]; cwd: string; env: Env },
  ): Job {
    const id = randomUUID();
    const pty = this.spawn(command);
    const job: Job = { id, agentId, kind, pty, exitCode: null };
    this.jobs.set(id, job);
    pty.onData((data) => this.onOutput({ jobId: id, agentId, kind, data, exitCode: null }));
    pty.onExit(({ exitCode }) => {
      job.exitCode = exitCode;
      this.jobs.delete(id);
      this.onOutput({ jobId: id, agentId, kind, data: "", exitCode });
      this.onExit(job);
    });
    return job;
  }

  write(jobId: string, data: string): void {
    this.jobs.get(jobId)?.pty.write(data);
  }

  cancel(jobId: string): void {
    this.jobs.get(jobId)?.pty.kill();
  }

  /** Kill everything — on quit. */
  cancelAll(): void {
    for (const job of this.jobs.values()) {
      job.pty.kill();
    }
  }
}
