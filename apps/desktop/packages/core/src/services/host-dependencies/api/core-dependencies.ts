import type { HostDependencyDefinition } from '#primitives/host-dependencies/api';
import { aptInstallCommand } from './apt-commands';

const aptInstallOption = (packages: string) => ({
  method: 'apt' as const,
  command: aptInstallCommand(packages.split(' ')),
  packages: packages.split(' '),
  recommended: true,
  elevation: 'always' as const,
});

export const GIT_DEPENDENCY_DESCRIPTOR: HostDependencyDefinition = {
  id: 'git',
  name: 'Git',
  category: 'core',
  binaryNames: ['git'],
  installDocs: 'https://git-scm.com/downloads',
  installCommands: {
    macos: [
      { method: 'homebrew', command: 'brew install git', recommended: true, elevation: 'never' },
    ],
    linux: [aptInstallOption('git')],
    windows: [
      {
        method: 'winget',
        command: 'winget install --id Git.Git',
        recommended: true,
        elevation: 'never',
      },
    ],
  },
  status: 'active',
};

export const RIPGREP_DEPENDENCY_DESCRIPTOR: HostDependencyDefinition = {
  id: 'ripgrep',
  name: 'Ripgrep',
  category: 'core',
  binaryNames: ['rg'],
  installDocs: 'https://github.com/BurntSushi/ripgrep#installation',
  installCommands: {
    macos: [
      {
        method: 'homebrew',
        command: 'brew install ripgrep',
        recommended: true,
        elevation: 'never',
      },
    ],
    linux: [aptInstallOption('ripgrep')],
    windows: [
      {
        method: 'winget',
        command: 'winget install --id BurntSushi.ripgrep.MSVC',
        recommended: true,
        elevation: 'never',
      },
    ],
  },
  status: 'active',
};

export const NODE_DEPENDENCY_DESCRIPTOR: HostDependencyDefinition = {
  id: 'node',
  name: 'Node.js',
  category: 'core',
  binaryNames: ['node'],
  installDocs: 'https://nodejs.org/en/download',
  installCommands: {
    macos: [
      { method: 'homebrew', command: 'brew install node', recommended: true, elevation: 'never' },
    ],
    linux: [aptInstallOption('nodejs npm')],
    windows: [
      {
        method: 'winget',
        command: 'winget install --id OpenJS.NodeJS.LTS',
        recommended: true,
        elevation: 'never',
      },
    ],
  },
  status: 'active',
};

export const NPM_DEPENDENCY_DESCRIPTOR: HostDependencyDefinition = {
  id: 'npm',
  name: 'npm',
  category: 'core',
  binaryNames: ['npm'],
  installDocs: 'https://docs.npmjs.com/downloading-and-installing-node-js-and-npm',
  installCommands: {
    macos: [
      { method: 'homebrew', command: 'brew install node', recommended: true, elevation: 'never' },
    ],
    linux: [aptInstallOption('npm')],
    windows: [
      {
        method: 'winget',
        command: 'winget install --id OpenJS.NodeJS.LTS',
        recommended: true,
        elevation: 'never',
      },
    ],
  },
  status: 'active',
};

export const TMUX_DEPENDENCY_DESCRIPTOR: HostDependencyDefinition = {
  id: 'tmux',
  name: 'tmux',
  category: 'core',
  binaryNames: ['tmux'],
  installDocs: 'https://github.com/tmux/tmux/wiki/Installing',
  installCommands: {
    macos: [
      { method: 'homebrew', command: 'brew install tmux', recommended: true, elevation: 'never' },
    ],
    linux: [aptInstallOption('tmux')],
  },
  status: 'active',
};

export const CURL_DEPENDENCY_DESCRIPTOR: HostDependencyDefinition = {
  id: 'curl',
  name: 'curl',
  category: 'core',
  binaryNames: ['curl'],
  installDocs: 'https://curl.se/download.html',
  installCommands: {
    linux: [aptInstallOption('curl')],
    windows: [
      {
        method: 'winget',
        command: 'winget install --id cURL.cURL',
        recommended: true,
        elevation: 'never',
      },
    ],
  },
  status: 'active',
};

export const REQUIRED_CORE_DEPENDENCIES: HostDependencyDefinition[] = [
  GIT_DEPENDENCY_DESCRIPTOR,
  RIPGREP_DEPENDENCY_DESCRIPTOR,
];

export const RECOMMENDED_CORE_DEPENDENCIES: HostDependencyDefinition[] = [
  NODE_DEPENDENCY_DESCRIPTOR,
  NPM_DEPENDENCY_DESCRIPTOR,
  TMUX_DEPENDENCY_DESCRIPTOR,
  CURL_DEPENDENCY_DESCRIPTOR,
];

export const CORE_DEPENDENCIES: HostDependencyDefinition[] = [
  ...REQUIRED_CORE_DEPENDENCIES,
  ...RECOMMENDED_CORE_DEPENDENCIES,
];
