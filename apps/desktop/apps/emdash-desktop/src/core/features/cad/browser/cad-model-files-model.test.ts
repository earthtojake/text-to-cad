import { describe, expect, it } from 'vitest';
import {
  cadDefaultSourcePath,
  cadModelDirectory,
  cadModelSourcePath,
  cadModelStemPath,
  isCadModelSourcePath,
  selectCadModelFiles,
} from './cad-model-files-model';

describe('cadModelStemPath', () => {
  it('maps source and generated representations to one logical model', () => {
    expect(cadModelStemPath('/workspace/models/bracket.step.py')).toBe('/workspace/models/bracket');
    expect(cadModelStemPath('/workspace/models/bracket.stp.py')).toBe('/workspace/models/bracket');
    expect(cadModelStemPath('/workspace/models/bracket.py')).toBe('/workspace/models/bracket');
    expect(cadModelStemPath('/workspace/models/bracket.step')).toBe('/workspace/models/bracket');
    expect(cadModelStemPath('C:\\models\\bracket.implicit.mjs')).toBe('C:/models/bracket');
    expect(cadModelDirectory('/workspace/models/bracket.step')).toBe('/workspace/models');
  });
});

describe('cadDefaultSourcePath', () => {
  it('uses the cadgen 0.5 plain-Python source convention', () => {
    expect(isCadModelSourcePath('/workspace/models/bracket.py')).toBe(true);
    expect(isCadModelSourcePath('/workspace/models/bracket.step.py')).toBe(true);
    expect(isCadModelSourcePath('/workspace/models/bracket.stp.py')).toBe(true);
    expect(isCadModelSourcePath('/workspace/models/bracket.step')).toBe(false);
    expect(cadDefaultSourcePath('/workspace/models/bracket.step')).toBe(
      '/workspace/models/bracket.py'
    );
    expect(cadDefaultSourcePath('/workspace/models/bracket.stp')).toBe(
      '/workspace/models/bracket.py'
    );
  });
});

describe('cadModelSourcePath', () => {
  it('uses the linked generator while the canonical STEP is open', () => {
    expect(
      cadModelSourcePath(
        [
          { path: '/workspace/models/bracket.step', type: 'file' },
          { path: '/workspace/models/bracket.step.py', type: 'file' },
        ],
        '/workspace/models/bracket.step',
        '/workspace/models/bracket.step.py'
      )
    ).toBe('/workspace/models/bracket.step.py');
  });

  it('keeps imported STEP geometry honest when no editable source is linked', () => {
    expect(
      cadModelSourcePath(
        [{ path: '/workspace/models/imported.step', type: 'file' }],
        '/workspace/models/imported.step'
      )
    ).toBeNull();
  });

  it('links a cadgen 0.5 STEP to its plain Python model rather than a helper', () => {
    expect(
      cadModelSourcePath(
        [
          { path: '/workspace/models/bracket.step', type: 'file' },
          { path: '/workspace/models/bracket_common.py', type: 'file' },
          { path: '/workspace/models/bracket.py', type: 'file' },
        ],
        '/workspace/models/bracket.step',
        '/workspace/models/bracket.py'
      )
    ).toBe('/workspace/models/bracket.py');
  });

  it('prefers the migrated plain source while a legacy source is retained', () => {
    expect(
      cadModelSourcePath(
        [
          { path: '/workspace/models/bracket.step.py', type: 'file' },
          { path: '/workspace/models/bracket.py', type: 'file' },
          { path: '/workspace/models/bracket.step', type: 'file' },
        ],
        '/workspace/models/bracket.step',
        '/workspace/models/bracket.py'
      )
    ).toBe('/workspace/models/bracket.py');
  });

  it('does not link an imported STEP to an unrelated plain same-stem Python file', () => {
    expect(
      cadModelSourcePath(
        [
          { path: '/workspace/models/vendor.step', type: 'file' },
          { path: '/workspace/models/vendor.py', type: 'file' },
        ],
        '/workspace/models/vendor.step'
      )
    ).toBeNull();
  });
});

describe('selectCadModelFiles', () => {
  it('keeps user-owned model files and hides repository and Jake internals', () => {
    const files = selectCadModelFiles(
      [
        { path: '/workspace/models/bracket.step', type: 'file' },
        { path: '/workspace/models/bracket.step.py', type: 'file' },
        { path: '/workspace/models/bracket.dxf', type: 'file' },
        { path: '/workspace/models/bracket.stl', type: 'file' },
        { path: '/workspace/models/bracket-reference.png', type: 'file' },
        { path: '/workspace/models/bracket.artifact.json', type: 'file' },
        { path: '/workspace/models/__cadgen__/bracket.glb', type: 'file' },
        { path: '/workspace/models/__pycache__/bracket.pyc', type: 'file' },
        { path: '/workspace/packages/bracket.step', type: 'file' },
        { path: '/workspace/models/unrelated.step', type: 'file' },
      ],
      '/workspace/models/bracket.step.py'
    );

    expect(files).toEqual([
      { path: '/workspace/models/bracket.step', name: 'bracket.step', role: 'model' },
      { path: '/workspace/models/bracket.step.py', name: 'bracket.step.py', role: 'source' },
      { path: '/workspace/models/bracket.dxf', name: 'bracket.dxf', role: 'drawing' },
      {
        path: '/workspace/models/bracket-reference.png',
        name: 'bracket-reference.png',
        role: 'reference',
      },
      {
        path: '/workspace/models/bracket.artifact.json',
        name: 'bracket.artifact.json',
        role: 'validation',
      },
      { path: '/workspace/models/bracket.stl', name: 'bracket.stl', role: 'export' },
    ]);
  });

  it('includes model-prefixed evidence from CAD relationship folders', () => {
    const files = selectCadModelFiles(
      [
        { path: '/workspace/models/snapshots/bracket-iso.png', type: 'file' },
        { path: '/workspace/models/analyses/bracket/run-1/analysis.json', type: 'file' },
        { path: '/workspace/models/analyses/bracket/run-1/results.vtk', type: 'file' },
        { path: '/workspace/models/references/bracket-sketch.jpg', type: 'file' },
        { path: '/workspace/models/exports/bracket.3mf', type: 'file' },
        { path: '/workspace/models/snapshots/other-iso.png', type: 'file' },
      ],
      '/workspace/models/bracket.step'
    );

    expect(files.map(({ name, role }) => ({ name, role }))).toEqual([
      { name: 'bracket-sketch.jpg', role: 'reference' },
      { name: 'analysis.json', role: 'analysis' },
      { name: 'results.vtk', role: 'analysis' },
      { name: 'bracket-iso.png', role: 'validation' },
      { name: 'bracket.3mf', role: 'export' },
    ]);
  });
});
