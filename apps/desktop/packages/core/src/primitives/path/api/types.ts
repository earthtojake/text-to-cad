import type { HostRef } from '#primitives/host/api/types';

export type Brand<T, Name extends string> = T & { readonly __brand: Name };

export type PortableRelativePath = Brand<string, 'PortableRelativePath'>;
export type ResourceUri = Brand<string, 'ResourceUri'>;
export type ResourceKey = Brand<string, 'ResourceKey'>;

export type PathStyle = 'posix' | 'win32';
export type CaseSensitivity = 'sensitive' | 'insensitive';
export type UnicodeNormalization = 'preserve' | 'nfc';

export type PathProfile = Readonly<{
  style: PathStyle;
  caseSensitivity: CaseSensitivity;
  unicodeNormalization: UnicodeNormalization;
}>;

export type PosixPathRoot = Readonly<{
  kind: 'posix';
}>;

export type DrivePathRoot = Readonly<{
  kind: 'drive';
  driveLetter: string;
}>;

export type UncPathRoot = Readonly<{
  kind: 'unc';
  server: string;
  share: string;
}>;

export type HostPathRoot = PosixPathRoot | DrivePathRoot | UncPathRoot;

export type HostAbsolutePath = Readonly<{
  root: HostPathRoot;
  segments: readonly string[];
}>;

export type HostFileRef = Readonly<{
  host: HostRef;
  path: HostAbsolutePath;
}>;

export type ScopedPath = Readonly<{
  root: HostFileRef;
  relative: PortableRelativePath;
}>;

export type ResourceKeyOptions = Readonly<{
  profile?: Partial<PathProfile>;
}>;

export type HostFileRefComparisonOptions = Readonly<{
  profile?: Partial<PathProfile>;
}>;
