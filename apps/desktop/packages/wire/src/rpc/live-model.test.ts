import { ok } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { LiveModelClientHandle } from '../api/client';
import {
  defineContract,
  liveModel,
  liveState,
  mutation,
  type LiveModelKey,
  type LiveModelDef,
} from '../api/define';
import { encodeTopic } from '../api/topics';
import { createLiveModelReplicaCache, type LiveModelReplicaCacheOptions } from '../live/replica';
import { expose, type ExposedMutationHandlers } from '../state/bridge/expose';
import { cell } from '../state/core';
import { createTestWire } from '../testing';
import { createController } from './controller';

const keySchema = z.object({ conversationId: z.string() });
const stateSchema = z.object({ title: z.string() });
const usageSchema = z.object({ tokens: z.number() });

const contract = defineContract({
  conversation: liveModel({
    key: keySchema,
    states: {
      state: liveState({ data: stateSchema }),
      usage: liveState({ data: usageSchema }),
    },
    mutations: {
      setTitle: mutation({
        input: z.object({ title: z.string() }),
        data: z.void(),
        error: z.string(),
      }),
    },
  }),
});

type ConversationDef = typeof contract.conversation;

function conversationSource(
  def: ConversationDef,
  initial: { title: string; tokens: number },
  mutations?: Partial<ExposedMutationHandlers<ConversationDef>>
) {
  const state = cell({ title: initial.title });
  const usage = cell({ tokens: initial.tokens });
  const provider = expose(
    def,
    { state: () => state, usage: () => usage },
    {
      mutations: mutations ?? {
        async setTitle(context) {
          const stateRevision = state.update(() => ({ title: context.input.title }), {
            mutationIds: [context.mutationId],
          });
          const usageRevision = usage.update(
            (previous) => ({ tokens: previous.tokens + context.input.title.length }),
            { mutationIds: [context.mutationId] }
          );
          await Promise.all([
            context.observed('state', stateRevision),
            context.observed('usage', usageRevision),
          ]);
          return ok(undefined);
        },
      },
    }
  );
  return { state, usage, provider };
}

function setup() {
  const key = { conversationId: 'c1' };
  const { provider } = conversationSource(contract.conversation, { title: 'Initial', tokens: 0 });
  const wire = createTestWire(contract, { conversation: provider });
  return { client: wire.client, controller: wire.controller, key, provider };
}

describe('liveModel', () => {
  it('registers group member models and resolves their live topics', async () => {
    const { controller, key, provider } = setup();
    const topic = encodeTopic(contract.conversation.states.state.id, key);
    const lease = controller.acquireLive(topic);
    expect(lease).not.toBeNull();
    const source = await lease!.ready();
    await expect(Promise.resolve(source.snapshot())).resolves.toMatchObject({
      data: { title: 'Initial' },
    });
    await lease!.release();
    await provider.dispose();
    expect(() => controller.acquireLive(topic)).toThrow(/disposed/);
  });

  it('binds a group client and settles multi-member mutations', async () => {
    const { client, key } = setup();
    const seenTitles: string[] = [];
    const { instance: conversation, dispose } = await acquireConversation(
      client.conversation,
      key,
      {
        onChange: {
          state: (state) => seenTitles.push((state as { title: string }).title),
        },
      }
    );
    await conversation.ready;

    const invocation = await conversation.mutations.setTitle({ title: 'Updated' });
    await invocation.settled;

    expect(invocation.result.success).toBe(true);
    expect(conversation.states.state.current()).toEqual({ title: 'Updated' });
    expect(conversation.states.usage.current()).toEqual({ tokens: 7 });
    expect(seenTitles.at(-1)).toBe('Updated');
    await dispose();
  });

  it('dedupes duplicate group mutation ids', async () => {
    const { client, key } = setup();
    const { instance: conversation, dispose } = await acquireConversation(client.conversation, key);

    await conversation.mutations.setTitle({ title: 'Once' }, { mutationId: 'same-group-mutation' });
    await conversation.mutations.setTitle(
      { title: 'Twice' },
      { mutationId: 'same-group-mutation' }
    );

    expect(conversation.states.state.current()).toEqual({ title: 'Once' });
    expect(conversation.states.usage.current()).toEqual({ tokens: 4 });
    await dispose();
  });

  it('requires a matching provider for groups', () => {
    const other = defineContract({
      other: liveModel({
        key: keySchema,
        states: {
          state: liveState({ data: stateSchema }),
          usage: liveState({ data: usageSchema }),
        },
      }),
    });
    const { provider } = conversationSource(other.other as unknown as ConversationDef, {
      title: 'Initial',
      tokens: 0,
    });
    expect(() => createController(contract, { conversation: provider as never })).toThrow(
      /created for 'other'/
    );
  });

  it('passes the envelope key to exposed mutation handlers', async () => {
    const key = { conversationId: 'keyed' };
    const state = cell({ title: 'Initial' });
    const usage = cell({ tokens: 0 });
    const provider = expose(
      contract.conversation,
      { state: () => state, usage: () => usage },
      {
        mutations: {
          async setTitle(context) {
            expect(context.key).toEqual(key);
            const revision = state.update(() => ({ title: context.input.title }), {
              mutationIds: [context.mutationId],
            });
            await context.observed('state', revision);
            return ok(undefined);
          },
        },
      }
    );
    const { client: contractClient } = createTestWire(contract, { conversation: provider });

    const { instance: conversation, dispose } = await acquireConversation(
      contractClient.conversation,
      key
    );
    const invocation = await conversation.mutations.setTitle({ title: 'Handled' });
    await invocation.settled;

    expect(conversation.states.state.current()).toEqual({ title: 'Handled' });
    await dispose();
  });

  it('requires handlers for exposed mutations', async () => {
    const key = { conversationId: 'no-handler' };
    const { provider } = conversationSource(
      contract.conversation,
      { title: 'Initial', tokens: 0 },
      {}
    );
    const { client: contractClient } = createTestWire(contract, { conversation: provider });

    await expect(
      contractClient.conversation.mutate('setTitle', { key, input: { title: 'x' } })
    ).rejects.toThrow(/requires a handler/);
  });

  it('mounts group model ids and mutations under nested contract keys', async () => {
    const nested = defineContract({ child: contract });
    const key = { conversationId: 'nested' };
    const { provider } = conversationSource(nested.child.conversation, {
      title: 'Initial',
      tokens: 0,
    });
    const { client: contractClient } = createTestWire(nested, {
      child: { conversation: provider },
    });

    expect(nested.child.conversation.states.state.id).toBe('child.conversation.state');
    const { instance: conversation, dispose } = await acquireConversation(
      contractClient.child.conversation,
      key
    );
    const invocation = await conversation.mutations.setTitle({ title: 'Nested' });
    await invocation.settled;

    expect(conversation.states.state.current()).toEqual({ title: 'Nested' });
    await dispose();
  });
});

async function acquireConversation<Group extends LiveModelDef>(
  group: LiveModelClientHandle<Group>,
  key: LiveModelKey<Group>,
  options: LiveModelReplicaCacheOptions = {}
) {
  const replica = createLiveModelReplicaCache(group.def, group, options);
  const lease = replica.acquire(key);
  const instance = await lease.ready();
  return {
    instance,
    async dispose() {
      await lease.release();
      await replica.dispose();
    },
  };
}
