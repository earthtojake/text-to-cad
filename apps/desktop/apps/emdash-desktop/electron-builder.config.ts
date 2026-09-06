import type { Configuration } from 'electron-builder';
import {
  assertCadBundleSource,
  assertPackagedCadResources,
  cadExtraResources,
  HARDCORE_REPOSITORY_ROOT,
  resolveTextToCadRoot,
} from './scripts/release/cad-resources.ts';
import {
  APP_ID,
  ARTIFACT_PREFIX,
  PRODUCT_NAME,
} from './src/core/primitives/app-identity/api/app-identity.ts';

// The canonical Text-to-CAD tree this desktop ships: the monorepo root above apps/desktop.
const TEXT_TO_CAD_ROOT = resolveTextToCadRoot();

const config: Configuration = {
  appId: APP_ID,
  productName: PRODUCT_NAME,
  executableName: PRODUCT_NAME,
  directories: { output: 'release' },
  artifactName: `${ARTIFACT_PREFIX}-\${arch}.\${ext}`,
  publish: [
    {
      provider: 'github',
      owner: 'earthtojake',
      repo: 'text-to-cad',
      releaseType: 'draft',
    },
  ],
  generateUpdatesFilesForAllChannels: false,
  beforePack: () => assertCadBundleSource(TEXT_TO_CAD_ROOT, HARDCORE_REPOSITORY_ROOT),
  afterPack: ({ appOutDir }) => assertPackagedCadResources(appOutDir),
  files: ['out/**/*', 'node_modules/**/*', 'drizzle/**/*'],
  extraResources: cadExtraResources(TEXT_TO_CAD_ROOT, HARDCORE_REPOSITORY_ROOT),
  asarUnpack: [
    'out/main/adapters/**',
    'node_modules/better-sqlite3/**',
    'node_modules/node-pty/**',
    'node_modules/@parcel/watcher/**',
    '**/*.node',
  ],
  mac: {
    category: 'public.app-category.developer-tools',
    hardenedRuntime: true,
    entitlements: 'build/entitlements.mac.plist',
    entitlementsInherit: 'build/entitlements.mac.plist',
    extendInfo: {
      NSMicrophoneUsageDescription:
        'Hardcore needs microphone access for voice dictation and voice mode features.',
    },
    target: [
      { target: 'dmg', arch: ['arm64'] },
      { target: 'zip', arch: ['arm64'] },
    ],
    icon: 'src/assets/images/hardcore/hardcore.icns',
    notarize: false,
  },
  dmg: {
    icon: 'src/assets/images/hardcore/hardcore.icns',
    background: 'build/dmg-background.tiff',
    window: { width: 530, height: 319 },
    contents: [
      { x: 132, y: 150, type: 'file' },
      { x: 398, y: 150, type: 'link', path: '/Applications' },
    ],
  },
  linux: {
    category: 'Development',
    icon: 'src/assets/images/hardcore/hardcore.png',
    target: [
      { target: 'AppImage', arch: ['x64'] },
      { target: 'deb', arch: ['x64'] },
      { target: 'rpm', arch: ['x64'] },
    ],
  },
  win: {
    icon: 'src/assets/images/hardcore/hardcore.png',
    target: [
      { target: 'nsis', arch: ['x64'] },
      { target: 'msi', arch: ['x64'] },
    ],
  },
  msi: {
    oneClick: false,
    perMachine: false,
  },
  nsis: {
    differentialPackage: true,
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    perMachine: false,
  },
  npmRebuild: false,
  // Encrypt Chromium's on-disk cookie store (in-app browser logins) with OS-level
  // keys, like Chrome does. One-way: never disable once shipped or existing
  // cookie stores become unreadable.
  electronFuses: {
    enableCookieEncryption: true,
  },
};

export default config;
