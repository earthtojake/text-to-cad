import type { LogSink } from '@emdash/wire/live';
import type { LiveLogSnapshotData } from '@emdash/wire/rpc';
import type { Terminal } from '@xterm/xterm';

type XtermLogTerminal = Pick<Terminal, 'reset' | 'write'>;

const TRUNCATED_NOTICE = '\r\n[output truncated]\r\n';

export function createXtermLogSink(terminal: XtermLogTerminal): LogSink {
  return {
    reset(data: LiveLogSnapshotData) {
      terminal.reset();
      if (data.truncated) terminal.write(TRUNCATED_NOTICE);
      if (data.text.length > 0) terminal.write(data.text);
    },
    append(chunk) {
      terminal.write(chunk);
    },
  };
}
