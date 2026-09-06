import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { describe, expect, it, vi } from 'vitest';
import type { NormalizedEvent } from '#runtimes/acp/api';
import type { AcpConnectionContext } from '#runtimes/acp/node/connection/source';
import { buildAgentClient, type InboundRouter } from './agent-client';

describe('buildAgentClient generated-image ingress', () => {
  it('redacts image data before provider enrichment while forwarding the original for persistence', async () => {
    const encoded = Buffer.from('generated image bytes '.repeat(8)).toString('base64');
    const dataUri = `data:image/png;base64,${encoded}`;
    const update = {
      sessionUpdate: 'tool_call_update',
      toolCallId: 'image-1',
      title: 'Image generation',
      status: 'completed',
      content: [
        {
          type: 'content',
          content: { type: 'image', data: encoded, mimeType: 'image/png', uri: dataUri },
        },
      ],
      rawOutput: JSON.stringify({ result: dataUri, note: 'keep this text' }),
      _meta: { mirroredImage: encoded, mirroredUri: dataUri },
    } as SessionUpdate;

    const normalize = vi.fn((safeUpdate: SessionUpdate): NormalizedEvent => {
      const outputText = (safeUpdate as { rawOutput?: unknown }).rawOutput;
      return {
        kind: 'tool_update',
        toolCallId: 'image-1',
        title: 'Image generation',
        toolKind: 'other',
        status: 'completed',
        parentToolCallId: null,
        diffs: [],
        ...(typeof outputText === 'string' ? { outputText } : {}),
      };
    });
    const connection: AcpConnectionContext = {
      key: 'claude:/workspace',
      providerId: 'claude',
      cwd: '/workspace',
      normalize,
    };
    const onSessionUpdate = vi.fn<InboundRouter['onSessionUpdate']>(async () => undefined);
    const router = {
      onSessionUpdate,
      onPermissionRequest: vi.fn(),
      onCreateTerminal: vi.fn(),
      onElicitation: vi.fn(),
    } as unknown as InboundRouter;
    const client = buildAgentClient(connection, router, {} as never);

    await client.sessionUpdate({ sessionId: 'session-1', update });

    const normalizedInput = normalize.mock.calls[0]?.[0];
    expect(JSON.stringify(normalizedInput)).not.toContain(encoded);
    expect(JSON.stringify(normalizedInput)).not.toContain('data:image');
    expect(JSON.stringify(normalizedInput)).toContain('keep this text');
    expect(onSessionUpdate).toHaveBeenCalledWith(
      connection,
      { sessionId: 'session-1', update },
      expect.objectContaining({ outputText: expect.stringContaining('keep this text') })
    );
    const normalizedEvent = onSessionUpdate.mock.calls[0]?.[2];
    expect(JSON.stringify(normalizedEvent)).not.toContain(encoded);
    expect(JSON.stringify(normalizedEvent)).not.toContain('data:image');
  });

  it('leaves ordinary textual tool output unchanged', async () => {
    const update = {
      sessionUpdate: 'tool_call_update',
      toolCallId: 'execute-1',
      title: 'Execute',
      rawOutput: 'ordinary terminal output',
    } as SessionUpdate;
    const normalize = vi.fn(
      (): NormalizedEvent => ({
        kind: 'tool_update',
        toolCallId: 'execute-1',
        title: 'Execute',
        toolKind: 'execute',
        status: 'completed',
        parentToolCallId: null,
        diffs: [],
        outputText: 'ordinary terminal output',
      })
    );
    const connection = {
      key: 'claude:/workspace',
      providerId: 'claude',
      cwd: '/workspace',
      normalize,
    } as AcpConnectionContext;
    const onSessionUpdate = vi.fn<InboundRouter['onSessionUpdate']>(async () => undefined);
    const client = buildAgentClient(
      connection,
      {
        onSessionUpdate,
        onPermissionRequest: vi.fn(),
        onCreateTerminal: vi.fn(),
      } as unknown as InboundRouter,
      {} as never
    );

    await client.sessionUpdate({ sessionId: 'session-1', update });

    expect(normalize).toHaveBeenCalledWith(update);
    expect(onSessionUpdate.mock.calls[0]?.[2]).toMatchObject({
      outputText: 'ordinary terminal output',
    });
  });
});
