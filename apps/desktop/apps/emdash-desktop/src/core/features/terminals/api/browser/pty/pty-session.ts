import { makeAutoObservable, onBecomeObserved, runInAction } from 'mobx';
import {
  FrontendPty,
  type FrontendPtyConnector,
} from '@core/features/terminals/api/browser/pty/pty';

export type PtySessionStatus = 'disconnected' | 'connecting' | 'ready';

type PtySessionPrepareResult = void | false;

export class PtySession {
  pty: FrontendPty | null = null;
  status: PtySessionStatus = 'disconnected';
  private connectPromise: Promise<void> | null = null;
  private version = 0;
  private connectionRequested = false;

  constructor(
    readonly sessionId: string,
    private readonly prepare?: () => Promise<PtySessionPrepareResult>,
    private readonly onOpenFile?: (filePath: string) => void,
    private readonly onOpenExternal?: (filePath: string) => void,
    private readonly connector: FrontendPtyConnector = noopConnector(),
    private readonly canConnect: () => boolean = () => true
  ) {
    makeAutoObservable(this, {
      pty: false,
    });
    // Lazy connect: auto-connects the first time any observer reads status.
    // Sessions are created at data-load time without connecting; this fires
    // when the session is first rendered as the active conversation or terminal.
    onBecomeObserved(this, 'status', () => {
      if (this.status === 'disconnected') void this.connect();
    });
  }

  async connect() {
    this.connectionRequested = true;
    if (!this.canConnect()) return;
    if (this.pty) return;
    if (this.connectPromise) return this.connectPromise;

    const version = this.version;
    this.connectPromise = (async () => {
      const prepared = await this.prepare?.();
      if (prepared === false) return;
      if (version !== this.version) return;
      if (this.pty) return;
      const pty = new FrontendPty(
        this.sessionId,
        undefined,
        this.onOpenFile,
        this.onOpenExternal,
        this.connector
      );
      runInAction(() => {
        this.pty = pty;
        this.status = 'connecting';
      });
      await pty.connect();
      if (version !== this.version || this.pty !== pty) return;
      runInAction(() => {
        this.status = 'ready';
      });
    })().finally(() => {
      this.connectPromise = null;
    });

    return this.connectPromise;
  }

  resumeIfRequested(): void {
    if (this.connectionRequested && this.status === 'disconnected') void this.connect();
  }

  dispose() {
    this.version++;
    this.pty?.dispose();
    runInAction(() => {
      this.pty = null;
      this.status = 'disconnected';
    });
  }

  destroy() {
    this.connectionRequested = false;
    this.dispose();
  }
}

function noopConnector(): FrontendPtyConnector {
  return {
    connect() {
      return () => {};
    },
  };
}
