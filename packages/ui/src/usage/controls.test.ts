import { afterEach, expect, it, vi } from 'vitest';
import { BURST_MS, CONTROLS, REPORT_MS, createControlUsage } from './controls.js';

// A page whose visibility a test sets, with the counter's timer on a clock the test moves.
function page() {
  let hidden = false;
  const document = new EventTarget() as EventTarget & { visibilityState: string };
  Object.defineProperty(document, 'visibilityState', { get: () => (hidden ? 'hidden' : 'visible') });
  const window = new EventTarget() as EventTarget & { setInterval: typeof setInterval; clearInterval: typeof clearInterval };
  window.setInterval = ((handler: () => void, ms: number) => setInterval(handler, ms)) as typeof setInterval;
  window.clearInterval = ((id: number) => clearInterval(id)) as typeof clearInterval;
  return { page: { document, window } as unknown as { document: Document; window: Window },
    hide(value: boolean) { hidden = value; document.dispatchEvent(new Event('visibilitychange')); } };
}
function counter() {
  let now = 1_000_000;
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const view = page();
  const usage = createControlUsage({ report: counts => reports.push(counts), now: () => now, page: view.page });
  return { usage, reports, view, tick(ms: number) { now += ms; vi.advanceTimersByTime(ms); } };
}
afterEach(() => { vi.useRealTimers(); });

it('a press is counted by its name, at most every minute, and a name not on the list is not counted', () => {
  vi.useFakeTimers();
  const { usage, reports, tick } = counter();
  usage.used('display_xray');
  usage.used('display_xray');
  usage.used('export_step');
  usage.used('/Users/someone/secret.step');
  usage.used('Display_XRay');
  expect(reports).toEqual([]);
  tick(REPORT_MS);
  expect(reports).toEqual([[{ control: 'display_xray', count: 2, seconds: 0 }, { control: 'export_step', count: 1, seconds: 0 }]]);
  tick(REPORT_MS); // nothing new: nothing said
  expect(reports).toHaveLength(1);
  expect(CONTROLS.every(name => /^[a-z][a-z_]*$/.test(name))).toBe(true);
});

it('a setting moved in a burst is one change, and another burst a second', () => {
  vi.useFakeTimers();
  const { usage, reports, tick } = counter();
  for (let step = 0; step < 20; step += 1) { usage.changed('clip_amount'); tick(BURST_MS / 4); } // a slider dragged
  tick(BURST_MS);
  usage.changed('clip_amount');
  usage.flush();
  expect(reports).toEqual([[{ control: 'clip_amount', count: 2, seconds: 0 }]]);
});

it('a tool that stays on counts each turn on and its whole seconds while the page is shown, the rest kept for the next report', () => {
  vi.useFakeTimers();
  const { usage, reports, tick, view } = counter();
  usage.active('measure', true);
  tick(REPORT_MS + 500);
  // A minute on: its use and its seconds; the half second waits.
  expect(reports).toEqual([[{ control: 'measure', count: 1, seconds: 60 }]]);
  tick(REPORT_MS - 500);
  expect(reports[1]).toEqual([{ control: 'measure', count: 0, seconds: 60 }]);
  // Hidden, it stops running, and what was held is said at once: the page may not come back.
  tick(10_000);
  view.hide(true);
  expect(reports[2]).toEqual([{ control: 'measure', count: 0, seconds: 10 }]);
  tick(3_600_000);
  view.hide(false);
  tick(4_000);
  usage.active('measure', false);
  // Taken up again without being a person's choice (the tool a view opens with): seconds alone.
  usage.active('measure', true, { counted: false });
  tick(2_000);
  usage.active('measure', true); // already on: nothing
  usage.flush();
  expect(reports[3]).toEqual([{ control: 'measure', count: 0, seconds: 6 }]);
});

it('stopping says what it holds and leaves no timer or listener behind', () => {
  vi.useFakeTimers();
  const { usage, reports, tick, view } = counter();
  usage.used('preview_reset');
  usage.stop();
  expect(reports).toEqual([[{ control: 'preview_reset', count: 1, seconds: 0 }]]);
  usage.active('preview', true);
  tick(2_000);
  usage.active('preview', false);
  usage.stop();
  expect(reports[1]).toEqual([{ control: 'preview', count: 1, seconds: 2 }]);
  view.hide(true);
  tick(REPORT_MS * 3);
  expect(reports).toHaveLength(2);
  // Counting again starts it again.
  usage.used('home_pin');
  tick(REPORT_MS);
  expect(reports[2]).toEqual([{ control: 'home_pin', count: 1, seconds: 0 }]);
});

it('a report that fails fails nothing it counted', () => {
  const usage = createControlUsage({ report: () => { throw new Error('the host is gone'); }, page: null });
  usage.used('undo');
  expect(() => usage.flush()).not.toThrow();
});
