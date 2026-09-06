import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';

export const PLATFORMS = ['macos', 'windows', 'linux'] as const;
export type Platform = (typeof PLATFORMS)[number];

export const INSTALL_METHODS = [
  'installer-macos',
  'installer-windows',
  'installer-linux',
  'homebrew',
  'winget',
  'powershell',
  'npm',
  'apt',
  'curl',
  'pip',
  'cargo',
  'other',
] as const;
export const installMethodSchema = z.enum(INSTALL_METHODS);
export type InstallMethod = (typeof INSTALL_METHODS)[number];

export type DependencyStatus = 'available' | 'missing' | 'error';

export const elevationPolicySchema = z.enum(['never', 'always', 'on-failure']);
export type ElevationPolicy = z.output<typeof elevationPolicySchema>;

export interface ProbeResult {
  command: string;
  path: string | null;
  stdout: string;
  stderr: string;
  exitCode: number | null;
  timedOut: boolean;
}

export const hostDependencyUpdateCommandSchema = z.object({
  kind: z.literal('self'),
  args: z.array(z.string()),
});
export type HostDependencyUpdateCommand = z.output<typeof hostDependencyUpdateCommandSchema>;

export const installCommandOptionSchema = z.object({
  method: installMethodSchema,
  command: z.string().min(1),
  packages: z.array(z.string()).optional(),
  label: z.string().optional(),
  recommended: z.boolean().optional(),
  elevation: elevationPolicySchema.default('never'),
  updateCommand: z.string().optional(),
  uninstallCommand: z.string().optional(),
});
export type InstallCommandOption = z.output<typeof installCommandOptionSchema>;
export type InstallCommandOptionInput = z.input<typeof installCommandOptionSchema>;

export const installCommandsSchema = z.partialRecord(
  z.enum(PLATFORMS),
  z.array(installCommandOptionSchema)
);
export type InstallCommands = z.output<typeof installCommandsSchema>;
export type InstallCommandsInput = z.input<typeof installCommandsSchema>;

export const hostDependencyDescriptorSchema = z
  .object({
    id: z.string(),
    /** Binary names to try in order; first success wins. */
    binaryNames: z.array(z.string()).min(1),
    installDocs: z.string().optional(),
    /** Optional install commands, grouped by the host platform they run on. */
    installCommands: installCommandsSchema.optional(),
    /** Optional self-update command run as the selected executable plus these argv tokens. */
    updateCommand: hostDependencyUpdateCommandSchema.optional(),
  })
  .passthrough();
export type HostDependencyDescriptor = z.output<typeof hostDependencyDescriptorSchema>;

export type IHostDependencyBehavior = {
  /**
   * Override the default status resolution logic.
   * Useful for CLIs that exit non-zero on `--version` but are still available.
   */
  resolveStatus?(result: ProbeResult): DependencyStatus;
};

export const hostDependencyCapability = definePluginCapability<IHostDependencyBehavior>()(
  'host-dependency',
  hostDependencyDescriptorSchema
);
