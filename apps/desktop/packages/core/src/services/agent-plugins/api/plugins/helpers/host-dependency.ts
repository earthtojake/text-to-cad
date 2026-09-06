import type {
  HostDependencyDescriptor,
  InstallCommandsInput,
  InstallCommandOption,
  HostDependencyUpdateCommand,
} from '#primitives/host-dependencies/api';
import { installCommandsSchema } from '#primitives/host-dependencies/api';

export function homebrewOption(opts: {
  formula: string;
  cask?: boolean;
  recommended?: boolean;
}): InstallCommandOption {
  const caskFlag = opts.cask ? ' --cask' : '';
  return {
    method: 'homebrew',
    command: `brew install${caskFlag} ${opts.formula}`,
    recommended: opts.recommended,
    elevation: 'never',
  };
}

/** Build a full HostDependencyDescriptor for a globally-installed npm package. */
export function npmDependency(opts: {
  id: string;
  package: string;
  /** Binary names to probe; defaults to [opts.id]. */
  binaryNames?: string[];
  installFlags?: string;
  /** @deprecated Package-manager install metadata is no longer used. */
  versionSuffix?: string;
  recommended?: boolean;
  /** Optional link to documentation shown in the UI. */
  installDocs?: string;
  /** @deprecated Version probes are no longer part of HostDependencies. */
  skipVersionProbe?: boolean;
  /** @deprecated Version probes are no longer part of HostDependencies. */
  versionArgs?: string[];
  extraOptions?: InstallCommandsInput;
  updateCommand?: HostDependencyUpdateCommand;
}): HostDependencyDescriptor {
  const installFlags = opts.installFlags ? ` ${opts.installFlags}` : '';
  const npmInstall: InstallCommandOption = {
    method: 'npm',
    command: `npm install -g ${opts.package}${installFlags}`,
    recommended: opts.recommended,
    elevation: 'on-failure',
  };
  const installCommands = installCommandsSchema.parse({
    macos: [npmInstall, ...(opts.extraOptions?.macos ?? [])],
    linux: [npmInstall, ...(opts.extraOptions?.linux ?? [])],
    windows: [npmInstall, ...(opts.extraOptions?.windows ?? [])],
  });

  return {
    id: opts.id,
    binaryNames: opts.binaryNames ?? [opts.id],
    ...(opts.installDocs ? { installDocs: opts.installDocs } : {}),
    installCommands,
    ...(opts.updateCommand ? { updateCommand: opts.updateCommand } : {}),
  };
}
