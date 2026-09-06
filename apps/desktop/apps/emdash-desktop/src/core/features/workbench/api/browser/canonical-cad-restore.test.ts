import { describe, expect, it } from 'vitest';
import type { CadModelCatalog, CadModelRecord } from '@core/features/cad/contributions/mementos';
import type { Conversation } from '@core/primitives/conversations/api';
import {
  planCanonicalCadCatalogTabRetargets,
  planCanonicalCadRestore,
  planCanonicalCadTabRetarget,
  planCanonicalCadTabRetargets,
  planLegacyCadRestore,
} from './canonical-cad-restore';

const baseConversation: Conversation = {
  id: 'design-1',
  projectId: 'project-1',
  taskId: 'task-1',
  providerId: 'claude-code',
  title: 'Design',
  lastInteractedAt: '2026-08-28T10:00:00.000Z',
  isInitialConversation: false,
  type: 'acp',
  contextKey: 'cad-model:royal-castle',
};

function model(overrides: Partial<CadModelRecord> = {}): CadModelRecord {
  return {
    contextKey: 'cad-model:royal-castle',
    modelPath: 'royal-castle.step',
    sourcePath: 'royal-castle.step.py',
    artifacts: [
      { path: 'royal-castle.step', role: 'model' },
      { path: 'royal-castle.step.py', role: 'source' },
    ],
    conversations: {},
    activeConversationId: 'design-1',
    run: { status: 'completed' },
    updatedAt: '2026-08-28T10:00:00.000Z',
    ...overrides,
  };
}

function catalog(models: CadModelRecord[], activeModelKey?: string): CadModelCatalog {
  return {
    version: '3',
    ...(activeModelKey ? { activeModelKey } : {}),
    models: Object.fromEntries(models.map((record) => [record.contextKey, record])),
  };
}

