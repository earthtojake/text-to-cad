# Recipes

## Parse a Native POSIX Path

```ts
const parsed = parseAbsolute('/home/david/repo/src/index.ts', {
  profile: { style: 'posix' },
});
```

## Parse a Native Windows Path

```ts
const parsed = parseAbsolute('C:\\Users\\David\\repo\\src\\index.ts', {
  profile: { style: 'win32' },
});
```

## Build a Host File Ref

```ts
const host = hostRef('remote', 'connection-1');
const path = parseAbsolute('/repo/src/index.ts', { profile: { style: 'posix' } });

if (path.success) {
  const ref = hostFileRef(host, path.data);
}
```

## Use a Root-Scoped Path

```ts
const root = hostFileRef(LOCAL_HOST_REF, rootPath);
const relative = parsePortableRelativePath('src/index.ts');

if (relative.success) {
  const scoped = scopedPath(root, relative.data);
  const resolved = resolveScopedPath(scoped);
}
```

Use this pattern for watcher events, Git paths, file tree nodes, and bulk file
operations.

## Store a Resource URI

```ts
const uri = encodeResourceUri(ref);
const decoded = decodeResourceUri(uri);
```

Store the URI when a durable string identity is needed. Keep `ResourceKey` for
in-memory maps only.

## Deduplicate with a Resource Key

```ts
const key = resourceKeyFromFileRef(ref, {
  profile: {
    style: 'win32',
    caseSensitivity: 'insensitive',
    unicodeNormalization: 'nfc',
  },
});

modelsByResource.set(key, model);
```

## Convert an Event Under a Watched Root

```ts
const changed = hostFileRef(root.host, changedAbsolutePath);
const relative = relativizeHostFileRef(root, changed);

if (relative.success) {
  const scoped = scopedPath(root, relative.data);
}
```

Batch and coalesce watcher events with resource keys derived from the resolved
file refs, not by string-prefix comparisons.

## Validate a Contract Model

Use structured schemas for contracts instead of ad hoc `z.string()` path fields.

```ts
const readTextInputSchema = z.object({
  file: scopedPathSchema,
  options: readFileOptionsSchema.optional(),
});
```

For root-scoped bulk APIs, keeping root and relative path separate is often more
compact:

```ts
const treePathKeySchema = z.object({
  root: hostAbsolutePathSchema,
  path: portableRelativePathSchema,
  sessionId: z.string(),
});
```

This compact form is appropriate after a domain controller has already selected
the host-bound runtime connection. Use `hostFileRefSchema` instead when the same
payload must still be routed to a host.

For durable UI state, use a resource URI:

```ts
const fileTabStateSchema = z.object({
  resource: resourceUriSchema,
});
```

Only use native absolute input schemas at ingress boundaries:

```ts
const nativePickerInputSchema = z.object({
  path: absolutePathInputSchema({ profile: { style: 'posix' } }),
});
```

## Handle Errors

All parsing helpers return `Result<T, PathError>`.

```ts
const parsed = parsePortableRelativePath(input);
if (!parsed.success) {
  switch (parsed.error.type) {
    case 'invalid-path':
      return parsed.error.message;
    case 'outside-root':
      return 'Path is outside the selected root';
    default:
      return 'Invalid resource';
  }
}
```
