import { JSDOM } from 'jsdom';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { defineCommand } from '@core/primitives/commands/api';
import {
  defineViewScope,
  disabled,
  hidden,
  type ViewScopeImpl,
} from '@core/primitives/view-scopes/api';
import { focusScope as focusScopeInstance, ViewScopes } from './scopes';

const archiveCommand = defineCommand({
  id: 'task.archive',
  title: 'Archive Task',
  category: 'Task',
});
const pinCommand = defineCommand({
  id: 'task.pin',
  title: 'Pin Task',
  category: 'Task',
});
const createBranchCommand = defineCommand({
  id: 'task.createBranch',
  title: 'Create Branch',
  category: 'Git',
  input: z.object({ branchName: z.string(), baseRef: z.string() }),
});

const windowScope = defineViewScope({
  id: 'window',
  params: z.object({}),
  commands: [archiveCommand],
  activation: 'logical',
});
const taskScope = defineViewScope({
  id: 'view.task',
  params: z.object({ taskId: z.string() }),
  commands: [archiveCommand, pinCommand, createBranchCommand],
  activation: 'logical',
  key: ({ taskId }) => taskId,
});
const capturingScope = defineViewScope({
  id: 'modal',
  params: z.object({}),
  commands: [],
  activation: 'focus',
  traits: ['capturing'],
});
const focusScope = defineViewScope({
  id: 'terminal',
  params: z.object({ terminalId: z.string() }),
  commands: [archiveCommand],
  activation: 'focus',
});