describe('canonical CAD artifact restore planning', () => {
  it('restores the active canonical model and its active chat', () => {
    const plan = planCanonicalCadRestore(catalog([model()], 'cad-model:royal-castle'), [
      baseConversation,
    ]);

    expect(plan).toEqual({
      contextKey: 'cad-model:royal-castle',
      path: 'royal-castle.step',
      conversationId: 'design-1',
    });
  });

  it('uses the model artifact when no editable generator exists', () => {
    const plan = planCanonicalCadRestore(catalog([model({ sourcePath: undefined })]), [
      baseConversation,
    ]);

    expect(plan?.path).toBe('royal-castle.step');
  });

  it('keeps an explicitly active model ahead of a newer model', () => {
    const newer = model({
      contextKey: 'cad-model:other',
      modelPath: 'other.step',
      sourcePath: 'other.step.py',
      updatedAt: '2026-08-28T11:00:00.000Z',
    });

    expect(
      planCanonicalCadRestore(catalog([model(), newer], 'cad-model:royal-castle'), [
        baseConversation,
      ])?.path
    ).toBe('royal-castle.step');
  });

  it('falls back from a dangling active key to the newest matching model', () => {
    const matching = model({ updatedAt: '2026-08-28T09:00:00.000Z' });
    const unrelated = model({
      contextKey: 'cad-model:other',
      modelPath: 'other.step',
      updatedAt: '2026-08-28T11:00:00.000Z',
    });

    expect(
      planCanonicalCadRestore(catalog([matching, unrelated], 'cad-model:missing'), [
        baseConversation,
      ])?.path
    ).toBe('royal-castle.step');
  });

  it('does not guess between multiple catalog models without a matching chat', () => {
    const unrelatedConversation = { ...baseConversation, contextKey: undefined };
    const other = model({
      contextKey: 'cad-model:other',
      modelPath: 'other.step',
      updatedAt: '2026-08-28T11:00:00.000Z',
    });

    expect(planCanonicalCadRestore(catalog([model(), other]), [unrelatedConversation])).toBeNull();
  });

  it('does nothing for a genuinely new task with no CAD record', () => {
    expect(planCanonicalCadRestore(catalog([]), [baseConversation])).toBeNull();
  });

  it('does not restore an archived active conversation', () => {
    const archivedModel = model({
      conversations: {
        'design-1': {
          id: 'design-1',
          type: 'design',
          createdAt: '2026-08-28T10:00:00.000Z',
          updatedAt: '2026-08-28T10:00:00.000Z',
          archivedAt: '2026-08-28T11:00:00.000Z',
        },
      },
    });

    expect(planCanonicalCadRestore(catalog([archivedModel]), [baseConversation])).toEqual({
      contextKey: 'cad-model:royal-castle',
      path: 'royal-castle.step',
    });
  });

  it('reopens the accepted STEP after an interrupted run without selecting stale source', () => {
    const interrupted = model({
      sourcePath: 'recipes/royal-castle.py',
      run: {
        id: 'interrupted-run',
        origin: 'source',
        status: 'interrupted',
      },
    });

    expect(
      planCanonicalCadRestore(catalog([interrupted], interrupted.contextKey), [baseConversation])
    ).toMatchObject({
      path: 'royal-castle.step',
      conversationId: 'design-1',
    });
  });

  it('retargets a persisted legacy source tab to the catalog STEP on restart', () => {
    const restorePlan = planCanonicalCadRestore(catalog([model()], 'cad-model:royal-castle'), [
      baseConversation,
    ]);
    expect(restorePlan).not.toBeNull();
    if (!restorePlan) return;

    expect(
      planCanonicalCadTabRetarget(restorePlan, [
        {
          tabId: 'persisted-cad-tab',
          path: 'royal-castle.step.py',
          contextKey: 'cad-model:royal-castle',
        },
      ])
    ).toEqual({ tabId: 'persisted-cad-tab', path: 'royal-castle.step' });
  });

  it('retargets every persisted legacy source tab for the restored model', () => {
    const restorePlan = planCanonicalCadRestore(catalog([model()], 'cad-model:royal-castle'), [
      baseConversation,
    ]);
    expect(restorePlan).not.toBeNull();
    if (!restorePlan) return;

    expect(
      planCanonicalCadTabRetargets(restorePlan, [
        {
          tabId: 'left-pane-tab',
          path: 'royal-castle.step.py',
          contextKey: 'cad-model:royal-castle',
        },
        {
          tabId: 'right-pane-tab',
          path: 'recipes/royal-castle.py',
          contextKey: 'cad-model:royal-castle',
        },
        {
          tabId: 'other-model-tab',
          path: 'bridge.step.py',
          contextKey: 'cad-model:bridge',
        },
      ])
    ).toEqual([
      { tabId: 'left-pane-tab', path: 'royal-castle.step' },
      { tabId: 'right-pane-tab', path: 'royal-castle.step' },
    ]);
  });

  it('keeps an already canonical persisted CAD tab unchanged', () => {
    const restorePlan = planCanonicalCadRestore(catalog([model()], 'cad-model:royal-castle'), [
      baseConversation,
    ]);
    expect(restorePlan).not.toBeNull();
    if (!restorePlan) return;

    expect(
      planCanonicalCadTabRetarget(restorePlan, [
        {
          tabId: 'persisted-cad-tab',
          path: 'royal-castle.step',
          contextKey: 'cad-model:royal-castle',
        },
      ])
    ).toBeNull();
  });

  it('retargets source tabs for every catalog model across multiple panes', () => {
    const bridge = model({
      contextKey: 'cad-model:bridge',
      modelPath: 'models/bridge.step',
      sourcePath: 'recipes/bridge.py',
      updatedAt: '2026-08-28T11:00:00.000Z',
    });
    const enclosure = model({
      contextKey: 'cad-model:enclosure',
      modelPath: 'models/enclosure.step',
      sourcePath: 'recipes/enclosure.py',
      updatedAt: '2026-08-28T12:00:00.000Z',
    });

    expect(
      planCanonicalCadCatalogTabRetargets(catalog([bridge, enclosure], bridge.contextKey), [
        {
          tabId: 'left-pane-active-model',
          path: 'recipes/bridge.py',
          contextKey: bridge.contextKey,
        },
        {
          tabId: 'right-pane-non-active-model',
          path: 'recipes/enclosure.py',
          contextKey: enclosure.contextKey,
        },
      ])
    ).toEqual([
      { tabId: 'left-pane-active-model', path: 'models/bridge.step' },
      { tabId: 'right-pane-non-active-model', path: 'models/enclosure.step' },
    ]);
  });

  it('uses an explicit source link when recipe and STEP directories and stems differ', () => {
    const customOutput = model({
      contextKey: 'cad-model:STEP/final-plate',
      modelPath: 'STEP/final-plate.step',
      sourcePath: 'src/recipes/plate-generator.py',
    });

    expect(
      planCanonicalCadCatalogTabRetargets(catalog([customOutput]), [
        {
          tabId: 'custom-source-tab',
          path: 'src/recipes/plate-generator.py',
          // Persisted tabs historically derived this from their own path, so
          // it need not equal the canonical model's context key.
          contextKey: 'cad-model:src/recipes/plate-generator',
        },
      ])
    ).toEqual([{ tabId: 'custom-source-tab', path: 'STEP/final-plate.step' }]);
  });

  it('keeps every already canonical model tab unchanged', () => {
    const bridge = model({
      contextKey: 'cad-model:bridge',
      modelPath: 'models/bridge.step',
      sourcePath: 'recipes/bridge.py',
    });
    const enclosure = model({
      contextKey: 'cad-model:enclosure',
      modelPath: 'models/enclosure.step',
      sourcePath: 'recipes/enclosure.py',
    });

    expect(
      planCanonicalCadCatalogTabRetargets(catalog([bridge, enclosure]), [
        { tabId: 'bridge', path: bridge.modelPath, contextKey: bridge.contextKey },
        { tabId: 'enclosure', path: enclosure.modelPath, contextKey: enclosure.contextKey },
      ])
    ).toEqual([]);
  });

  it('keeps a deliberate same-context CAD export tab unchanged', () => {
    const bracket = model({
      contextKey: 'cad-model:models/bracket',
      modelPath: 'models/bracket.step',
      sourcePath: 'recipes/bracket.py',
    });

    expect(
      planCanonicalCadCatalogTabRetargets(catalog([bracket]), [
        {
          tabId: 'mesh-export',
          path: 'models/bracket.stl',
          contextKey: bracket.contextKey,
        },
      ])
    ).toEqual([]);
  });
});

describe('legacy CAD artifact restore planning', () => {
  it('checks only same-stem artifacts and never executes a legacy recipe on restart', () => {
    expect(planLegacyCadRestore([baseConversation])).toEqual({
      contextKey: 'cad-model:royal-castle',
      conversationId: 'design-1',
      candidatePaths: [
        'royal-castle.step',
        'royal-castle.stp',
        'royal-castle.stl',
        'royal-castle.3mf',
        'royal-castle.glb',
        'royal-castle.dxf',
      ],
    });
  });

  it('rejects CAD context paths that escape the workspace', () => {
    expect(
      planLegacyCadRestore([{ ...baseConversation, contextKey: 'cad-model:../outside/secret' }])
    ).toBeNull();
  });
});
