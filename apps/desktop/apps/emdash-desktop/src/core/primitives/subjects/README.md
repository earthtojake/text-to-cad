# Subjects

A subject is a typed name for one domain-owned identity. Mementos use subjects to
scope state and to delete all state associated with an entity without knowing
which contributors stored it.

A subject value contains only its stable wire identity:

```ts
type Subject = {
  kind: string;
  key: string;
};
```

It deliberately does not contain domain data, services, lifecycle methods, or a
parent/child relationship. UI hierarchy changes must not change persisted keys.

## Defining a subject

Define concrete subjects in the owning feature's declarative
`contributions/subject.ts` module:

```ts
import { defineSubject } from '@core/primitives/subjects/api';
import { z } from 'zod';

export const taskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string().uuid() }),
  encode: ({ taskId }) => taskId,
  retention: {
    maxAge: 90 * 24 * 60 * 60 * 1_000,
    maxEntries: 1_000,
  },
});
```

Calling the definition validates and encodes a domain key:

```ts
const subject = taskSubject({ taskId });
// { kind: 'task', key: taskId }
```

The callable definition also exposes:

- `kind`, used to bind memento definitions and locate React providers;
- `keySchema`, the domain key's Zod schema;
- `encode(key)`, for deterministic key generation;
- `is(subject)`, a kind-level type guard;
- optional kind-level retention defaults.

Use `appSubject({})` for state that belongs to the application rather than a
particular domain entity.

## Key requirements

An encoded key must be:

- deterministic for the entity's entire lifetime;
- independent of navigation and component hierarchy;
- safe to send over wire and store as SQLite text;
- unambiguous within its `kind`.

Do not use mutable labels, array indexes, routes, view IDs, or filesystem paths
that can change while the entity remains the same.

## What subjects are not

Subjects are identity values, not domain objects. Do not add:

- data loading or accessors;
- event subscriptions;
- parent pointers;
- cleanup behavior;
- mutable state.

Lifecycle operations consume subjects. For example,
`MementoClient.deleteBySubject(taskSubject({ taskId }))` removes every memento
owned by that task, regardless of which features defined those mementos.
For bulk maintenance, `deleteOrphans(taskSubject.kind, validEncodedKeys)` removes
state for domain entities that no longer exist.
