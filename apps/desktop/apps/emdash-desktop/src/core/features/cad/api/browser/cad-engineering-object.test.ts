import { describe, expect, it } from 'vitest';
import {
  availableEngineeringWorkspaceModes,
  cadSourcePath,
  DERIVED_ENGINEERING_ARTIFACTS,
  ENGINEERING_OBJECT_MODES,
} from './cad-engineering-object';

describe('engineering object workspace modes', () => {
  it('keeps part and assembly capabilities distinct', () => {
    expect(ENGINEERING_OBJECT_MODES.part).not.toContain('instructions');
    expect(ENGINEERING_OBJECT_MODES.assembly).toContain('instructions');
    expect(ENGINEERING_OBJECT_MODES.assembly).toContain('bom');
    expect(ENGINEERING_OBJECT_MODES.part).not.toContain('files');
    expect(ENGINEERING_OBJECT_MODES.assembly).not.toContain('files');
    expect(ENGINEERING_OBJECT_MODES['profile-2d']).toEqual(['2d', 'parameters', 'source']);
  });

  it('shows only implemented or already-created applicable modes', () => {
    expect(
      availableEngineeringWorkspaceModes({
        kind: 'part',
        implementedModes: ['3d', 'files', 'source', 'analysis'],
        hasSource: true,
      })
    ).toEqual(['3d', 'source']);
    expect(
      availableEngineeringWorkspaceModes({
        kind: 'part',
        implementedModes: ['3d', 'source', 'analysis'],
        hasSource: false,
        createdModes: ['drawing', 'analysis'],
      })
    ).toEqual(['3d', 'drawing']);
  });

  it('keeps derived outputs revision-linked to their owner', () => {
    expect(DERIVED_ENGINEERING_ARTIFACTS.drawing).toMatchObject({ revisionLinked: true });
    expect(DERIVED_ENGINEERING_ARTIFACTS['assembly-guide'].ownerKinds).toEqual(['assembly']);
  });

  it('offers Source only for an authoritative generator path', () => {
    expect(cadSourcePath('/project/bracket.step.py')).toBe('/project/bracket.step.py');
    expect(cadSourcePath('/project/bracket.stp.py')).toBe('/project/bracket.stp.py');
    expect(cadSourcePath('/project/bracket.py')).toBe('/project/bracket.py');
    expect(cadSourcePath('/project/bracket.step')).toBeNull();
  });
});
