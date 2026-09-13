# Keybindings

Keybindings are portable definitions of keyboard gestures. This primitive owns
validation, canonicalization, typed authoring, override resolution, conflict
classification, and display. Commands and view scopes consume it later; it
does not execute commands itself.

## Chord grammar

Canonical chords use the tinykeys grammar and `$mod` alias:

- Character tokens such as `$mod+K` match `KeyboardEvent.key`. Use them for
  mnemonic bindings such as save, open, and search.
- Code tokens such as `$mod+BracketLeft` match `KeyboardEvent.code`. Use them
  for positional punctuation and navigation bindings.
- Named keys such as `Escape`, `$mod+ArrowLeft`, and `F5` have equivalent
  key/code semantics.

Use `code()` to author positional bindings:

```ts
const back = code(['Mod'], 'BracketLeft');
```

`KEY_CODES` is the source of truth for both the `KeyCode` type and runtime
validation. Chords using `Alt` with a printable key must use a code token,
because macOS Option combinations change `event.key`. Sequences are not
supported yet.

Tinykeys provides `parseKeybinding` and `matchKeybindingPress`. The primitive
adds strict validation because tinykeys otherwise accepts typos that never
match. App commands resolve through the window dispatcher and active view-scope
path. `useChordKeydown` is reserved for component-local keyboard behavior.

## Bindings and settings

Bindings distinguish system-owned and configurable policy structurally:

```ts
const close = keybinding.fixed('Escape');

const navigateBack = keybinding.settings(
  'navigateBack',
  code(['Mod'], 'BracketLeft')
);
```

Defaults live in code. Settings persist only overrides:

- missing key: use the default;
- string: use that chord;
- `null`: explicitly unbound.

Resetting deletes the override. Legacy `Mod+K` strings normalize to `$mod+K`
at the read boundary. Invalid stored values fall back to the default instead
of throwing. Fixed bindings have no settings key and therefore cannot be
overridden.

The recorder stores code tokens for printable keys and named keys as-is.
Recording the effective default clears the override rather than persisting a
no-op customization.

## Conflicts

`findConflicts()` returns one of:

- `reserved`: collision with a fixed binding;
- `error`: configurable collision in the same group;
- `shadowing`: collision across groups.

Char/code comparisons need a layout. Catalog checks use `CODE_TO_US_CHAR` for
deterministic CI behavior. The recorder uses the current layout map when one is
available.

## Layout and dispatch boundaries

Layout never changes binding resolution. `KeyboardLayoutService` uses
`navigator.keyboard.getLayoutMap()` only to display code tokens in terms of
the current keyboard layout and to supply runtime conflict translation.

The dispatcher has one window listener. It pre-parses bindings with tinykeys,
collects every command whose press matches, and asks the scope tree to resolve
exactly once. Collect-then-resolve prevents a char and code binding for the same
keystroke from firing twice. Per-binding repeat and text-input gating happens
before resolution, and `preventDefault()` happens only after a command resolves
successfully.

## Downstream command integration

Command definitions should import `Keybinding`, `keybinding`, and `code` from
`@core/primitives/keybindings/api`. Positional defaults for navigate back,
navigate forward, and split pane use `BracketLeft`, `BracketRight`, and
`Backslash` code tokens; mnemonic bindings remain char strings. Native menu
accelerators and browser shortcut claims derive from the same resolved chords
used by the dispatcher.
