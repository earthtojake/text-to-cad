export type PtySignal =
  | 'SIGHUP' // 1  - hangup / PTY master closed (common when emdash window closes)
  | 'SIGINT' // 2  - Ctrl+C (user interrupt)
  | 'SIGQUIT' // 3  - Ctrl+\ (quit + core dump)
  | 'SIGILL' // 4  - illegal instruction
  | 'SIGTRAP' // 5  - trace / breakpoint trap
  | 'SIGABRT' // 6  - abort() called
  | 'SIGBUS' // 7  - bus error (bad memory access)
  | 'SIGFPE' // 8  - floating-point exception
  | 'SIGKILL' // 9  - force kill (cannot be caught or ignored)
  | 'SIGUSR1' // 10 - user-defined signal 1
  | 'SIGSEGV' // 11 - invalid memory reference (segfault)
  | 'SIGUSR2' // 12 - user-defined signal 2
  | 'SIGPIPE' // 13 - write to closed pipe (agent output discarded)
  | 'SIGALRM' // 14 - alarm timer expired
  | 'SIGTERM' // 15 - graceful termination request (default `kill` signal)
  | 'SIGCHLD' // 17 - child process state changed
  | 'SIGCONT' // 18 - continue a stopped process
  | 'SIGSTOP' // 19 - stop process (cannot be caught or ignored)
  | 'SIGTSTP' // 20 - Ctrl+Z (stop from terminal)
  | 'SIGTTIN' // 21 - background process attempted terminal read
  | 'SIGTTOU' // 22 - background process attempted terminal write
  | 'SIGURG' // 23 - urgent data available on socket
  | 'SIGXCPU' // 24 - CPU time limit exceeded
  | 'SIGXFSZ' // 25 - file size limit exceeded
  | 'SIGVTALRM' // 26 - virtual timer expired
  | 'SIGPROF' // 27 - profiling timer expired
  | 'SIGWINCH' // 28 - terminal window resized (rarely surfaces as an exit signal)
  | 'SIGPWR' // 30 - power failure
  | 'SIGSYS'; // 31 - bad system call

export const SIGNAL_BY_NUMBER: Readonly<Record<number, PtySignal>> = {
  1: 'SIGHUP',
  2: 'SIGINT',
  3: 'SIGQUIT',
  4: 'SIGILL',
  5: 'SIGTRAP',
  6: 'SIGABRT',
  7: 'SIGBUS',
  8: 'SIGFPE',
  9: 'SIGKILL',
  10: 'SIGUSR1',
  11: 'SIGSEGV',
  12: 'SIGUSR2',
  13: 'SIGPIPE',
  14: 'SIGALRM',
  15: 'SIGTERM',
  17: 'SIGCHLD',
  18: 'SIGCONT',
  19: 'SIGSTOP',
  20: 'SIGTSTP',
  21: 'SIGTTIN',
  22: 'SIGTTOU',
  23: 'SIGURG',
  24: 'SIGXCPU',
  25: 'SIGXFSZ',
  26: 'SIGVTALRM',
  27: 'SIGPROF',
  28: 'SIGWINCH',
  30: 'SIGPWR',
  31: 'SIGSYS',
};

const KNOWN_SIGNAL_NAMES = new Set<string>(Object.values(SIGNAL_BY_NUMBER));

export function normalizeSignal(raw: number | string | null | undefined): PtySignal | undefined {
  if (raw == null) return undefined;
  if (typeof raw === 'number') return SIGNAL_BY_NUMBER[raw];
  const canonical = raw.startsWith('SIG') ? raw : `SIG${raw}`;
  return KNOWN_SIGNAL_NAMES.has(canonical) ? (canonical as PtySignal) : undefined;
}

export const EXIT_CODE_MEANINGS: Readonly<Record<number, string>> = {
  0: 'Success',
  1: 'General error',
  2: 'Misuse of shell built-in',
  126: 'Command not executable (permission denied)',
  127: 'Command not found',
  128: 'Invalid argument to exit()',
  129: 'Terminated by SIGHUP (PTY closed)',
  130: 'Terminated by SIGINT (Ctrl+C)',
  131: 'Terminated by SIGQUIT (Ctrl+\\)',
  134: 'Terminated by SIGABRT',
  137: 'Killed by SIGKILL (force kill / OOM)',
  139: 'Terminated by SIGSEGV (segfault)',
  141: 'Terminated by SIGPIPE (broken pipe)',
  143: 'Terminated by SIGTERM (graceful stop)',
};

export function getExitCodeMeaning(exitCode: number): string {
  const knownExitCode = EXIT_CODE_MEANINGS[exitCode];
  if (knownExitCode) {
    return knownExitCode;
  }
  if (signalFromExitCode(exitCode)) {
    return `Terminated by ${signalFromExitCode(exitCode)}`;
  }
  return `Unknown exit code: ${exitCode}`;
}

function signalFromExitCode(exitCode: number): PtySignal | undefined {
  if (exitCode > 128 && exitCode <= 159) {
    return SIGNAL_BY_NUMBER[exitCode - 128];
  }
  return undefined;
}
