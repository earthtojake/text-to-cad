import { describe, expect, it } from 'vitest';
import { homebrewOption, npmDependency } from './host-dependency';

describe('homebrewOption', () => {
  it('builds a Homebrew install option', () => {
    const opt = homebrewOption({ formula: 'myapp', recommended: true });
    expect(opt).toEqual({
      method: 'homebrew',
      command: 'brew install myapp',
      recommended: true,
      elevation: 'never',
    });
  });

  it('adds the cask flag when requested', () => {
    const opt = homebrewOption({ formula: 'myapp', cask: true });
    expect(opt.command).toBe('brew install --cask myapp');
  });
});

describe('npmDependency', () => {
  const base = { id: 'mytool', package: '@acme/mytool' };

  it('defaults binaryNames to [id]', () => {
    const dep = npmDependency(base);
    expect(dep.binaryNames).toEqual(['mytool']);
  });

  it('respects explicit binaryNames override', () => {
    const dep = npmDependency({ ...base, binaryNames: ['bin1', 'bin2'] });
    expect(dep.binaryNames).toEqual(['bin1', 'bin2']);
  });

  it('carries installDocs when provided', () => {
    const dep = npmDependency({ ...base, installDocs: 'https://example.com/docs' });
    expect(dep.installDocs).toBe('https://example.com/docs');
  });

  it('omits installDocs when not provided', () => {
    const dep = npmDependency(base);
    expect('installDocs' in dep).toBe(false);
  });

  it('carries an optional self-update command', () => {
    const dep = npmDependency({
      ...base,
      updateCommand: { kind: 'self', args: ['upgrade'] },
    });
    expect(dep.updateCommand).toEqual({ kind: 'self', args: ['upgrade'] });
  });

  it('adds npm install options for every platform', () => {
    const dep = npmDependency({ ...base, installFlags: '--ignore-scripts', recommended: true });
    expect(dep.installCommands?.macos?.[0]).toEqual({
      method: 'npm',
      command: 'npm install -g @acme/mytool --ignore-scripts',
      recommended: true,
      elevation: 'on-failure',
    });
    expect(dep.installCommands?.linux?.[0]).toEqual(dep.installCommands?.macos?.[0]);
    expect(dep.installCommands?.windows?.[0]).toEqual(dep.installCommands?.macos?.[0]);
  });

  it('appends platform-specific extra options', () => {
    const extra = homebrewOption({ formula: 'mytool' });
    const dep = npmDependency({ ...base, extraOptions: { macos: [extra] } });
    expect(dep.installCommands?.macos).toEqual([
      {
        method: 'npm',
        command: 'npm install -g @acme/mytool',
        recommended: undefined,
        elevation: 'on-failure',
      },
      extra,
    ]);
  });
});
