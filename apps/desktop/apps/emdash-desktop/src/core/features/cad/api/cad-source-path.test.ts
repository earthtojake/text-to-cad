import { describe, expect, it } from 'vitest';
import {
  cadSourcePanelPresentation,
  canonicalCadModelPathForLegacySource,
  isEditableCadSourcePath,
  isLegacyCadSourcePath,
  migratedCadSourcePath,
} from './cad-source-path';

describe('legacy CAD source paths', () => {
  it('maps retired double-suffix sources to the plain source and canonical model', () => {
    expect(isLegacyCadSourcePath('models/bracket.step.py')).toBe(true);
    expect(migratedCadSourcePath('models/bracket.step.py')).toBe('models/bracket.py');
    expect(canonicalCadModelPathForLegacySource('models/bracket.step.py')).toBe(
      'models/bracket.step'
    );
    expect(migratedCadSourcePath('models/bracket.STP.PY')).toBe('models/bracket.py');
    expect(canonicalCadModelPathForLegacySource('models/bracket.STP.PY')).toBe(
      'models/bracket.STP'
    );
  });

  it('does not mistake an ordinary cadgen model for a legacy source', () => {
    expect(isLegacyCadSourcePath('models/bracket.py')).toBe(false);
    expect(migratedCadSourcePath('models/bracket.py')).toBeNull();
    expect(canonicalCadModelPathForLegacySource('models/bracket.py')).toBeNull();
  });

  it('allows every Python filename; cadgen validates the program on rebuild', () => {
    expect(isEditableCadSourcePath('models/bracket.step.py')).toBe(true);
    expect(isEditableCadSourcePath('models/bracket.stp.py')).toBe(true);
    expect(isEditableCadSourcePath('models/bracket.py')).toBe(true);
    expect(isEditableCadSourcePath('models/bracket.step')).toBe(false);
  });

  it('uses honest legacy and canonical source labels', () => {
    expect(cadSourcePanelPresentation('models/bracket.step.py')).toEqual({
      readOnly: false,
      subtitle: 'Model recipe · rebuilds canonical STEP · ⌘S to save',
    });
    expect(cadSourcePanelPresentation('models/bracket.py')).toEqual({
      readOnly: false,
      subtitle: 'Model recipe · rebuilds canonical STEP · ⌘S to save',
    });
  });
});
