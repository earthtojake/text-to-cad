import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

async function getPtyModule() {
  return import('@core/features/terminals/api/browser/pty/pty');
}

function noopConnector() {
  return {
    connect: () => () => {},
  };
}

async function createPty() {
  const { FrontendPty } = await getPtyModule();
  return new FrontendPty('retention-session', undefined, undefined, undefined, noopConnector());
}

function createVisibleContainer(): HTMLDivElement {
  const container = document.createElement('div');
  container.setAttribute('data-test-mount', 'true');
  Object.assign(container.style, {
    position: 'fixed',
    top: '0px',
    left: '0px',
    width: '900px',
    height: '500px',
  });
  document.body.appendChild(container);
  return container;
}

async function writeLines(
  terminal: { write(data: string, cb?: () => void): void },
  start: number,
  count: number
): Promise<void> {
  const chunk = Array.from({ length: count }, (_, i) => `line-${start + i}`).join('\r\n') + '\r\n';
  await new Promise<void>((resolve) => terminal.write(chunk, resolve));
}

async function until(check: () => boolean, timeoutMs = 2_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (check()) return true;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  return check();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe('terminal retention', () => {
  beforeEach(() => {
    vi.stubGlobal('electronAPI', {
      eventOn: vi.fn(() => () => {}),
      eventSend: vi.fn(),
      invoke: vi.fn(() => Promise.resolve({ success: true, data: null })),
    });

    document.documentElement.style.setProperty('--xterm-bg', '#101010');
    document.documentElement.style.setProperty('--xterm-fg', '#f0f0f0');
    document.documentElement.style.setProperty('--xterm-cursor', '#f0f0f0');
    document.documentElement.style.setProperty('--xterm-cursor-accent', '#101010');
    document.documentElement.style.setProperty('--xterm-selection-bg', '#335577');
    document.documentElement.style.setProperty('--xterm-selection-fg', '#ffffff');
  });

  afterEach(async () => {
    const { disposeAllPtys } = await getPtyModule();
    disposeAllPtys();
    document.querySelector('[data-terminal-host="true"]')?.remove();
    document.querySelector('[data-test-mount="true"]')?.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('caps task-terminal scrollback at 10k lines', async () => {
    const pty = await createPty();
    expect(pty.terminal.options.scrollback).toBe(10_000);
  });

  it('preserves buffer contents and scroll position across unmount/remount', async () => {
    const pty = await createPty();
    const container = createVisibleContainer();
    pty.mount(container);

    await writeLines(pty.terminal, 0, 300);
    const buffer = pty.terminal.buffer.active;
    expect(buffer.baseY).toBeGreaterThan(0);

    pty.terminal.scrollLines(-40);
    const scrolledViewportY = buffer.viewportY;
    expect(scrolledViewportY).toBe(buffer.baseY - 40);

    pty.unmount();
    await sleep(50);
    pty.mount(container);
    await sleep(50);

    expect(buffer.viewportY).toBe(scrolledViewportY);
    expect(buffer.getLine(5)?.translateToString(true)).toBe('line-5');
    expect(buffer.getLine(250)?.translateToString(true)).toBe('line-250');
  });

  it('pauses rendering while parked off-screen and resumes on remount', async () => {
    const pty = await createPty();
    const container = createVisibleContainer();

    let renderCount = 0;
    pty.terminal.onRender(() => {
      renderCount += 1;
    });

    pty.mount(container);
    await writeLines(pty.terminal, 0, 10);
    expect(await until(() => renderCount > 0)).toBe(true);

    pty.unmount();
    // Wait for the IntersectionObserver to observe the off-screen host and
    // pause the render service.
    const renderService = (
      pty.terminal as unknown as {
        _core: { _renderService: { _isPaused: boolean } };
      }
    )._core._renderService;
    expect(await until(() => renderService._isPaused)).toBe(true);

    renderCount = 0;
    await writeLines(pty.terminal, 10, 50);
    await sleep(150);
    expect(renderCount).toBe(0);

    pty.mount(container);
    expect(await until(() => renderCount > 0)).toBe(true);
    expect(pty.terminal.buffer.active.getLine(30)?.translateToString(true)).toBe('line-30');
  });

  it('does not leak canvases or terminal elements across repeated mount/unmount cycles', async () => {
    const pty = await createPty();
    const container = createVisibleContainer();

    pty.mount(container);
    await writeLines(pty.terminal, 0, 20);
    await sleep(50);

    const canvasCount = document.querySelectorAll('canvas').length;
    const xtermElementCount = document.querySelectorAll('.xterm').length;
    expect(xtermElementCount).toBe(1);

    for (let cycle = 0; cycle < 10; cycle += 1) {
      pty.unmount();
      pty.mount(container);
    }
    await sleep(100);

    expect(document.querySelectorAll('canvas').length).toBe(canvasCount);
    expect(document.querySelectorAll('.xterm').length).toBe(xtermElementCount);
  });
});
