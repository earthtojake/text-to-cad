import { z } from 'zod';

export type PlatformKey = 'darwin' | 'win32' | 'linux';

export type PlatformConfig = {
  openCommands?: string[];
  openUrls?: string[];
  checkCommands?: string[];
  bundleIds?: string[];
  appNames?: string[];
  // Free-form mdfind query (darwin only). App is considered installed if the
  // query returns any results. Use when bundleIds/appNames can't distinguish
  // the app (e.g., stable and Canary share a bundle ID but differ in display name).
  mdfindQuery?: string;
  // Windows only: detect and launch via `vswhere.exe` (the canonical Visual Studio
  // locator). `devenv.exe` is rarely on PATH, so availability is resolved by running
  // `vswhere -latest -property productPath` and launching the resolved devenv.exe.
  winVswhere?: boolean;
  label?: string;
  iconPath?: string;
};

type OpenInAppConfigShape = {
  id: string;
  label: string;
  iconPath: (typeof ICON_PATHS)[keyof typeof ICON_PATHS];
  invertInDark?: boolean;
  alwaysAvailable?: boolean;
  hideIfUnavailable?: boolean;
  autoInstall?: boolean;
  supportsRemote?: boolean;
  platforms: Partial<Record<PlatformKey, PlatformConfig>>;
};

const ICON_PATHS = {
  finder: 'finder.png',
  explorer: 'explorer.svg',
  files: 'files.svg',
  cursor: 'cursor.svg',
  vscode: 'vscode.png',
  vscodium: 'vscodium.png',
  windsurf: 'windsurf.png',
  xcode: 'xcode.png',
  terminal: 'terminal.png',
  kaku: 'kaku.png',
  alacritty: 'alacritty.svg',
  hyper: 'hyper.svg',
  warp: 'warp.png',
  iterm2: 'iterm2.png',
  ghostty: 'ghostty.png',
  kitty: 'kitty.png',
  termy: 'termy.svg',
  zed: 'zed.png',
  trae: 'trae.png',
  'intellij-idea': 'intellij-idea.svg',
  'android-studio': 'android-studio.svg',
  'android-studio-canary': 'android-studio-canary.svg',
  webstorm: 'webstorm.svg',
  phpstorm: 'phpstorm.svg',
  pycharm: 'pycharm.svg',
  rubymine: 'rubymine.svg',
  rustrover: 'rustrover.svg',
  rider: 'rider.svg',
  athas: 'athas.svg',
  kiro: 'kiro.png',
  antigravity: 'antigravity.png',
  'visual-studio': 'visual-studio.svg',
} as const;

