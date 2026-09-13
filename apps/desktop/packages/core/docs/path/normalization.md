# Normalization

Path normalization in Emdash is explicit. Callers choose the dialect they are
parsing instead of inheriting the operating system of the current process.

## Native Absolute Paths

`parseAbsolute()` accepts a `profile` option.

```ts
parseAbsolute('/home/david/repo', { profile: { style: 'posix' } });
parseAbsolute('C:\\Users\\David\\repo', { profile: { style: 'win32' } });
parseAbsolute('\\\\server\\share\\repo', { profile: { style: 'win32' } });
```

POSIX parsing treats backslash as a valid filename character. Windows parsing
treats both `\\` and `/` as separators.

The parser:

- rejects null bytes;
- resolves `.` and `..` lexically;
- rejects paths that escape their root;
- preserves Unicode spelling by default and normalizes only when requested;
- preserves path spelling and casing for display;
- uppercases Windows drive letters in the structured root.

The parser does not:

- call `realpath()`;
- check whether the path exists;
- authorize access;
- turn a POSIX backslash into a separator.

## Portable Relative Paths

`PortableRelativePath` is used for scoped coordinates such as file tree keys,
Git paths, watcher events, and root-relative Wire payloads.

Rules:

- `/` is the separator.
- The empty string is the root.
- Leading `/`, Windows drive roots, and UNC roots are rejected.
- `.` and `..` are resolved lexically; escaping the root is rejected.
- Backslash is a literal character, not a separator.
- Null bytes are rejected.

```ts
parsePortableRelativePath('src/./components/../index.ts');
// => 'src/index.ts'

parsePortableRelativePath('../outside');
// => invalid-path
```

## Comparison

Stored paths preserve spelling. Equality and deduplication use comparison keys
created from an explicit `PathProfile`.

```ts
const semantics = createPathSemantics({
  style: 'win32',
  caseSensitivity: 'insensitive',
  unicodeNormalization: 'nfc',
});
```

Do not lowercase or otherwise rewrite stored paths to make comparison easier.
Use `ResourceKey` or `PathSemantics.comparisonKey()` for maps and sets.
