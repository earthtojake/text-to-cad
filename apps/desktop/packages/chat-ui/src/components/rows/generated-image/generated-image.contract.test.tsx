import { SEGMENTERS } from '@components/engine/unit-registry';
import { DEFAULT_THEME } from '@core/theme';
import type { SegmentCtx } from '@core/units';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createChatContext } from '@/chat-context';
import { createChatView } from '@/chat-view';
import type { ChatCommands, ChatMessage, ChatToolCall, ToolNode, TranscriptTurn } from '@/index';
import { createChatState } from '@/state/chat-state';

const segmentCtx = {
  active: false,
  caches: {},
  expanded: () => false,
  plan: () => null,
  pendingToolCallIds: () => new Set<string>(),
  terminalOutput: () => null,
} as unknown as SegmentCtx;

const nextPaint = (): Promise<void> =>
  new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));

const cleanups: Array<() => void> = [];

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup();
});

function mount(items: ChatToolCall[], commands: ChatCommands): HTMLElement {
  const context = createChatContext({ theme: DEFAULT_THEME });
  const state = createChatState(context);
  const turn: TranscriptTurn = {
    id: 'turn-generated-image',
    seq: 0,
    initiator: 'agent',
    items: items.map((item, seq) => ({ ...item, seq })) as unknown as TranscriptTurn['items'],
  };
  state.transcript.history.seed([turn]);

  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;top:0;left:0;width:640px;height:500px;';
  document.body.appendChild(host);
  const view = createChatView({ context, state, parent: host, commands });

  cleanups.push(() => {
    view.dispose();
    state.dispose();
    context.dispose();
    host.remove();
  });
  return host;
}