describe('ViewScopes', () => {
  it('resolves and executes the innermost enabled command', () => {
    const outerExecute = vi.fn();
    const innerExecute = vi.fn();
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: outerExecute }) },
    });
    const inner = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ execute: innerExecute }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(inner);

    const hit = scopes.resolveKeybinding(new Set([archiveCommand.id]));
    if (hit.kind === 'winner') void hit.command.execute(undefined, 'keybinding');

    expect(hit.kind).toBe('winner');
    expect(innerExecute).toHaveBeenCalledWith(undefined, 'keybinding');
    expect(outerExecute).not.toHaveBeenCalled();
    scopes.dispose();
  });

  it('lets a disabled inner binding consume without falling through', () => {
    const outerExecute = vi.fn();
    const innerExecute = vi.fn();
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: outerExecute }) },
    });
    const inner = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({
          availability: () => disabled('Already archived'),
          execute: innerExecute,
        }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(inner);

    expect(scopes.resolveKeybinding(new Set([archiveCommand.id]))).toEqual({
      kind: 'consumed',
      commandId: 'task.archive',
    });
    expect(innerExecute).not.toHaveBeenCalled();
    expect(outerExecute).not.toHaveBeenCalled();
    scopes.dispose();
  });

  it('skips hidden bindings and continues to an outer scope', () => {
    const outerExecute = vi.fn();
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: outerExecute }) },
    });
    const inner = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ availability: () => hidden, execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(inner);

    const hit = scopes.resolveKeybinding(new Set([archiveCommand.id]));
    if (hit.kind === 'winner') void hit.command.execute(undefined);

    expect(hit.kind).toBe('winner');
    expect(outerExecute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('truncates resolution at a capturing scope', () => {
    const outerExecute = vi.fn();
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: outerExecute }) },
    });
    const modal = scopes.instantiate(capturingScope(), { parent: outer, impl: {} });
    scopes.activateCapture(modal);

    expect(scopes.resolveKeybinding(new Set(['task.archive']))).toEqual({ kind: 'none' });
    expect(outerExecute).not.toHaveBeenCalled();
    scopes.dispose();
  });

  it('resolves multiple keybinding candidates once in declaration order', () => {
    const archiveExecute = vi.fn();
    const pinExecute = vi.fn();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const scopes = new ViewScopes(undefined);
    const task = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      impl: {
        'task.archive': () => ({ execute: archiveExecute }),
        'task.pin': () => ({ execute: pinExecute }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(task);

    const hit = scopes.resolveKeybinding(new Set(['task.pin', 'task.archive']));

    expect(hit.kind).toBe('winner');
    if (hit.kind === 'winner') {
      expect(hit.command.def).toBe(archiveCommand);
      void hit.command.execute(undefined, 'keybinding');
    }
    expect(archiveExecute).toHaveBeenCalledOnce();
    expect(pinExecute).not.toHaveBeenCalled();
    if (import.meta.env.DEV) expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
    scopes.dispose();
  });

  it('lets a disabled earlier candidate consume before an enabled sibling', () => {
    const pinExecute = vi.fn();
    const scopes = new ViewScopes(undefined);
    const task = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      impl: {
        'task.archive': () => ({
          availability: () => disabled('Unavailable'),
          execute: vi.fn(),
        }),
        'task.pin': () => ({ execute: pinExecute }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(task);

    expect(scopes.resolveKeybinding(new Set(['task.archive', 'task.pin']))).toEqual({
      kind: 'consumed',
      commandId: 'task.archive',
    });
    expect(pinExecute).not.toHaveBeenCalled();
    scopes.dispose();
  });

  it('disposes an instance subtree and removes it from the active path', () => {
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const inner = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(inner);

    outer.dispose();

    expect(outer.isDisposed).toBe(true);
    expect(inner.isDisposed).toBe(true);
    expect(scopes.activePath).toEqual([]);
    scopes.dispose();
  });

  it('falls back to the nearest live ancestor when an active subtree is disposed', () => {
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const middle = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const inner = scopes.instantiate(taskScope({ taskId: 'task-2' }), {
      parent: middle,
      impl: {
        'task.archive': () => ({ execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    scopes.activate(inner);

    middle.dispose();

    expect(middle.isDisposed).toBe(true);
    expect(inner.isDisposed).toBe(true);
    expect(scopes.activePath).toEqual([outer]);
    scopes.dispose();
  });

  it('activates focus scopes through one delegated focus listener', () => {
    const dom = new JSDOM('<div id="root"><input id="terminal" /></div>');
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    scopes.activate(outer);
    const input = dom.window.document.querySelector<HTMLInputElement>('#terminal');
    expect(input).not.toBeNull();
    terminal.attachRef(input);

    input?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    expect(scopes.activePath.map((handle) => handle.ref.scopeId)).toEqual(['terminal', 'window']);
    expect(input?.getAttribute('data-view-scope')).toBe(terminal.id);
    expect(scopes.activePath[0]).toBe(terminal);
    expect(scopes.isWithinActivePath(outer)).toBe(true);
    scopes.dispose();
  });

  it('rejects focus scopes in the logical activation channel', () => {
    const scopes = new ViewScopes(undefined);
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });

    expect(() => scopes.activate(terminal)).toThrow(
      'View scope terminal does not use logical activation'
    );
    scopes.dispose();
  });

  it('clears ambient focus when focus moves to a logical scope root', () => {
    const dom = new JSDOM(
      '<div id="window" tabindex="-1"><div id="terminal" tabindex="-1"></div></div>'
    );
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const windowElement = dom.window.document.querySelector<HTMLElement>('#window');
    const terminalElement = dom.window.document.querySelector<HTMLElement>('#terminal');
    outer.attachRef(windowElement);
    terminal.attachRef(terminalElement);
    scopes.activate(outer);
    terminalElement?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    expect(scopes.activePath).toEqual([terminal, outer]);

    windowElement?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    expect(scopes.activePath).toEqual([outer]);
    scopes.dispose();
  });

  it('keeps the last focus scope active when focus moves to unscoped chrome', () => {
    const dom = new JSDOM(
      '<div id="terminal" tabindex="-1"></div><button id="sidebar">Sidebar</button>'
    );
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    scopes.activate(outer);
    const terminalElement = dom.window.document.querySelector<HTMLElement>('#terminal');
    terminal.attachRef(terminalElement);
    terminalElement?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    dom.window.document
      .querySelector<HTMLElement>('#sidebar')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    expect(scopes.activePath[0]).toBe(terminal);
    expect(scopes.activePath).toEqual([terminal, outer]);
    scopes.dispose();
  });

  it('falls back to a live ancestor when an active focus scope detaches', () => {
    const dom = new JSDOM('<div id="terminal" tabindex="-1"></div>');
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    scopes.activate(outer);
    const terminalElement = dom.window.document.querySelector<HTMLElement>('#terminal');
    terminal.attachRef(terminalElement);
    terminalElement?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    expect(scopes.activePath[0]).toBe(terminal);

    terminal.attachRef(null);

    expect(scopes.activePath[0]).toBe(outer);
    expect(scopes.activePath).toEqual([outer]);
    scopes.dispose();
  });

  it('restores the underlying focus path after a parentless overlay closes', () => {
    const dom = new JSDOM(
      '<div id="terminal" tabindex="-1"></div><div id="modal" tabindex="-1"></div>'
    );
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    terminal.attachRef(dom.window.document.querySelector<HTMLElement>('#terminal'));
    modal.attachRef(dom.window.document.querySelector<HTMLElement>('#modal'));
    scopes.activate(outer);
    dom.window.document
      .querySelector<HTMLElement>('#terminal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    const popOverlay = scopes.activateCapture(modal);
    dom.window.document
      .querySelector<HTMLElement>('#modal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    expect(scopes.activePath).toEqual([modal]);

    popOverlay();

    expect(scopes.activePath).toEqual([terminal, outer]);

    // A closing dialog may still receive focus before its exit animation
    // unmounts. It is no longer an overlay and must not replace the terminal.
    dom.window.document
      .querySelector<HTMLElement>('#modal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    expect(scopes.activePath).toEqual([terminal, outer]);
    scopes.dispose();
  });

  it('reveals the latest logical scope when navigation changes beneath an overlay', () => {
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const firstTask = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const nextTask = scopes.instantiate(taskScope({ taskId: 'task-2' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    scopes.activate(firstTask);
    const popOverlay = scopes.activateCapture(modal);

    scopes.activate(nextTask);
    expect(scopes.activePath).toEqual([modal]);

    popOverlay();

    expect(scopes.activePath).toEqual([nextTask, outer]);
    scopes.dispose();
  });

  it('clears a stale focused branch when a sibling logical scope activates', () => {
    const dom = new JSDOM('<div id="terminal" tabindex="-1"></div>');
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const nextView = scopes.instantiate(taskScope({ taskId: 'task-2' }), {
      parent: outer,
      impl: {
        'task.archive': () => ({ execute: vi.fn() }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    terminal.attachRef(dom.window.document.querySelector<HTMLElement>('#terminal'));
    dom.window.document
      .querySelector<HTMLElement>('#terminal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    scopes.activate(nextView);

    expect(scopes.activePath[0]).toBe(nextView);
    expect(scopes.activePath).toEqual([nextView, outer]);
    scopes.dispose();
  });

  it('focuses a delegate before falling back to the scope root', () => {
    const dom = new JSDOM('<div id="root" tabindex="-1"><input id="delegate" /></div>');
    const scopes = new ViewScopes(dom.window.document);
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const root = dom.window.document.querySelector<HTMLElement>('#root');
    const delegate = dom.window.document.querySelector<HTMLInputElement>('#delegate');
    terminal.attachRef(root);
    terminal.attachFocusDelegate(delegate);

    expect(focusScopeInstance(terminal)).toBe(true);
    expect(dom.window.document.activeElement).toBe(delegate);

    terminal.attachFocusDelegate(null);
    expect(focusScopeInstance(terminal)).toBe(true);
    expect(dom.window.document.activeElement).toBe(root);
    scopes.dispose();
  });

  it('preserves the underlying focus path for command palette discovery', () => {
    const dom = new JSDOM(
      '<div id="terminal" tabindex="-1"></div><div id="modal" tabindex="-1"></div>'
    );
    const scopes = new ViewScopes(dom.window.document);
    const execute = vi.fn();
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute }) },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    terminal.attachRef(dom.window.document.querySelector<HTMLElement>('#terminal'));
    modal.attachRef(dom.window.document.querySelector<HTMLElement>('#modal'));
    dom.window.document
      .querySelector<HTMLElement>('#terminal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    scopes.activateCapture(modal);
    dom.window.document
      .querySelector<HTMLElement>('#modal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    expect(scopes.getActiveCommand(archiveCommand)).toBeUndefined();
    expect(
      scopes.getActiveCommand(archiveCommand, { belowActiveCapture: true })?.availability.kind
    ).toBe('enabled');
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');
    expect(execute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('preserves the underlying scope when a capturing scope activates before focus', () => {
    const dom = new JSDOM('<div id="modal" tabindex="-1"></div>');
    const scopes = new ViewScopes(dom.window.document);
    const execute = vi.fn();
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute }) },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    modal.attachRef(dom.window.document.querySelector<HTMLElement>('#modal'));
    scopes.activate(outer);

    // ModalRenderer pushes a fresh overlay before Base UI's focus pass.
    scopes.activateCapture(modal);
    dom.window.document
      .querySelector<HTMLElement>('#modal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    expect(
      scopes.getActiveCommand(archiveCommand, { belowActiveCapture: true })?.availability.kind
    ).toBe('enabled');
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');
    expect(execute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('resolves through the next capture after the top capture closes', () => {
    const scopes = new ViewScopes(undefined);
    const execute = vi.fn();
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute }) },
    });
    const bottomModal = scopes.instantiate(capturingScope(), { impl: {} });
    const topModal = scopes.instantiate(capturingScope(), { impl: {} });
    scopes.activate(outer);
    scopes.activateCapture(bottomModal);
    scopes.activateCapture(topModal);

    expect(scopes.getActiveCommand(archiveCommand, { belowActiveCapture: true })).toBeUndefined();

    topModal.dispose();
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');

    expect(execute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('derives the layer below a capture after the lower capture closes first', () => {
    const scopes = new ViewScopes(undefined);
    const execute = vi.fn();
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute }) },
    });
    const bottomModal = scopes.instantiate(capturingScope(), { impl: {} });
    const topModal = scopes.instantiate(capturingScope(), { impl: {} });
    scopes.activate(outer);
    const removeBottom = scopes.activateCapture(bottomModal);
    const removeTop = scopes.activateCapture(topModal);

    removeBottom();

    expect(scopes.activePath).toEqual([topModal]);
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');
    expect(execute).toHaveBeenCalledOnce();

    removeTop();
    expect(scopes.activePath).toEqual([outer]);
    scopes.dispose();
  });

  it('reactivates a capture idempotently and ignores its stale disposer', () => {
    const scopes = new ViewScopes(undefined);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const firstModal = scopes.instantiate(capturingScope(), { impl: {} });
    const nextModal = scopes.instantiate(capturingScope(), { impl: {} });
    scopes.activate(outer);
    const removeFirstActivation = scopes.activateCapture(firstModal);
    scopes.activateCapture(nextModal);

    const removeCurrentActivation = scopes.activateCapture(firstModal);

    expect(scopes.activePath).toEqual([firstModal]);
    removeFirstActivation();
    expect(scopes.activePath).toEqual([firstModal]);

    removeCurrentActivation();
    expect(scopes.activePath).toEqual([nextModal]);
    scopes.dispose();
  });

  it('removes a capture when its root detaches without disposal', () => {
    const dom = new JSDOM('<div id="modal" tabindex="-1"></div>');
    const scopes = new ViewScopes(dom.window.document);
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: vi.fn() }) },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    modal.attachRef(dom.window.document.querySelector<HTMLElement>('#modal'));
    scopes.activate(outer);
    scopes.activateCapture(modal);
    expect(scopes.activePath).toEqual([modal]);

    modal.attachRef(null);

    expect(modal.isDisposed).toBe(false);
    expect(scopes.activePath).toEqual([outer]);
    scopes.dispose();
  });

  it('uses the current ambient path each time the same capture opens', () => {
    const scopes = new ViewScopes(undefined);
    const firstExecute = vi.fn();
    const nextExecute = vi.fn();
    const firstTask = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      impl: {
        'task.archive': () => ({ execute: firstExecute }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const nextTask = scopes.instantiate(taskScope({ taskId: 'task-2' }), {
      impl: {
        'task.archive': () => ({ execute: nextExecute }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    scopes.activate(firstTask);
    scopes.activateCapture(modal)();
    scopes.activate(nextTask);

    scopes.activateCapture(modal);
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');

    expect(firstExecute).not.toHaveBeenCalled();
    expect(nextExecute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('uses logical navigation that occurs beneath an active capture', () => {
    const scopes = new ViewScopes(undefined);
    const firstExecute = vi.fn();
    const nextExecute = vi.fn();
    const firstTask = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      impl: {
        'task.archive': () => ({ execute: firstExecute }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const nextTask = scopes.instantiate(taskScope({ taskId: 'task-2' }), {
      impl: {
        'task.archive': () => ({ execute: nextExecute }),
        'task.pin': () => ({ execute: vi.fn() }),
        'task.createBranch': () => ({ execute: vi.fn() }),
      },
    });
    const modal = scopes.instantiate(capturingScope(), { impl: {} });
    scopes.activate(firstTask);
    scopes.activateCapture(modal);

    scopes.activate(nextTask);
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');

    expect(firstExecute).not.toHaveBeenCalled();
    expect(nextExecute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('does not resolve palette commands against a disposed ambient focus scope', () => {
    const dom = new JSDOM(
      '<div id="terminal" tabindex="-1"></div><div id="modal" tabindex="-1"></div>'
    );
    const scopes = new ViewScopes(dom.window.document);
    const outerExecute = vi.fn();
    const staleExecute = vi.fn();
    const outer = scopes.instantiate(windowScope(), {
      impl: { 'task.archive': () => ({ execute: outerExecute }) },
    });
    const terminal = scopes.instantiate(focusScope({ terminalId: 'terminal-1' }), {
      parent: outer,
      impl: { 'task.archive': () => ({ execute: staleExecute }) },
    });
    const modal = scopes.instantiate(capturingScope(), { parent: outer, impl: {} });
    terminal.attachRef(dom.window.document.querySelector<HTMLElement>('#terminal'));
    modal.attachRef(dom.window.document.querySelector<HTMLElement>('#modal'));
    scopes.activate(outer);
    dom.window.document
      .querySelector<HTMLElement>('#terminal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    scopes.activateCapture(modal);
    dom.window.document
      .querySelector<HTMLElement>('#modal')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));

    terminal.dispose();
    scopes
      .getActiveCommand(archiveCommand, { belowActiveCapture: true })
      ?.execute(undefined, 'palette');

    expect(staleExecute).not.toHaveBeenCalled();
    expect(outerExecute).toHaveBeenCalledOnce();
    scopes.dispose();
  });

  it('rejects incomplete instance implementations in development', () => {
    const scopes = new ViewScopes(undefined);

    if (import.meta.env.DEV) {
      expect(() =>
        scopes.instantiate(taskScope({ taskId: 'task-1' }), { impl: {} as never })
      ).toThrow(
        'View scope implementation view.task is missing command bindings: task.archive, task.pin, task.createBranch'
      );
    }
    scopes.dispose();
  });

  it('validates explicit command input before invoking a binding', () => {
    const execute = vi.fn();
    const implementation: ViewScopeImpl<typeof taskScope> = {
      'task.archive': () => ({ execute: vi.fn() }),
      'task.pin': () => ({ execute: vi.fn() }),
      'task.createBranch': () => ({ execute }),
    };
    const scopes = new ViewScopes(undefined);
    const instance = scopes.instantiate(taskScope({ taskId: 'task-1' }), {
      impl: implementation,
    });
    const command = instance.getCommand(createBranchCommand);

    expect(() => command?.execute({ branchName: 'feature', baseRef: 1 } as never)).toThrow();
    void command?.execute({ branchName: 'feature', baseRef: 'main' });
    expect(execute).toHaveBeenCalledWith(
      { branchName: 'feature', baseRef: 'main' },
      'programmatic'
    );
    scopes.dispose();
  });
});
