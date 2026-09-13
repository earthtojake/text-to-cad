# Palette

Palette items opt commands into search and command-palette presentation without
adding renderer concerns to `CommandDef`.

- Contribution modules create portable `PaletteItemDef` values.
- `PALETTE_CATALOG` is the canonical searchable palette inventory.
- Browser code may register a custom renderer by command-definition identity.
- Palette commands must accept `undefined` input because selection is an
  argument-less invocation surface.