describe('generated image segmentation', () => {
  it('keeps the image result adjacent to its tool activity row', () => {
    const tool = {
      kind: 'unknown-tool-call',
      id: 'image-tool',
      seq: 0,
      toolCallId: 'image-call',
      title: 'Image generation',
      status: 'done',
      toolKind: 'image-generation',
      name: 'Image generation',
      attachments: [{ id: 'generated-1', name: 'concept.png', mimeType: 'image/png' }],
    } satisfies ToolNode;

    const units = SEGMENTERS[tool.kind]!.segment(tool, segmentCtx);

    expect(units.map((unit) => unit.kind)).toEqual(['tool', 'generated-image']);
    expect(units[1]!.data).toMatchObject({
      sourceItemId: 'image-tool',
      source: 'generated-image',
      attachments: [{ id: 'generated-1', name: 'concept.png' }],
    });
  });

  it('renders assistant image attachments even when no tool association is available', () => {
    const message = {
      kind: 'message',
      id: 'assistant-image',
      role: 'assistant',
      text: 'Here is the generated concept.',
      attachments: [{ id: 'generated-2', name: 'concept-2.png', mimeType: 'image/png' }],
    } satisfies ChatMessage;

    const units = SEGMENTERS.message!.segment(message, segmentCtx);

    expect(units.map((unit) => unit.kind)).toEqual(['message', 'generated-image']);
    expect(units[1]!.data).toMatchObject({
      sourceItemId: 'assistant-image',
      source: 'assistant-message',
    });
  });

  it('emits image results for specialized execute and subagent rows', () => {
    const tools = [
      {
        kind: 'execute-tool-call',
        id: 'execute-image',
        seq: 0,
        toolCallId: 'execute-image-call',
        title: 'Render preview',
        status: 'done',
        command: 'render-preview',
        attachments: [{ id: 'execute-output', name: 'render.png', mimeType: 'image/png' }],
      },
      {
        kind: 'spawn-subagent-tool-call',
        id: 'subagent-image',
        seq: 1,
        toolCallId: 'subagent-image-call',
        title: 'Design helper',
        status: 'done',
        name: 'Design helper',
        attachments: [{ id: 'subagent-output', name: 'concept.png', mimeType: 'image/png' }],
      },
    ] satisfies ToolNode[];

    expect(
      tools.map((tool) => SEGMENTERS[tool.kind]!.segment(tool, segmentCtx).map((unit) => unit.kind))
    ).toEqual([
      ['execute', 'generated-image'],
      ['subagent', 'generated-image'],
    ]);
  });

  it('surfaces nested image results once with collision-free unit ids', () => {
    const nestedImageTool = {
      kind: 'unknown-tool-call',
      id: 'nested-image-tool',
      seq: 0,
      toolCallId: 'nested-image-call',
      title: 'Image generation',
      status: 'done',
      toolKind: 'image-generation',
      name: 'Image generation',
      attachments: [{ id: 'nested-output', name: 'nested.png', mimeType: 'image/png' }],
    } satisfies ToolNode;
    const duplicateChild = {
      ...nestedImageTool,
      id: 'nested-image-duplicate',
      toolCallId: 'nested-image-duplicate-call',
    } satisfies ToolNode;
    const nestedSubagent = {
      kind: 'spawn-subagent-tool-call',
      id: 'nested-subagent',
      seq: 0,
      toolCallId: 'nested-subagent-call',
      title: 'Design helper',
      status: 'done',
      name: 'Design helper',
      children: [nestedImageTool, duplicateChild],
    } satisfies ToolNode;
    const nestedExecute = {
      kind: 'execute-tool-call',
      id: 'nested-execute',
      seq: 1,
      toolCallId: 'nested-execute-call',
      title: 'Render output',
      status: 'done',
      command: 'render-output',
      attachments: [{ id: 'execute-output', name: 'render.png', mimeType: 'image/png' }],
    } satisfies ToolNode;
    const group = {
      kind: 'tool-group',
      id: 'image-tool-group',
      seq: 0,
      label: 'Design tools',
      groupKind: 'read-batch',
      status: 'done',
      children: [nestedSubagent, nestedExecute],
    } satisfies ToolNode;

    const units = SEGMENTERS[group.kind]!.segment(group, segmentCtx);
    const imageUnits = units.filter((unit) => unit.kind === 'generated-image');

    expect(units.map((unit) => unit.kind)).toEqual([
      'tool-group',
      'generated-image',
      'generated-image',
    ]);
    expect(imageUnits.map((unit) => unit.data)).toMatchObject([
      {
        sourceItemId: 'nested-image-tool',
        attachments: [{ id: 'nested-output' }],
      },
      {
        sourceItemId: 'nested-execute',
        attachments: [{ id: 'execute-output' }],
      },
    ]);
    expect(new Set(units.map((unit) => unit.id)).size).toBe(units.length);
  });

  it('resolves, lays out, and opens a generated image without colliding virtual rows', async () => {
    const onViewImage = vi.fn();
    const frameErrors: unknown[][] = [];
    const originalConsoleError = console.error;
    const consoleError = vi.spyOn(console, 'error').mockImplementation((...args) => {
      frameErrors.push(args);
    });
    cleanups.push(() => {
      consoleError.mockRestore();
      console.error = originalConsoleError;
    });

    const preview =
      'data:image/svg+xml,' +
      encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/>');
    const host = mount(
      [
        {
          kind: 'tool',
          id: 'generated-image-tool',
          name: 'Generated image',
          activity: 'image-generation',
          status: 'done',
          outputAttachments: [
            { id: 'generated-image-ref', name: 'concept.png', mimeType: 'image/png' },
          ],
        },
      ],
      {
        resolveAttachment: async () => preview,
        onViewImage,
      }
    );

    await nextPaint();
    await nextPaint();

    const button = host.querySelector<HTMLButtonElement>(
      'button[aria-label="View generated image: concept.png"]'
    );
    expect(button).not.toBeNull();
    expect(button!.offsetWidth).toBe(280);
    expect(button!.offsetHeight).toBe(280);
    expect(button!.querySelector('img')?.getAttribute('src')).toBe(preview);

    button!.click();
    expect(onViewImage).toHaveBeenCalledWith({
      attachment: {
        id: 'generated-image-ref',
        name: 'concept.png',
        mimeType: 'image/png',
        dataUrl: preview,
      },
      itemId: 'generated-image-tool',
      source: 'generated-image',
    });
    expect(
      frameErrors.some(([message]) => String(message).includes('frame scheduler phase error'))
    ).toBe(false);
  });
});
