# Resources

`HostFileRef` is the canonical application-level file identity:

```ts
type HostFileRef = {
  host: HostRef;
  path: HostAbsolutePath;
};
```

It identifies a logical path on a host. It is not an inode identity. Symlinks,
hard links, and renames are handled by runtime-specific filesystem behavior.

## Host References

`HostRef` is defined by `@emdash/core/primitives/host/api`:

```ts
type HostRef = {
  type: 'local' | 'remote';
  id: string;
};
```

It is used by domain controllers to select a host-bound runtime connection. A
runtime executes on the addressed host and therefore does not need `HostRef` in
its own Git or Files keys.

## Absolute Roots

Structured roots avoid ambiguity across hosts and drives:

```ts
{ kind: 'posix' }
{ kind: 'drive', driveLetter: 'C' }
{ kind: 'unc', server: 'server', share: 'share' }
```

The path segments are stored separately from the root, so `/`, `C:/`, and
`//server/share` cannot be confused.

## Scoped Paths

Use `ScopedPath` when many operations share a root:

```ts
type ScopedPath = {
  root: HostFileRef;
  relative: PortableRelativePath;
};
```

This is the preferred globally addressable shape for watcher events, tree
entries, and batch operations. Host-local runtime contracts use the equivalent
compact shape: a `HostAbsolutePath` root plus `PortableRelativePath` coordinates.

## Resource URIs

`ResourceUri` is the stable string encoding:

```text
emdash-file://v2/local/local/posix/home/david/repo/src/index.ts
emdash-file://v2/remote/connection-1/drive/c/Users/David/repo/src/index.ts
emdash-file://v2/remote/connection-2/unc/server/share/repo/src/index.ts
```

Use it for serialization, persistence, Monaco model identity, and durable
messages. Percent encoding is applied per path segment.

## Contract Schemas

Path schemas live next to the path primitives so Wire/RPC contracts and
persisted models do not duplicate validation rules.

Use:

- `hostFileRefSchema` for a globally addressable file resource.
- `scopedPathSchema` for a file under a known root.
- `portableRelativePathSchema` for Git paths, file tree entry keys, and watcher
  paths that are already scoped by another field.
- `resourceUriSchema` for persisted or Monaco-style string identity.
- `resourceRefFromUriSchema` when a boundary accepts a URI string but internal
  code wants a decoded `HostFileRef`.
- `absolutePathInputSchema(profile)` only at native/user/host ingress
  boundaries.

Schemas delegate to the canonical parsers. For example,
`portableRelativePathSchema` transforms `src/./index.ts` into `src/index.ts`
instead of merely branding the original string.

## Resource Keys

`ResourceKey` is an opaque comparison key for maps and deduplication. It may be
case-insensitive or Unicode-normalized depending on the selected profile.

Do not persist `ResourceKey` as the only representation of a file. It is lossy by
design and may not preserve display spelling.
