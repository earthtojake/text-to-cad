import { describe, expect, it } from 'vitest';
import { baseName, buildOrigin, buildPagePath, fileAddress, normalizeVirtualPath, parseBuildLocation } from './build.ts';

describe('a build link', () => {
  it('names the build and the file, decoded, or nothing of the kind', () => {
    expect(parseBuildLocation('/b/k7Qx2/STEP/bracket.step')).toEqual({ id: 'k7Qx2', path: '/STEP/bracket.step' });
    expect(parseBuildLocation('/b/k7Qx2/STEP/my%20part.step/')).toEqual({ id: 'k7Qx2', path: '/STEP/my part.step' });
    expect(parseBuildLocation('/b/k7Qx2')).toEqual({ id: 'k7Qx2', path: '' });
    expect(parseBuildLocation('/b/k7Qx2/')).toEqual({ id: 'k7Qx2', path: '' });
    expect(parseBuildLocation('/b/k7Qx2/__cad/catalog')).toBeNull();
    expect(parseBuildLocation('/b/__cad/x.step')).toBeNull();
    expect(parseBuildLocation('/b/%ZZ/x.step')).toBeNull();
    expect(parseBuildLocation('/')).toBeNull();
    expect(parseBuildLocation('/account')).toBeNull();
  });
  it('spells the page, the API origin and a file address from one build', () => {
    expect(buildPagePath('k7Qx2', 'STEP/my part.step')).toBe('/b/k7Qx2/STEP/my%20part.step');
    expect(buildOrigin('https://cad.example/', 'k7Qx2')).toBe('https://cad.example/b/k7Qx2');
    expect(fileAddress('https://cad.example', 'k7Qx2', '/STEP/bracket.step')).toBe('https://cad.example/b/k7Qx2/STEP/bracket.step');
    expect(normalizeVirtualPath('//STEP//a.step/')).toBe('/STEP/a.step');
    expect(normalizeVirtualPath('')).toBe('');
    expect(baseName('/STEP/bracket.step')).toBe('bracket.step');
  });
});
