import { describe, expect, it } from 'vitest';
import { loadConfig } from '../server/config.ts';
import { sha256Hex } from '../server/ids.ts';
import { normalizePath, parseBuildRef, validateBuild, validateSnapshotArgs } from '../server/validate.ts';

const limits = loadConfig({ CLOUD_AUTH: 'dev', CLOUD_MAX_FILES: '4', CLOUD_MAX_INPUT_BYTES: '100' }).limits;

describe('paths', () => {
  it('keeps normalized relative paths and drops ./', () => {
    expect(normalizePath('src/bracket.py')).toBe('src/bracket.py');
    expect(normalizePath('./src/bracket.py')).toBe('src/bracket.py');
  });

  it.each([
    ['../escape.py', /stay inside/],
    ['src/../../x.py', /stay inside/],
    ['/etc/passwd', /absolute/],
    ['C:/model.py', /absolute/],
    ['src\\model.py', /backslash/],
    ['src//model.py', /empty folder/],
    ['src/', /empty folder/],
    ['src/a\u0000.py', /control character/],
    ['.cadgen/store', /reserved/],
    ['src/.cadgen-cache/x', /reserved/],
    ['', /empty/],
  ])('refuses %j', (raw, message) => {
    expect(() => normalizePath(raw)).toThrow(message);
  });
});

describe('build requests', () => {
  const base = {
    files: [
      { path: 'src/a.py', sha256: sha256Hex('a'), bytes: 1 },
      { path: 'src/b.py', sha256: sha256Hex('b'), bytes: 1 },
    ],
    entry: ['src/a.py'],
    pythonpath: ['src'],
    title: 'Base',
  };

  it('decodes text and base64 files and checks the entry', () => {
    const valid = validateBuild({ files: { 'src/a.py': 'print(1)', 'vendor/m.step': { base64: Buffer.from('STEP').toString('base64') } }, entry: 'src/a.py' }, null, limits);
    expect(new TextDecoder().decode(valid.added.get('vendor/m.step'))).toBe('STEP');
    expect(valid.entry).toEqual(['src/a.py']);
  });

  it('edits a base build: changed files, deletions, and its entry by default', () => {
    const valid = validateBuild({ base: 'x', files: { 'src/a.py': 'new' }, delete: ['src/b.py'] }, base, limits);
    expect([...valid.added.keys()]).toEqual(['src/a.py']);
    expect(valid.kept).toEqual([]);
    expect(valid.entry).toEqual(['src/a.py']);
    expect(valid.pythonpath).toEqual(['src']);
    expect(valid.title).toBe('Base');
  });

  it.each([
    [{ files: { 'a.py': 'x' } }, /no entry and no CAD file to show/],
    [{ files: { 'a.py': 'x' }, entry: 'b.py' }, /not one of the build's files/],
    [{ files: { 'a.txt': 'x' }, entry: 'a.txt' }, /not a Python script/],
    [{ files: {}, entry: 'a.py' }, /files is empty/],
    [{ files: { 'a.py': { base64: 'not base64!' } }, entry: 'a.py' }, /not valid base64/],
    [{ files: { 'a.py': 'x', 'a.py/b': 'y' }, entry: 'a.py' }, /both a file and a folder/],
    [{ files: { 'A.py': 'x', 'a.py': 'y' }, entry: 'a.py' }, /differ only by case/],
    [{ files: { 'a.py': 'x' }, entry: 'a.py', delete: ['b.py'] }, /name the build in base/],
  ])('refuses %j', (input, message) => {
    expect(() => validateBuild(input, null, limits)).toThrow(message);
  });

  it('takes no entry for a build that only publishes CAD files', () => {
    expect(validateBuild({ files: { 'robot.urdf': '<robot name="r"/>' } }, null, limits).entry).toEqual([]);
    expect(validateBuild({ files: { 'parts/motor.step': 'ISO-10303-21;' }, entry: '' }, null, limits).entry).toEqual([]);
    expect(validateBuild({ base: 'x', files: { 'parts/motor.step': 'ISO' }, entry: [] }, base, limits).entry).toEqual([]);
  });

  it('enforces the file count and size caps', () => {
    const files = Object.fromEntries(['a', 'b', 'c', 'd', 'e'].map((name) => [`${name}.py`, 'x']));
    expect(() => validateBuild({ files, entry: 'a.py' }, null, limits)).toThrow(/at most 4 files/);
    expect(() => validateBuild({ files: { 'a.py': 'x'.repeat(101) }, entry: 'a.py' }, null, limits)).toThrow(/at most 100 bytes/);
  });

  it('refuses deleting what the base does not have', () => {
    expect(() => validateBuild({ base: 'x', delete: ['nope.py'] }, base, limits)).toThrow(/does not have/);
  });
});

describe('snapshot arguments', () => {
  it('passes the allowed flags through', () => {
    expect(validateSnapshotArgs(['--display', 'render', '--camera=iso', '--view-labels', '--width', '800'])).toEqual(['--display', 'render', '--camera=iso', '--view-labels', '--width', '800']);
  });

  it.each([
    [['--job', 'x.json'], /not allowed/],
    [['--video', '{}'], /not allowed/],
    [['out.png'], /not allowed/],
    [['--width', '100000'], /16 to 4096/],
    [['--camera'], /needs a value/],
  ])('refuses %j', (args, message) => {
    expect(() => validateSnapshotArgs(args)).toThrow(message);
  });
});

describe('build references', () => {
  it('reads an id or a link with a file and selector', () => {
    expect(parseBuildRef('abcdefghABCDEFGH')).toEqual({ id: 'abcdefghABCDEFGH', path: null });
    expect(parseBuildRef('https://cad.example/b/abcdefghABCDEFGH/STEP/my%20part.step#o1.f2')).toEqual({ id: 'abcdefghABCDEFGH', path: 'STEP/my part.step' });
    expect(() => parseBuildRef('https://cad.example/x/y')).toThrow(/not a build id/);
  });
});
