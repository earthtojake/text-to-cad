import { describe, expect, it } from 'vitest';
import { basenameFromAnyPath, safePathSegment } from './path-name';

describe('path-name helpers', () => {
  describe('basenameFromAnyPath', () => {
    it('extracts a project name from a Windows path', () => {
      expect(basenameFromAnyPath('E:\\my_work\\github_pro\\emdash')).toBe('emdash');
    });

    it('extracts a project name from a POSIX path', () => {
      expect(basenameFromAnyPath('/home/admin/github_pro/emdash')).toBe('emdash');
    });

    it('ignores trailing path separators', () => {
      expect(basenameFromAnyPath('E:\\my_work\\github_pro\\emdash\\')).toBe('emdash');
      expect(basenameFromAnyPath('/home/admin/github_pro/emdash/')).toBe('emdash');
    });
  });

  describe('safePathSegment', () => {
    it('keeps normal project names unchanged', () => {
      expect(safePathSegment('emdash')).toBe('emdash');
    });

    it('collapses path-shaped project names to a safe single segment', () => {
      expect(safePathSegment('E:\\my_work\\github_pro\\emdash')).toBe('emdash');
      expect(safePathSegment('../emdash')).toBe('emdash');
    });

    it('falls back when no safe segment remains', () => {
      expect(safePathSegment('///', 'project-id')).toBe('project-id');
    });

    it('falls back for Windows reserved device names', () => {
      expect(safePathSegment('NUL', 'project-id')).toBe('project-id');
      expect(safePathSegment('com1', 'project-id')).toBe('project-id');
    });
  });
});
