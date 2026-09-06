import { describe, expect, it } from 'vitest';
import { isCadFilePath } from './cad-file';

describe('isCadFilePath', () => {
  it.each([
    'bracket.step.py',
    'bracket.stp.py',
    'bracket.STEP',
    'bracket.stp',
    'mesh.stl',
    'print.3mf',
    'scene.glb',
    'drawing.dxf',
    'shape.implicit.js',
  ])('recognizes %s', (path) => {
    expect(isCadFilePath(path)).toBe(true);
  });

  it.each(['notes.md', 'model.ts', 'step.py', 'shape.obj'])(
    'leaves %s in the file editor',
    (path) => {
      expect(isCadFilePath(path)).toBe(false);
    }
  );
});
