import type { LiveLogSource } from '@emdash/wire/live';
import { PtySession, type PtySessionOptions } from './pty-session';
import type { PtySpawnSpec, PtySpawner } from './types';

export interface PtyRegistryOptions {
  onSessionChanged?: (key: string, session: PtySession | null) => void;
}

export class PtyRegistry {
  private readonly sessions = new Map<string, PtySession>();

  constructor(
    private readonly spawner: PtySpawner,
    private readonly options: PtyRegistryOptions = {}
  ) {}

  async create(
    key: string,
    spec: PtySpawnSpec,
    options: PtySessionOptions & { replaceExisting?: boolean } = {}
  ): Promise<PtySession> {
    if (options.replaceExisting ?? true) {
      this.dispose(key);
    } else if (this.sessions.has(key)) {
      throw new Error(`PTY session '${key}' already exists`);
    }

    const proc = await this.spawner.spawn(spec);
    options.onProcess?.(proc);
    const session = new PtySession(key, spec, proc, {
      ...options,
      onExit: (info) => {
        options.onExit?.(info);
        this.options.onSessionChanged?.(key, session);
      },
      onStateChange: () => {
        options.onStateChange?.();
        this.options.onSessionChanged?.(key, session);
      },
    });
    this.sessions.set(key, session);
    this.options.onSessionChanged?.(key, session);
    return session;
  }

  get(key: string): PtySession | undefined {
    return this.sessions.get(key);
  }

  getLog(key: string): LiveLogSource | null {
    return this.sessions.get(key)?.output ?? null;
  }

  write(key: string, data: string): boolean {
    const session = this.sessions.get(key);
    if (!session) return false;
    session.write(data);
    return true;
  }

  resize(key: string, cols: number, rows: number): boolean {
    const session = this.sessions.get(key);
    if (!session) return false;
    session.resize(cols, rows);
    return true;
  }

  kill(key: string): boolean {
    const session = this.sessions.get(key);
    if (!session) return false;
    session.kill();
    return true;
  }

  dispose(key: string): boolean {
    const session = this.sessions.get(key);
    if (!session) return false;
    session.dispose();
    this.sessions.delete(key);
    this.options.onSessionChanged?.(key, null);
    return true;
  }

  killAll(): void {
    for (const key of [...this.sessions.keys()]) {
      this.dispose(key);
    }
  }
}
