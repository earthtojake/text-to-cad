# Layouts

Layouts declare the named slots that a view may fill. They describe workbench
furniture, not navigation state, and contain no React components or runtime
registrations.

## Slot kinds

- `main`: one required component supplied by the active view;
- `optional`: at most one component supplied by the active view;
- `wrapper`: one required component that receives view params and `children`;
- `multi`: an extension point filled by multiple independent contributors.

`multi` slots are part of the declaration vocabulary, but the contribution
registry for their fills is intentionally deferred until there is a concrete
consumer.

```ts
import { defineLayout, slot } from '@core/primitives/layouts/api';

export const fullScreenLayout = defineLayout({
  id: 'full-screen',
  slots: {
    wrap: slot.wrapper(),
    main: slot.main(),
  },
});
```

React bindings derive their required and optional component shape through
`SlotFills` from `@core/primitives/layouts/react`. Layout definitions remain
runtime-independent.

The canonical `workbenchLayout` is exported by the primitive API because
feature contribution modules may depend on primitives but not on another
feature. The workbench contribution surface re-exports that same definition for
discovery alongside its other declarations.