const _OPEN_IN_APPS = {
  finder: {
    id: 'finder',
    label: 'Finder',
    iconPath: ICON_PATHS.finder,
    alwaysAvailable: true,
    // AppService opens the platform file manager via Electron shell.openPath.
    platforms: {
      win32: {
        label: 'Explorer',
        iconPath: ICON_PATHS.explorer,
      },
      linux: {
        label: 'Files',
        iconPath: ICON_PATHS.files,
      },
    },
  },
  cursor: {
    id: 'cursor',
    label: 'Cursor',
    iconPath: ICON_PATHS.cursor,
    invertInDark: true,
    autoInstall: true,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: ['command -v cursor >/dev/null 2>&1 && cursor .', 'open -a "Cursor" .'],
        checkCommands: ['cursor'],
        appNames: ['Cursor'],
      },
      win32: {
        openCommands: ['cursor {{path}}'],
        checkCommands: ['cursor'],
      },
      linux: {
        openCommands: ['cursor {{path}}'],
        checkCommands: ['cursor'],
      },
    },
  },
  vscode: {
    id: 'vscode',
    label: 'VS Code',
    iconPath: ICON_PATHS.vscode,
    autoInstall: true,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v code >/dev/null 2>&1 && code {{path}}',
          'open -n -b com.microsoft.VSCode --args {{path}}',
          'open -n -a "Visual Studio Code" {{path}}',
        ],
        checkCommands: ['code'],
        bundleIds: ['com.microsoft.VSCode', 'com.microsoft.VSCodeInsiders'],
        appNames: ['Visual Studio Code'],
      },
      win32: {
        openCommands: ['code {{path}}', 'code-insiders {{path}}'],
        checkCommands: ['code', 'code-insiders'],
      },
      linux: {
        openCommands: ['code {{path}}', 'code-insiders {{path}}'],
        checkCommands: ['code', 'code-insiders'],
      },
    },
  },
  vscodium: {
    id: 'vscodium',
    label: 'VSCodium',
    iconPath: ICON_PATHS.vscodium,
    autoInstall: true,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v codium >/dev/null 2>&1 && codium {{path}}',
          'open -n -b com.vscodium --args {{path}}',
          'open -n -a "VSCodium" {{path}}',
        ],
        checkCommands: ['codium'],
        bundleIds: ['com.vscodium'],
        appNames: ['VSCodium'],
      },
      win32: {
        openCommands: ['codium {{path}}'],
        checkCommands: ['codium'],
      },
      linux: {
        openCommands: ['codium {{path}}'],
        checkCommands: ['codium'],
      },
    },
  },
  windsurf: {
    id: 'windsurf',
    label: 'Windsurf',
    iconPath: ICON_PATHS.windsurf,
    autoInstall: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v windsurf >/dev/null 2>&1 && windsurf {{path}}',
          'open -n -b com.exafunction.windsurf --args {{path}}',
          'open -n -a "Windsurf" {{path}}',
        ],
        checkCommands: ['windsurf'],
        bundleIds: ['com.exafunction.windsurf'],
        appNames: ['Windsurf'],
      },
      win32: {
        openCommands: ['windsurf {{path}}'],
        checkCommands: ['windsurf'],
      },
      linux: {
        openCommands: ['windsurf {{path}}'],
        checkCommands: ['windsurf'],
      },
    },
  },
  xcode: {
    id: 'xcode',
    label: 'Xcode',
    iconPath: ICON_PATHS.xcode,
    platforms: {
      darwin: {
        openCommands: [
          'command -v xed >/dev/null 2>&1 && xed {{path}}',
          'open -n -b com.apple.dt.Xcode --args {{path}}',
          'open -n -a "Xcode" {{path}}',
        ],
        checkCommands: ['xed'],
        bundleIds: ['com.apple.dt.Xcode'],
        appNames: ['Xcode'],
      },
    },
  },
  terminal: {
    id: 'terminal',
    label: 'Terminal',
    iconPath: ICON_PATHS.terminal,
    alwaysAvailable: true,
    supportsRemote: true,
    platforms: {
      darwin: { openCommands: ['open -a Terminal {{path}}'] },
      win32: {
        openCommands: ['wt -d {{path}}', 'start cmd /K "cd /d {{path_raw}}"'],
      },
      linux: {
        openCommands: [
          'x-terminal-emulator --working-directory={{path}}',
          'gnome-terminal --working-directory={{path}}',
          'konsole --workdir {{path}}',
        ],
      },
    },
  },
  kaku: {
    id: 'kaku',
    label: 'Kaku',
    iconPath: ICON_PATHS.kaku,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v kaku >/dev/null 2>&1 && kaku start --cwd {{path}}',
          'open -na "Kaku" --args start --cwd {{path}}',
        ],
        checkCommands: ['kaku'],
        appNames: ['Kaku'],
      },
      linux: {
        openCommands: ['kaku start --cwd {{path}}'],
        checkCommands: ['kaku'],
      },
    },
  },
  alacritty: {
    id: 'alacritty',
    label: 'Alacritty',
    iconPath: ICON_PATHS.alacritty,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v alacritty >/dev/null 2>&1 && alacritty --working-directory {{path}}',
          'open -n -b org.alacritty --args --working-directory {{path}}',
          'open -na "Alacritty" --args --working-directory {{path}}',
        ],
        checkCommands: ['alacritty'],
        bundleIds: ['org.alacritty'],
        appNames: ['Alacritty'],
      },
      win32: {
        openCommands: [
          'start "" alacritty --working-directory "{{path_raw}}"',
          'alacritty --working-directory "{{path_raw}}"',
        ],
        checkCommands: ['alacritty'],
      },
      linux: {
        openCommands: ['alacritty --working-directory {{path}}'],
        checkCommands: ['alacritty'],
      },
    },
  },
  hyper: {
    id: 'hyper',
    label: 'Hyper',
    iconPath: ICON_PATHS.hyper,
    supportsRemote: true,
    // Hyper has no cwd flag (vercel/hyper#1213); a path arg is ignored. Best-effort
    // via exec cwd on linux/win32; macOS opens in Hyper's default dir.
    platforms: {
      darwin: {
        openCommands: ['open -na "Hyper"'],
        checkCommands: ['hyper'],
        bundleIds: ['co.zeit.hyper'],
        appNames: ['Hyper'],
      },
      win32: {
        openCommands: ['hyper'],
        checkCommands: ['hyper'],
      },
      linux: {
        openCommands: ['hyper'],
        checkCommands: ['hyper'],
      },
    },
  },
  warp: {
    id: 'warp',
    label: 'Warp',
    iconPath: ICON_PATHS.warp,
    supportsRemote: true,
    platforms: {
      darwin: {
        openUrls: [
          'warp://action/new_window?path={{path_url}}',
          'warppreview://action/new_window?path={{path_url}}',
        ],
        bundleIds: ['dev.warp.Warp-Stable'],
        appNames: ['Warp'],
      },
    },
  },
  iterm2: {
    id: 'iterm2',
    label: 'iTerm2',
    iconPath: ICON_PATHS.iterm2,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'open -b com.googlecode.iterm2 {{path}}',
          'open -a "iTerm" {{path}}',
          'open -a "iTerm2" {{path}}',
        ],
        bundleIds: ['com.googlecode.iterm2'],
        appNames: ['iTerm', 'iTerm2'],
      },
    },
  },
  ghostty: {
    id: 'ghostty',
    label: 'Ghostty',
    iconPath: ICON_PATHS.ghostty,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: ['open -b com.mitchellh.ghostty {{path}}', 'open -a "Ghostty" {{path}}'],
        bundleIds: ['com.mitchellh.ghostty'],
        appNames: ['Ghostty'],
      },
      linux: {
        openCommands: ['ghostty --working-directory={{path}}'],
        checkCommands: ['ghostty'],
      },
    },
  },
  kitty: {
    id: 'kitty',
    label: 'Kitty',
    iconPath: ICON_PATHS.kitty,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'open -n -b net.kovidgoyal.kitty --args --directory {{path}}',
          'open -na "kitty" --args --directory {{path}}',
        ],
        bundleIds: ['net.kovidgoyal.kitty'],
        appNames: ['kitty'],
      },
      linux: {
        openCommands: ['kitty --directory {{path}}'],
        checkCommands: ['kitty'],
      },
    },
  },
  termy: {
    id: 'termy',
    label: 'Termy',
    iconPath: ICON_PATHS.termy,
    platforms: {
      darwin: {
        openCommands: [
          'command -v termy >/dev/null 2>&1 && termy --working-directory={{path}}',
          'open -a "Termy" {{path}}',
        ],
        checkCommands: ['termy'],
        appNames: ['Termy'],
      },
      win32: {
        openCommands: ['start "" termy --working-directory={{path}}'],
        checkCommands: ['termy'],
      },
      linux: {
        openCommands: ['termy --working-directory={{path}}'],
        checkCommands: ['termy'],
      },
    },
  },
  zed: {
    id: 'zed',
    label: 'Zed',
    iconPath: ICON_PATHS.zed,
    autoInstall: true,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: ['command -v zed >/dev/null 2>&1 && zed {{path}}', 'open -a "Zed" {{path}}'],
        checkCommands: ['zed'],
        appNames: ['Zed'],
      },
      linux: {
        openCommands: ['zed {{path}}', 'xdg-open {{path}}'],
        checkCommands: ['zed'],
      },
      win32: {
        openCommands: ['zed {{path}}'],
        checkCommands: ['zed'],
      },
    },
  },
  athas: {
    id: 'athas',
    label: 'Athas',
    iconPath: ICON_PATHS.athas,
    autoInstall: true,
    supportsRemote: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v athas >/dev/null 2>&1 && athas {{path}}',
          'open -n -b com.code.athas --args {{path}}',
          'open -n -a "Athas" {{path}}',
        ],
        checkCommands: ['athas'],
        bundleIds: ['com.code.athas'],
        appNames: ['Athas'],
      },
      win32: {
        openCommands: ['athas "{{path_raw}}"'],
        checkCommands: ['athas'],
      },
      linux: {
        openCommands: ['athas {{path}}'],
        checkCommands: ['athas'],
      },
    },
  },
  kiro: {
    id: 'kiro',
    label: 'Kiro',
    iconPath: ICON_PATHS.kiro,
    autoInstall: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v kiro >/dev/null 2>&1 && kiro {{path}}',
          'open -a "Kiro" {{path}}',
        ],
        checkCommands: ['kiro'],
        bundleIds: ['dev.kiro.desktop'],
        appNames: ['Kiro'],
      },
      win32: {
        openCommands: ['kiro {{path}}'],
        checkCommands: ['kiro'],
      },
      linux: {
        openCommands: ['kiro {{path}}'],
        checkCommands: ['kiro'],
      },
    },
  },
  antigravity: {
    id: 'antigravity',
    label: 'Antigravity',
    iconPath: ICON_PATHS.antigravity,
    autoInstall: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v antigravity >/dev/null 2>&1 && antigravity {{path}}',
          'open -a "Antigravity" {{path}}',
        ],
        checkCommands: ['antigravity'],
        appNames: ['Antigravity'],
      },
      win32: {
        openCommands: ['antigravity {{path}}'],
        checkCommands: ['antigravity'],
      },
      linux: {
        openCommands: ['antigravity {{path}}'],
        checkCommands: ['antigravity'],
      },
    },
  },
  trae: {
    id: 'trae',
    label: 'Trae',
    iconPath: ICON_PATHS.trae,
    autoInstall: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v trae >/dev/null 2>&1 && trae {{path}}',
          'open -a "Trae" {{path}}',
        ],
        checkCommands: ['trae'],
        appNames: ['Trae'],
      },
      win32: {
        openCommands: ['trae "{{path_raw}}"'],
        checkCommands: ['trae'],
      },
      linux: {
        openCommands: ['trae {{path}}'],
        checkCommands: ['trae'],
      },
    },
  },
  'trae-solo': {
    id: 'trae-solo',
    label: 'Trae Solo',
    iconPath: ICON_PATHS.trae,
    autoInstall: true,
    platforms: {
      darwin: {
        openCommands: [
          'command -v trae-solo >/dev/null 2>&1 && trae-solo {{path}}',
          'open -a "Trae Solo" {{path}}',
        ],
        checkCommands: ['trae-solo'],
        appNames: ['Trae Solo'],
      },
      win32: {
        openCommands: ['trae-solo "{{path_raw}}"'],
        checkCommands: ['trae-solo'],
      },
      linux: {
        openCommands: ['trae-solo {{path}}'],
        checkCommands: ['trae-solo'],
      },
    },
  },
  'intellij-idea': {
    id: 'intellij-idea',
    label: 'IntelliJ IDEA',
    iconPath: ICON_PATHS['intellij-idea'],
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "IntelliJ IDEA" {{path}}'],
        bundleIds: ['com.jetbrains.intellij'],
        appNames: ['IntelliJ IDEA'],
      },
      win32: {
        openCommands: ['idea64 {{path}}', 'idea {{path}}'],
        checkCommands: ['idea64', 'idea'],
      },
      linux: {
        openCommands: ['idea {{path}}'],
        checkCommands: ['idea'],
      },
    },
  },
  rider: {
    id: 'rider',
    label: 'Rider',
    iconPath: ICON_PATHS.rider,
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "Rider" {{path}}', 'open -a "JetBrains Rider" {{path}}'],
        bundleIds: ['com.jetbrains.rider'],
        appNames: ['Rider', 'JetBrains Rider'],
      },
      win32: {
        openCommands: ['rider64 {{path}}', 'rider {{path}}'],
        checkCommands: ['rider64', 'rider'],
      },
      linux: {
        openCommands: ['rider {{path}}', 'rider.sh {{path}}'],
        checkCommands: ['rider', 'rider.sh'],
      },
    },
  },
  'android-studio': {
    id: 'android-studio',
    label: 'Android Studio',
    iconPath: ICON_PATHS['android-studio'],
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "Android Studio" {{path}}'],
        bundleIds: ['com.google.android.studio'],
        appNames: ['Android Studio'],
      },
      win32: {
        openCommands: ['studio64 {{path}}', 'studio {{path}}'],
        checkCommands: ['studio64', 'studio'],
      },
      linux: {
        openCommands: ['studio {{path}}'],
        checkCommands: ['studio'],
      },
    },
  },
  'android-studio-canary': {
    id: 'android-studio-canary',
    label: 'Android Studio Canary',
    iconPath: ICON_PATHS['android-studio-canary'],
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        // Canary shares bundle ID com.google.android.studio with stable, so we
        // search by display name containing "Canary" (e.g. "Android Studio Otter
        // 3 Feature Drop 2025.2.3 Canary 3.app" or "Android Studio Canary X.Y").
        mdfindQuery:
          'kMDItemCFBundleIdentifier == "com.google.android.studio" && kMDItemDisplayName == "*Canary*"cd',
        openCommands: [
          'CANARY=$(mdfind \'kMDItemCFBundleIdentifier == "com.google.android.studio" && kMDItemDisplayName == "*Canary*"cd\' | head -n 1) && [ -n "$CANARY" ] && open -a "$CANARY" {{path}}',
          'open -a "Android Studio Preview" {{path}}',
        ],
        appNames: ['Android Studio Preview'],
      },
      win32: {
        openCommands: ['studio-preview {{path}}'],
        checkCommands: ['studio-preview'],
      },
      linux: {
        openCommands: ['studio-preview {{path}}'],
        checkCommands: ['studio-preview'],
      },
    },
  },
  phpstorm: {
    id: 'phpstorm',
    label: 'PhpStorm',
    iconPath: ICON_PATHS.phpstorm,
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "PhpStorm" {{path}}'],
        bundleIds: ['com.jetbrains.PhpStorm'],
        appNames: ['PhpStorm'],
      },
      win32: {
        openCommands: ['phpstorm64 {{path}}', 'phpstorm {{path}}'],
        checkCommands: ['phpstorm64', 'phpstorm'],
      },
      linux: {
        openCommands: ['phpstorm {{path}}'],
        checkCommands: ['phpstorm'],
      },
    },
  },
  webstorm: {
    id: 'webstorm',
    label: 'WebStorm',
    iconPath: ICON_PATHS.webstorm,
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "WebStorm" {{path}}'],
        bundleIds: ['com.jetbrains.WebStorm'],
        appNames: ['WebStorm'],
      },
      win32: {
        openCommands: ['webstorm64 {{path}}', 'webstorm {{path}}'],
        checkCommands: ['webstorm64', 'webstorm'],
      },
      linux: {
        openCommands: ['webstorm {{path}}'],
        checkCommands: ['webstorm'],
      },
    },
  },
  pycharm: {
    id: 'pycharm',
    label: 'PyCharm',
    iconPath: ICON_PATHS.pycharm,
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "PyCharm" {{path}}'],
        bundleIds: ['com.jetbrains.pycharm'],
        appNames: ['PyCharm'],
      },
      win32: {
        openCommands: ['pycharm64 {{path}}', 'pycharm {{path}}'],
        checkCommands: ['pycharm64', 'pycharm'],
      },
      linux: {
        openCommands: ['pycharm {{path}}'],
        checkCommands: ['pycharm'],
      },
    },
  },
  rubymine: {
    id: 'rubymine',
    label: 'RubyMine',
    iconPath: ICON_PATHS.rubymine,
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "RubyMine" {{path}}'],
        bundleIds: ['com.jetbrains.rubymine'],
        appNames: ['RubyMine'],
      },
      win32: {
        openCommands: ['rubymine64 {{path}}', 'rubymine {{path}}'],
        checkCommands: ['rubymine64', 'rubymine'],
      },
      linux: {
        openCommands: ['rubymine {{path}}'],
        checkCommands: ['rubymine'],
      },
    },
  },
  rustrover: {
    id: 'rustrover',
    label: 'RustRover',
    iconPath: ICON_PATHS.rustrover,
    hideIfUnavailable: true,
    platforms: {
      darwin: {
        openCommands: ['open -a "RustRover" {{path}}'],
        bundleIds: ['com.jetbrains.rustrover'],
        appNames: ['RustRover'],
      },
      win32: {
        openCommands: ['rustrover64 {{path}}', 'rustrover {{path}}'],
        checkCommands: ['rustrover64', 'rustrover'],
      },
      linux: {
        openCommands: ['rustrover {{path}}'],
        checkCommands: ['rustrover'],
      },
    },
  },
  'visual-studio': {
    id: 'visual-studio',
    label: 'Visual Studio',
    iconPath: ICON_PATHS['visual-studio'],
    hideIfUnavailable: true,
    platforms: {
      // Windows-only IDE. Detected and launched via vswhere (see winVswhere);
      // the `devenv {{path}}` fallback covers setups where devenv.exe is on PATH.
      win32: {
        winVswhere: true,
        openCommands: ['start "" devenv {{path}}'],
        checkCommands: ['devenv'],
      },
    },
  },
} satisfies Record<string, OpenInAppConfigShape>;

