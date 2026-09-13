import { describe, expect, it } from 'vitest';
import { chord, code } from './chord';
import { findConflicts, type KeybindingEntry } from './conflicts';
import { keybinding } from './define-keybinding';

const linux = { os: 'linux' } as const;

describe('findConflicts', () => {
  it('classifies fixed, same-group, and cross-group collisions', () => {
    const entries: KeybindingEntry[] = [
      {
        id: 'candidate',
        group: 'task',
        binding: keybinding.settings('candidate', 'Mod+J'),
      },
      {
        id: 'reserved',
        group: 'window',
        binding: keybinding.fixed('Mod+J'),
      },
      {
        id: 'same-group',
        group: 'task',
        binding: keybinding.settings('sameGroup', 'Mod+J'),
      },
      {
        id: 'outer',
        group: 'window',
        binding: keybinding.settings('outer', 'Mod+J'),
      },
    ];

    expect(findConflicts(entries, chord('Mod+J'), 'candidate', {}, linux)).toEqual([
      { severity: 'reserved', id: 'reserved' },
      { severity: 'error', id: 'same-group' },
      { severity: 'shadowing', id: 'outer' },
    ]);
  });

  it('compares against effective overridden chords and excludes the target', () => {
    const entries: KeybindingEntry[] = [
      {
        id: 'candidate',
        group: 'task',
        binding: keybinding.settings('candidate', 'Mod+J'),
      },
      {
        id: 'other',
        group: 'task',
        binding: keybinding.settings('other', 'Mod+K'),
      },
    ];

    expect(findConflicts(entries, chord('Mod+J'), 'candidate', { other: 'Mod+J' }, linux)).toEqual([
      { severity: 'error', id: 'other' },
    ]);
  });

  it('treats explicit unbinding as conflict-free', () => {
    const entries: KeybindingEntry[] = [
      { id: 'candidate', binding: keybinding.settings('candidate', 'Mod+J') },
      { id: 'other', binding: keybinding.settings('other', 'Mod+J') },
    ];

    expect(findConflicts(entries, chord('Mod+J'), 'candidate', { other: null }, linux)).toEqual([]);
  });

  it('treats collisions with ungrouped commands as shadowing', () => {
    const entries: KeybindingEntry[] = [
      {
        id: 'candidate',
        groups: ['task'],
        binding: keybinding.settings('candidate', 'Mod+J'),
      },
      {
        id: 'ungrouped',
        binding: keybinding.settings('ungrouped', 'Mod+J'),
      },
    ];

    expect(findConflicts(entries, chord('Mod+J'), 'candidate', {}, linux)).toEqual([
      { severity: 'shadowing', id: 'ungrouped' },
    ]);
  });

  it('uses the US reference layout for build-time cross-kind conflicts', () => {
    const entries: KeybindingEntry[] = [
      { id: 'candidate', group: 'window', binding: keybinding.settings('candidate', 'Mod+[') },
      {
        id: 'positional',
        group: 'window',
        binding: keybinding.settings('positional', code(['Mod'], 'BracketLeft')),
      },
    ];

    expect(findConflicts(entries, chord('Mod+['), 'candidate', {}, linux)).toEqual([
      { severity: 'error', id: 'positional' },
    ]);
  });

  it('uses the supplied layout for runtime cross-kind conflicts', () => {
    const entries: KeybindingEntry[] = [
      { id: 'candidate', group: 'window', binding: keybinding.settings('candidate', 'Mod+[') },
      {
        id: 'positional',
        group: 'window',
        binding: keybinding.settings('positional', code(['Mod'], 'BracketLeft')),
      },
    ];

    const germanLayout = new Map([['BracketLeft', 'ü']]);
    expect(findConflicts(entries, chord('Mod+['), 'candidate', {}, linux, germanLayout)).toEqual(
      []
    );
    expect(findConflicts(entries, chord('Mod+Ü'), 'candidate', {}, linux, germanLayout)).toEqual([
      { severity: 'error', id: 'positional' },
    ]);
  });

  it('detects overlapping multi-scope groups and reserved system chords', () => {
    const entries: KeybindingEntry[] = [
      {
        id: 'candidate',
        groups: ['window', 'modal'],
        binding: keybinding.settings('candidate', 'Mod+K'),
      },
      {
        id: 'same-scope',
        groups: ['modal'],
        binding: keybinding.settings('sameScope', 'Mod+K'),
      },
      {
        id: 'system.hide',
        groups: [],
        binding: keybinding.fixed('Mod+H'),
      },
    ];

    expect(findConflicts(entries, chord('Mod+K'), 'candidate', {}, { os: 'mac' })).toEqual([
      { severity: 'error', id: 'same-scope' },
    ]);
    expect(findConflicts(entries, code(['Mod'], 'KeyH'), 'candidate', {}, { os: 'mac' })).toEqual([
      { severity: 'reserved', id: 'system.hide' },
    ]);
  });

  it('rejects a target id outside the supplied entries', () => {
    expect(() => findConflicts([], chord('Mod+K'), 'missing', {}, linux)).toThrow(
      'Unknown keybinding entry: missing'
    );
  });
});
