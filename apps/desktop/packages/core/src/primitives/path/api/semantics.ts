import type {
  CaseSensitivity,
  HostAbsolutePath,
  PathProfile,
  PathStyle,
  UnicodeNormalization,
} from './types';

export const POSIX_PATH_PROFILE: PathProfile = {
  style: 'posix',
  caseSensitivity: 'sensitive',
  unicodeNormalization: 'nfc',
};

export const WIN32_PATH_PROFILE: PathProfile = {
  style: 'win32',
  caseSensitivity: 'insensitive',
  unicodeNormalization: 'nfc',
};

export type CreatePathSemanticsOptions = Partial<PathProfile>;

export type PathSemantics = Readonly<{
  profile: PathProfile;
  comparisonKey(path: HostAbsolutePath): string;
  equals(a: HostAbsolutePath, b: HostAbsolutePath): boolean;
  contains(parent: HostAbsolutePath, child: HostAbsolutePath): boolean;
}>;

export function createPathProfile(options: CreatePathSemanticsOptions = {}): PathProfile {
  const style: PathStyle = options.style ?? 'posix';
  return {
    style,
    caseSensitivity: options.caseSensitivity ?? defaultCaseSensitivity(style),
    unicodeNormalization: options.unicodeNormalization ?? 'nfc',
  };
}

export function createPathSemantics(options: CreatePathSemanticsOptions = {}): PathSemantics {
  const profile = createPathProfile(options);
  return {
    profile,
    comparisonKey(path) {
      return comparisonKeyForAbsolutePath(path, profile);
    },
    equals(a, b) {
      return comparisonKeyForAbsolutePath(a, profile) === comparisonKeyForAbsolutePath(b, profile);
    },
    contains(parent, child) {
      const parentKey = comparisonKeyForAbsolutePath(parent, profile);
      const childKey = comparisonKeyForAbsolutePath(child, profile);
      const descendantPrefix = parentKey.endsWith('/') ? parentKey : `${parentKey}/`;
      return childKey === parentKey || childKey.startsWith(descendantPrefix);
    },
  };
}

export function normalizeForProfile(value: string, profile: PathProfile): string {
  const normalized = normalizeUnicode(value, profile.unicodeNormalization);
  return profile.caseSensitivity === 'insensitive'
    ? normalized.toLocaleLowerCase('en-US')
    : normalized;
}

export function comparisonKeyForAbsolutePath(path: HostAbsolutePath, profile: PathProfile): string {
  const normalize = (value: string) => normalizeForProfile(value, profile);
  const segments = path.segments.map(normalize).join('/');
  switch (path.root.kind) {
    case 'posix':
      return `posix:/${segments}`;
    case 'drive':
      return `drive:${normalize(path.root.driveLetter)}:/${segments}`;
    case 'unc':
      return `unc:${normalize(path.root.server)}/${normalize(path.root.share)}/${segments}`;
  }
}

export function normalizeUnicode(value: string, normalization: UnicodeNormalization): string {
  return normalization === 'nfc' ? value.normalize('NFC') : value;
}

function defaultCaseSensitivity(style: PathStyle): CaseSensitivity {
  return style === 'win32' ? 'insensitive' : 'sensitive';
}