export type OpenInAppId = keyof typeof _OPEN_IN_APPS;

export type OpenInAppConfig = OpenInAppConfigShape & { id: OpenInAppId };

// Re-export as a properly typed Record so Object.values() yields OpenInAppConfig[]
// and app.id is narrowed to OpenInAppId throughout the codebase.
export const OPEN_IN_APPS: Record<OpenInAppId, OpenInAppConfig> = _OPEN_IN_APPS as Record<
  OpenInAppId,
  OpenInAppConfig
>;

export const OPEN_IN_APP_IDS = Object.keys(OPEN_IN_APPS) as [OpenInAppId, ...OpenInAppId[]];

export const openInAppIdSchema = z.enum(OPEN_IN_APP_IDS);

export function getAppById(id: string): OpenInAppConfig | undefined {
  return isValidOpenInAppId(id) ? OPEN_IN_APPS[id] : undefined;
}

export function isValidOpenInAppId(value: unknown): value is OpenInAppId {
  return typeof value === 'string' && value in OPEN_IN_APPS;
}

export function getResolvedLabel(app: OpenInAppConfigShape, platform: PlatformKey): string {
  return app.platforms[platform]?.label || app.label;
}

export function getResolvedIconPath(app: OpenInAppConfigShape, platform: PlatformKey): string {
  return app.platforms[platform]?.iconPath || app.iconPath;
}
