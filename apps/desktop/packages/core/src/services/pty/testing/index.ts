import type { PtyExitInfo, PtyProcess, PtySpawnSpec, PtySpawner } from '#services/pty/api';

export interface FakePtyOptions {
  /**
   * Real PTY processes exit shortly after kill, so the fake mirrors that by
   * default. Disable to assert on kill calls without the exit side effect.
   */
  exitOnKill?: boolean;
}

/**
 * The one shared PTY process fake for runtime tests (spec:
 * conversation-lifecycle-chassis, testing section). Records writes, resizes,
 * and kills; exposes emitData/emitExit to script output and exit.
 */
export class FakePtyProcess implements PtyProcess {
  readonly writes: string[] = [];
  readonly resizes: Array<{ cols: number; rows: number }> = [];
  killCount = 0;
  private readonly dataHandlers: Array<(data: string) => void> = [];
  private readonly exitHandlers: Array<(info: PtyExitInfo) => void> = [];
  private exited = false;

  constructor(
    private readonly pid: number,
    private readonly options: FakePtyOptions = {}
  ) {}

  write(data: string): void {
    this.writes.push(data);
  }

  resize(cols: number, rows: number): void {
    this.resizes.push({ cols, rows });
  }

  kill(): void {
    this.killCount += 1;
    if (this.options.exitOnKill ?? true) {
      this.emitExit({ exitCode: null, signal: 'SIGTERM' });
    }
  }

  onData(handler: (data: string) => void): void {
    this.dataHandlers.push(handler);
  }

  onExit(handler: (info: PtyExitInfo) => void): void {
    this.exitHandlers.push(handler);
  }

  getPid(): number {
    return this.pid;
  }

  get isExited(): boolean {
    return this.exited;
  }

  emitData(data: string): void {
    for (const handler of this.dataHandlers) handler(data);
  }

  emitExit(info: PtyExitInfo = { exitCode: 0, signal: null }): void {
    if (this.exited) return;
    this.exited = true;
    for (const handler of this.exitHandlers) handler(info);
  }
}

export class FakePtySpawner implements PtySpawner {
  readonly specs: PtySpawnSpec[] = [];
  readonly processes: FakePtyProcess[] = [];
  /** When set, the next spawn attempts throw instead of creating a process. */
  failWith: Error | null = null;

  constructor(private readonly options: FakePtyOptions = {}) {}

  spawn(spec: PtySpawnSpec): PtyProcess {
    if (this.failWith) throw this.failWith;
    this.specs.push(spec);
    const process = new FakePtyProcess(this.processes.length + 1, this.options);
    this.processes.push(process);
    return process;
  }
}
