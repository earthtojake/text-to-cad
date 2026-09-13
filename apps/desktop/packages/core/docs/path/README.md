# Path System

`@emdash/core/primitives/path/api` defines Emdash's portable file identity vocabulary. It is
pure TypeScript, browser-safe, and does not perform filesystem I/O.

Use this module when a path crosses a process, renderer, persistence, or Wire
boundary. Runtime adapters remain responsible for converting structured paths
into native strings immediately before filesystem, Git, watcher, or process
spawn operations.

## Concepts

- `HostRef` from `@emdash/core/primitives/host/api` selects a local or remote runtime host.
- `HostAbsolutePath` is a structured absolute path with an explicit root:
  POSIX root, Windows drive, or UNC share.
- `PortableRelativePath` is a normalized `/`-separated coordinate relative to a
  known root. The empty string represents the root.
- `HostFileRef` combines `HostRef` and `HostAbsolutePath` into a routeable file
  address.
- `ScopedPath` combines a root `HostFileRef` and `PortableRelativePath`.
- `ResourceUri` is the versioned string form for serialization and persistence.
- `ResourceKey` is an opaque comparison key for maps and deduplication.

## Basic Flow

```ts
import {
  encodeResourceUri,
  hostFileRef,
  parseAbsolute,
  parsePortableRelativePath,
  resolveScopedPath,
  scopedPath,
} from '@emdash/core/primitives/path/api';
import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';

const rootPath = parseAbsolute('/repo', { profile: { style: 'posix' } });
const relative = parsePortableRelativePath('src/index.ts');

if (rootPath.success && relative.success) {
  const root = hostFileRef(LOCAL_HOST_REF, rootPath.data);
  const scoped = scopedPath(root, relative.data);
  const resolved = resolveScopedPath(scoped);

  if (resolved.success) {
    const uri = encodeResourceUri(resolved.data);
    // emdash-file://v2/local/local/posix/repo/src/index.ts
  }
}
```

`HostFileRef` belongs at routing, persistence, and renderer identity boundaries.
Once a domain controller has selected a host-bound Wire connection, Git and Files
runtime contracts carry `HostAbsolutePath` roots and `PortableRelativePath`
coordinates without repeating `HostRef` in every request.

## Related Pages

- [Normalization](normalization.md)
- [Resources](resources.md)
- [Boundaries](boundaries.md)
- [Recipes](recipes.md)
