# Navigation

Navigation consumes validated view refs and optional, JSON-shaped locations.
`api/` holds the portable contracts plus the persisted navigation/history
mementos; `browser/` owns the navigation engine: the `NavigationStore` and
`NavigationHistoryStore` (contributed to the APP SCOPE via `app-stores.ts`),
the `getNavigation()`/`getNavigationHistory()` selectors, and the React hooks
in `navigation-hooks.ts`.

The store never imports feature manifests: the host bootstrap (renderer
`main.tsx`) seeds the view catalog and the well-known home/settings refs
through `seedNavigationHost()` before the app scope creates the stores. Tests
seed a fake catalog through `testing.ts` (`seedTestNavigationHost`), mirroring
the wire primitive's `seedSliceWire`.

A `NavigationParticipant` lets an active view capture and restore its own
sub-location without teaching the history store about task tabs, editor
selections, or other feature-specific state. Participant attachment returns the
shared `Unsubscribe` lifecycle type.

`Resolution` is deliberately a domain union rather than
`Result<T, E>`. A redirect is an expected navigation outcome, not a failure.
Likewise, a view definition's `safeRef()` returns `undefined` for invalid
untrusted input because callers normally filter or fall back rather than recover
from an error value.
