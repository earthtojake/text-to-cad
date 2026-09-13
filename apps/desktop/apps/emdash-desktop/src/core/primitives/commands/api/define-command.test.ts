import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { keybinding } from '@core/primitives/keybindings/api';
import { defineCommand, type CommandInput, type CommandOutput } from './define-command';

describe('defineCommand', () => {
  it('creates a frozen definition with void input by default', () => {
    const command = defineCommand({
      id: 'app.settings',
      title: 'Open Settings',
      category: 'App',
    });

    expect(command.input.safeParse(undefined).success).toBe(true);
    expect(Object.isFrozen(command)).toBe(true);
    expectTypeOf<CommandInput<typeof command>>().toEqualTypeOf<void>();
  });

  it('infers input and output from the schema', () => {
    const command = defineCommand({
      id: 'task.createBranch',
      title: 'Create Branch',
      category: 'Git',
      input: z.object({
        branchName: z.string().trim(),
        baseRef: z.string(),
      }),
    });

    expectTypeOf<CommandInput<typeof command>>().toEqualTypeOf<{
      branchName: string;
      baseRef: string;
    }>();
    expectTypeOf<CommandOutput<typeof command>>().toEqualTypeOf<{
      branchName: string;
      baseRef: string;
    }>();
  });

  it('preserves a portable keybinding definition', () => {
    const binding = keybinding.settings('settings', 'Mod+,');
    const command = defineCommand({
      id: 'app.settings',
      title: 'Open Settings',
      category: 'App',
      keybinding: binding,
    });

    expect(command.keybinding).toBe(binding);
  });

  it('rejects an empty command id', () => {
    expect(() =>
      defineCommand({
        id: ' ',
        title: 'Invalid',
        category: 'Test',
      })
    ).toThrow('A command id must not be empty');
  });
});
