import { describe, expect, it } from 'vitest';
import { createXtermLogSink } from '@core/features/terminals/api/browser/pty/xterm-log-sink';

describe('createXtermLogSink', () => {
  it('resets xterm and writes retained text', () => {
    const terminal = new FakeTerminal();
    const sink = createXtermLogSink(terminal);

    sink.reset({ baseOffset: 0, text: 'hello', truncated: false });
    sink.append('\nworld');

    expect(terminal.events).toEqual(['reset', 'write:hello', 'write:\nworld']);
  });

  it('adds a truncation notice before retained text', () => {
    const terminal = new FakeTerminal();
    const sink = createXtermLogSink(terminal);

    sink.reset({ baseOffset: 1024, text: 'tail', truncated: true });

    expect(terminal.events).toEqual(['reset', 'write:\r\n[output truncated]\r\n', 'write:tail']);
  });
});

class FakeTerminal {
  readonly events: string[] = [];

  reset(): void {
    this.events.push('reset');
  }

  write(data: string): void {
    this.events.push(`write:${data}`);
  }
}
