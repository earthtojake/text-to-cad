/**
 * One-shot capture of the user's first "real" terminal message.
 *
 * Accumulates keystrokes, strips ANSI escapes, handles backspace,
 * and fires the `onCapture` callback once when a confirmed submit
 * passes validation. After firing, the buffer disables itself.
 */

/** Strings that look like non-task-related input (confirmations, slash commands, etc.) */
const SKIP_PATTERNS = [
  /^\//,
  /^y(es)?$/i,
  /^n(o)?$/i,
  /^ok$/i,
  /^q(uit)?$/i,
  /^exit$/i,
  /^help$/i,
  /^\d+$/,
];

const MIN_MESSAGE_LENGTH = 2;
const HAS_ALPHA = /[A-Za-z]/;

type SanitizerMode = 'normal' | 'escape' | 'csi' | 'osc' | 'osc-escape' | 'ss3';
type InputAction =
  | { type: 'insert'; text: string }
  | { type: 'submit' }
  | { type: 'backspace' }
  | { type: 'delete' }
  | { type: 'kill-line' }
  | { type: 'move-home' }
  | { type: 'move-end' }
  | { type: 'move-left'; count: number }
  | { type: 'move-right'; count: number };

const MAX_CSI_PAYLOAD_LENGTH = 256;

function isCsiFinalByte(ch: string): boolean {
  return ch >= '@' && ch <= '~';
}

class AnsiDecoder {
  private mode: SanitizerMode = 'normal';
  private csiBuffer = '';

  private readCount(payload: string): number {
    const raw = payload.split(';', 1)[0] ?? '';
    const value = Number.parseInt(raw, 10);
    if (!Number.isFinite(value) || value <= 0) return 1;
    return value;
  }

  private decodePlainChar(ch: string): InputAction[] {
    if (ch === '\r' || ch === '\n') return [{ type: 'submit' }];
    if (ch === '\x7f' || ch === '\b') return [{ type: 'backspace' }];
    if (ch === '\x04') return [{ type: 'delete' }];
    if (ch === '\x15') return [{ type: 'kill-line' }];
    if (ch === '\x01') return [{ type: 'move-home' }];
    if (ch === '\x05') return [{ type: 'move-end' }];
    if (ch === '\x02') return [{ type: 'move-left', count: 1 }];
    if (ch === '\x06') return [{ type: 'move-right', count: 1 }];
    if (ch.charCodeAt(0) >= 32) return [{ type: 'insert', text: ch }];
    return [];
  }

  private decodeCsi(payload: string, finalByte: string): InputAction[] {
    if (finalByte === 'u') {
      const codepoint = Number.parseInt(payload.split(';', 1)[0] ?? '', 10);
      if (codepoint === 8 || codepoint === 127) return [{ type: 'backspace' }];
      if (codepoint === 13) return [{ type: 'submit' }];
      if (codepoint === 21) return [{ type: 'kill-line' }];
      if (codepoint === 1) return [{ type: 'move-home' }];
      if (codepoint === 5) return [{ type: 'move-end' }];
      return [];
    }

    if (finalByte === 'D') return [{ type: 'move-left', count: this.readCount(payload) }];
    if (finalByte === 'C') return [{ type: 'move-right', count: this.readCount(payload) }];
    if (finalByte === 'H') return [{ type: 'move-home' }];
    if (finalByte === 'F') return [{ type: 'move-end' }];

    if (finalByte === '~') {
      const code = Number.parseInt(payload.split(';', 1)[0] ?? '', 10);
      if (code === 3) return [{ type: 'delete' }];
      if (code === 1 || code === 7) return [{ type: 'move-home' }];
      if (code === 4 || code === 8) return [{ type: 'move-end' }];
    }

    return [];
  }

  private decodeSs3(finalByte: string): InputAction[] {
    if (finalByte === 'D') return [{ type: 'move-left', count: 1 }];
    if (finalByte === 'C') return [{ type: 'move-right', count: 1 }];
    if (finalByte === 'H') return [{ type: 'move-home' }];
    if (finalByte === 'F') return [{ type: 'move-end' }];
    return [];
  }

