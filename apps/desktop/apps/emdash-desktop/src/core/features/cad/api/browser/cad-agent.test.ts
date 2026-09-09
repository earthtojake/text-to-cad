import { describe, expect, it } from 'vitest';
import type { Conversation } from '@core/primitives/conversations/api';
import {
  buildCadAgentContext,
  buildCadFirstRoutingContext,
  cadConversationsForModel,
  cadModelContextKey,
  selectCadConversation,
} from './cad-agent';

function conversation(overrides: Partial<Conversation>): Conversation {
  return {
    id: 'conversation-1',
    projectId: 'project-1',
    taskId: 'task-1',
    providerId: 'claude',
    title: 'Claude',
    lastInteractedAt: null,
    isInitialConversation: false,
    type: 'acp',
    ...overrides,
  };
}

describe('selectCadConversation', () => {
  it('selects only the conversation owned by the current CAD model', () => {
    const target = conversation({ id: 'target', contextKey: 'cad-model:examples/plate' });
    const unrelated = conversation({ id: 'unrelated', contextKey: 'cad-model:examples/bracket' });

    expect(
      selectCadConversation([unrelated, target], 'cad-model:examples/plate', new Set(['unrelated']))
        ?.id
    ).toBe('target');
  });

  it('ignores terminal-backed and legacy unscoped conversations', () => {
    expect(
      selectCadConversation(
        [conversation({ type: 'pty' }), conversation({ id: 'legacy' })],
        'cad-model:examples/plate',
        new Set()
      )
    ).toBeNull();
  });

  it('keeps several histories isolated and honors the model-selected conversation', () => {
    const design = conversation({ id: 'design', contextKey: 'cad-model:examples/plate' });
    const analysis = conversation({ id: 'analysis', contextKey: 'cad-model:examples/plate' });
    const unrelated = conversation({ id: 'other', contextKey: 'cad-model:examples/bracket' });

    expect(cadConversationsForModel([design, unrelated, analysis], design.contextKey!)).toEqual([
      design,
      analysis,
    ]);
    expect(
      selectCadConversation([design, analysis], design.contextKey!, new Set(['design']), 'analysis')
        ?.id
    ).toBe('analysis');
  });
});

describe('cadModelContextKey', () => {
  it('maps a STEP generator and its artifact to the same model', () => {
    expect(cadModelContextKey('examples/cad/plate.step.py')).toBe('cad-model:examples/cad/plate');
    expect(cadModelContextKey('examples/cad/plate.stp.py')).toBe('cad-model:examples/cad/plate');
    expect(cadModelContextKey('examples/cad/plate.py')).toBe('cad-model:examples/cad/plate');
    expect(cadModelContextKey('examples/cad/plate.step')).toBe('cad-model:examples/cad/plate');
  });

  it('normalizes Windows paths and implicit CAD source suffixes', () => {
    expect(cadModelContextKey('examples\\cad\\housing.implicit.mjs')).toBe(
      'cad-model:examples/cad/housing'
    );
  });
});

describe('buildCadAgentContext', () => {
  it('defaults ambiguous physical-object requests to CAD without removing general tools', () => {
    const context = buildCadFirstRoutingContext();

    expect(context).toContain('CAD-first');
    expect(context).toContain('physical object');
    expect(context).toContain('bundled Text-to-CAD skill');
    expect(context).toContain('Do not choose image generation');
    expect(context).toContain('screenshots, diagrams, and documents');
    expect(context).toContain('instead of forcing CAD');
    expect(context).toContain('Web search');
    expect(context).toContain('valid intermediate builds to the same output path');
    expect(context).toContain('cad-desktop skill');
  });

  it('anchors the agent to the current file and Jake validation workflow', () => {
    const context = buildCadAgentContext({
      relativePath: 'examples/cad/bracket.step',
      modelFiles: ['examples/cad/bracket.step.py', 'examples/cad/bracket.step'],
      revisionId: 'revision-4',
      conversationType: 'design',
      canEditGeometry: true,
      projectBrief: '<project-brief>Hold 50 N.</project-brief>',
      projectReferencePath: '/projects/gripper/context',
      manufacturingProfile: '<manufacturing-profile>process: "fdm"</manufacturing-profile>',
      engineeringWorkspace: '<engineering-workspace>PA12 datasheet</engineering-workspace>',
    });

    expect(context).toContain('examples/cad/bracket.step');
    expect(context).toContain('bundled Text-to-CAD skill');
    expect(context).toContain('render package provenance');
    expect(context).toContain('inspect/validate');
    expect(context).toContain('Hold 50 N.');
    expect(context).toContain('<manufacturing-profile>');
    expect(context).toContain('process: "fdm"');
    expect(context).toContain('PA12 datasheet');
    expect(context).toContain('/projects/gripper/context');
    expect(context).toContain('revision-4');
    expect(context).toContain('SHA-256 of the accepted on-disk STEP file');
    expect(context).toContain('bracket.step.py');
    expect(context).toContain('may change CAD geometry and other engineering artifacts');
    expect(context).toContain('drawing, assembly, analysis, or supporting file');
  });

  it('explains a temporary read-only state without assigning a permanent edit lease', () => {
    const context = buildCadAgentContext({
      relativePath: 'examples/cad/bracket.step',
      modelFiles: ['examples/cad/bracket.step'],
      revisionId: 'revision-4',
      conversationType: 'analysis',
      canEditGeometry: false,
      analysisRootPath: 'examples/cad/analyses/bracket',
    });

    expect(context).toContain('temporarily read-only');
    expect(context).toContain('until the active revision finishes');
    expect(context).toContain('analysis manifests');
    expect(context).toContain('examples/cad/analyses/bracket');
  });
});
