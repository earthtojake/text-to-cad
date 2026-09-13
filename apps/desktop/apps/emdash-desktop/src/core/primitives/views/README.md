# Views

Views are declarative, schema-backed identities. Feature contribution modules
define what a view is; renderer runtime bindings added later define how it is
rendered.

Calling a definition is the only supported way to construct a `ViewRef`:

```ts
export const taskViewDef = defineView({
  id: 'task',
  params: z.object({
    projectId: z.string().min(1),
    taskId: z.string().min(1),
  }),
  layout: workbenchLayout,
  historyKey: ({ taskId }) => taskId,
});

const ref = taskViewDef({ projectId, taskId });
```

The schema validates params at construction. `safeRef()` is the boundary for
untrusted values such as persisted navigation state: invalid params return
`undefined`, while zod's normal object behavior strips unknown keys. Parse
failures are intentionally dropped rather than migrated. `safeRef(undefined)`
treats the missing input as `{}`, so it succeeds only when the params schema
accepts an empty object.

Definitions whose params are all optional can be called without an argument
(`homeViewDef()`). Definitions with any required param require an argument.

## Identity and locations

`ViewRef.key` combines the stable view id with the definition's `historyKey`.
Views without a `historyKey` are singleton history places, even when their
non-identity params differ.

A location describes a history-significant place inside a view, such as the
active task tab. Location schemas are best-effort and unversioned. An invalid
persisted location may be discarded while retaining its view ref; unlike
mementos, locations do not use `defineVersionedSchema`.

## Subjects and mementos

A definition may project validated params to a domain `Subject`. This is a
bridge to subject-scoped mementos and entity cleanup, not a navigation-derived
storage key. Memento identity remains `(mementoId, subject.kind, subject.key)`.

## Invariants

- Contribution modules import only primitive APIs, zod, and sibling
  contribution declarations.
- Definitions contain no React components, MobX stores, or renderer/main
  implementations.
- Params and locations are bounded JSON-shaped values.
- Redirects and `safeRef()` misses are domain outcomes, not `Result` failures.
- Runtime registries and navigation engines consume the catalog but do not add
  feature-specific cases.
