export type ShellEnvPlatform = 'posix' | 'windows';

export type ShellEnvSource = 'login-shell' | 'windows' | 'process-fallback';

export type ShellEnvCapture = {
  readonly env: Record<string, string>;
  readonly source: ShellEnvSource;
  readonly capturedAt: number;
};

export type ShellEnvCaptureError = {
  readonly type: 'capture-failed';
  readonly shell?: string;
  readonly message: string;
};

export type ShellEnvPolicy = {
  readonly preserveKeys: ReadonlySet<string>;
  readonly userBinDirs: readonly string[];
  readonly platform?: ShellEnvPlatform;
};

export type ShellEnvLogger = {
  info?(message: string, metadata?: Record<string, unknown>): void;
  warn?(message: string, metadata?: Record<string, unknown>): void;
};

export type ShellEnvManager = {
  /** The operational host process environment updated for compatibility consumers. */
  readonly env: NodeJS.ProcessEnv;
  /** Awaits any initial or in-flight capture and returns an owned user-shell snapshot. */
  current(): Promise<Record<string, string>>;
  /** Returns an owned user-shell snapshot with host runtime controls excluded. */
  getUserShellEnv(): Record<string, string>;
  refresh(): Promise<void>;
};

export const SHELL_ENV_CAPTURE_GUARD: Record<string, string> = {
  DISABLE_AUTO_UPDATE: 'true',
  ZSH_TMUX_AUTOSTART: 'false',
  ZSH_TMUX_AUTOSTARTED: 'true',
};

export const DEFAULT_SHELL_ENV_PRESERVE_KEYS = new Set(['NODE_ENV']);