  feed(chunk: string): InputAction[] {
    const actions: InputAction[] = [];

    for (const ch of chunk) {
      switch (this.mode) {
        case 'normal':
          if (ch === '\x1b') {
            this.mode = 'escape';
            continue;
          }
          actions.push(...this.decodePlainChar(ch));
          continue;
        case 'escape':
          if (ch === '[') {
            this.mode = 'csi';
            this.csiBuffer = '';
            continue;
          }
          if (ch === ']') {
            this.mode = 'osc';
            continue;
          }
          if (ch === 'O') {
            this.mode = 'ss3';
            continue;
          }
          this.mode = 'normal';
          if (ch === '\x1b') {
            this.mode = 'escape';
            continue;
          }
          actions.push(...this.decodePlainChar(ch));
          continue;
        case 'csi':
          if (isCsiFinalByte(ch)) {
            actions.push(...this.decodeCsi(this.csiBuffer, ch));
            this.mode = 'normal';
            this.csiBuffer = '';
            continue;
          }
          if (this.csiBuffer.length < MAX_CSI_PAYLOAD_LENGTH) {
            this.csiBuffer += ch;
          }
          continue;
        case 'osc':
          if (ch === '\x07') {
            this.mode = 'normal';
            continue;
          }
          if (ch === '\x1b') {
            this.mode = 'osc-escape';
          }
          continue;
        case 'osc-escape':
          if (ch === '\\') {
            this.mode = 'normal';
            continue;
          }
          this.mode = ch === '\x1b' ? 'osc-escape' : 'osc';
          continue;
        case 'ss3':
          actions.push(...this.decodeSs3(ch));
          this.mode = 'normal';
          continue;
      }
    }

    return actions;
  }
}

class LineEditor {
  private lineBuffer = '';
  private cursor = 0;

  apply(actions: InputAction[]): string[] {
    const submitted: string[] = [];

    for (const action of actions) {
      switch (action.type) {
        case 'insert':
          this.lineBuffer =
            this.lineBuffer.slice(0, this.cursor) +
            action.text +
            this.lineBuffer.slice(this.cursor);
          this.cursor += action.text.length;
          break;
        case 'submit': {
          const message = this.lineBuffer.trim();
          if (message) submitted.push(message);
          this.lineBuffer = '';
          this.cursor = 0;
          break;
        }
        case 'backspace':
          if (this.cursor > 0) {
            this.lineBuffer =
              this.lineBuffer.slice(0, this.cursor - 1) + this.lineBuffer.slice(this.cursor);
            this.cursor -= 1;
          }
          break;
        case 'delete':
          if (this.cursor < this.lineBuffer.length) {
            this.lineBuffer =
              this.lineBuffer.slice(0, this.cursor) + this.lineBuffer.slice(this.cursor + 1);
          }
          break;
        case 'kill-line':
          this.clearLine();
          break;
        case 'move-home':
          this.cursor = 0;
          break;
        case 'move-end':
          this.cursor = this.lineBuffer.length;
          break;
        case 'move-left':
          this.cursor = Math.max(0, this.cursor - action.count);
          break;
        case 'move-right':
          this.cursor = Math.min(this.lineBuffer.length, this.cursor + action.count);
          break;
      }
    }

    return submitted;
  }

  clearLine(): void {
    this.lineBuffer = '';
    this.cursor = 0;
  }
}

export class SubmittedInputBuffer {
  private readonly decoder = new AnsiDecoder();
  private readonly editor = new LineEditor();

  feed(data: string): string[] {
    return this.editor.apply(this.decoder.feed(data));
  }

  clearLine(): void {
    this.editor.clearLine();
  }
}

/** Returns true if the message looks like a real task description. */
export function isRealTaskInput(message: string): boolean {
  const trimmed = message.trim();
  if (!trimmed || trimmed.length < MIN_MESSAGE_LENGTH) return false;
  if (!HAS_ALPHA.test(trimmed)) return false;
  for (const pattern of SKIP_PATTERNS) {
    if (pattern.test(trimmed)) return false;
  }
  return true;
}

export class TerminalInputBuffer {
  private readonly submittedInput = new SubmittedInputBuffer();
  private pendingMessage: string | null = null;
  private captured = false;
  private readonly onCapture: (message: string) => void;

  constructor(onCapture: (message: string) => void) {
    this.onCapture = onCapture;
  }

  /** Feed raw terminal input data (keystrokes). */
  feed(data: string): void {
    if (this.captured) return;
    const submittedMessages = this.submittedInput.feed(data);
    if (submittedMessages.length > 0) {
      this.pendingMessage = submittedMessages.at(-1) ?? null;
    }
  }

  /**
   * Called when PTY output indicates the agent is "busy" (processing).
   * If we have a pending message that passes validation, fire the callback.
   */
  confirmSubmit(): void {
    if (this.captured) return;
    if (!this.pendingMessage) return;

    if (isRealTaskInput(this.pendingMessage)) {
      this.captured = true;
      const message = this.pendingMessage;
      this.pendingMessage = null;
      this.submittedInput.clearLine();
      this.onCapture(message);
    } else {
      // Not a real task input — discard and keep listening
      this.pendingMessage = null;
    }
  }

  /** Whether the buffer has already fired its callback. */
  get isComplete(): boolean {
    return this.captured;
  }
}
