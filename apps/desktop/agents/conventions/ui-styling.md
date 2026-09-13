# UI Styling Conventions

This guide covers the rules and patterns for authoring styles in `packages/ui`.
The system uses [vanilla-extract](https://vanilla-extract.style/) (VE) with CSS `@layer`
ordering, shared recipes, and composition over inheritance.

## Core Principle: One Owner Per Property

Every CSS property on an element should have exactly **one authoritative source** of truth.
When two rules set the same property at the same specificity, source order decides —
which is fragile and hard to reason about.

**Anti-pattern (two owners fighting):**
```ts
// primitive: always sets padding 0.25rem
export const comboboxList = style({ padding: '0.25rem' });
// consumer: also sets padding → source-order roulette
export const list = style({ padding: '0.25rem' });
```

**Correct (single owner):**
```ts
// primitive owns padding; consumer just composes it
// consumer delegates to primitive, no override
<ComboboxList> {/* no extra className needed */}
```

## State = Variant, Not Higher-Specificity Selector

Express component state through `data-*` attributes handled inside the owning
`style()` or `recipe()`, not by adding specificity from the outside.

**Anti-pattern (state via higher specificity):**
```ts
// parent component pushing state into child via specificity escalation
globalStyle(`${someParent} ${childClass}`, { padding: 0 });
```

**Correct (state-owned selector inside the primitive):**
```ts
export const comboboxList = style({
  padding: '0.25rem',
  selectors: {
    '&[data-empty]': { padding: 0 },  // library-owned state drives own style
  },
});
```

## No globalStyle Across Component Boundaries

`globalStyle` with a multi-segment selector that crosses a component boundary
(e.g. `${parentClass} [data-slot="child"]`) creates invisible coupling.
If the child's class changes, the parent silently breaks.

**Anti-pattern (cross-boundary globalStyle):**
```ts
// combobox.css.ts reaching into input-group internals
globalStyle(`${comboboxContent} [data-slot="input-group"]`, {
  borderRadius: 0,
  boxShadow: 'none',
});
```

**Correct (variant prop on the child):**
```ts
// input-group.css.ts adds an "embedded" variant
export const inputGroup = recipe({
  variants: {
    variant: {
      embedded: { borderRadius: 0, boxShadow: 'none' },
    },
  },
});
// consumer passes the variant explicitly
<InputGroup variant="embedded" />
```

## Prefer Composition Over Inheritance

Reuse styles by **composing** `style()` arrays rather than inheriting through
class hierarchies or overrides.

```ts
// compose shared base into component-specific style
export const menuItem = style([
  menuItemBase(),          // shared structural recipe
  {
    selectors: { '&:focus': { backgroundColor: vars.surfaceHover } },
  },
]);
```

VE's `style([...])` merges multiple style objects/classes into one atomic class at
build time. The `recipe()` base also accepts an array:
```ts
recipe({ base: [sharedBase, { componentSpecific: '...' }] })
```

## SVG Sizing: Use svg-helpers

Use the shared helpers from `@styles/effects/svg-helpers.css` instead of hand-rolling
`globalStyle` for SVG sizing.

| Helper | Effect |
|--------|--------|
| `svgContainer` | `svg { pointer-events: none; flex-shrink: 0 }` |
| `svgDefaultSize` | `svg:not([class*='size-']) { width: 1rem; height: 1rem }` |
| `svgSmSize` | `svg:not([class*='size-']) { width: 0.75rem; height: 0.75rem }` |
| `svgTextSize` | same as default (alias for inline text contexts) |

```ts
export const menuItem = style([svgContainer, svgDefaultSize, { /* ... */ }]);
```

## Shared Recipes for Common Patterns

### menuItemBase

`@styles/recipes/menu-item.css` — structural recipe for all list item rows
(DropdownMenu, Select, Combobox, ComboboxPopup).

```ts
import { menuItemBase } from '@styles/recipes/menu-item.css';

export const myItem = style([
  menuItemBase({ trailingIndicator: true, fullWidth: true }),
  { selectors: { '&:focus': { backgroundColor: vars.surfaceHover } } },
]);
```

Variants: `trailingIndicator`, `fullWidth`, `inset`, `muted`.

### popupSurface + popupShadow*

`@styles/recipes/popup-surface.css` — base style for floating popup containers with
the animation keyframe selectors and visual properties already wired up.

```ts
import { popupSurface, popupShadowMd } from '@styles/recipes/popup-surface.css';

export const myMenu = style([
  popupSurface,
  popupShadowMd,
  { minWidth: '12rem', padding: '0.25rem' },
]);
```

Shadow variants: `popupShadowSm` (tooltips, comboboxes), `popupShadowMd` (menus, selects).

### InputGroup variant prop

`InputGroup` accepts a `variant` prop:

- `default` — standalone field with border, shadow, and focus ring
- `embedded` — bottom-border-only divider for use inside popup containers

```tsx
// ComboboxInput uses "embedded" automatically
<InputGroup variant="embedded" />
```

### Input bare prop

`Input` accepts a `bare` boolean that strips its standalone border/shadow/focus ring.
`InputGroupInput` passes `bare` automatically; consumers should not need it directly.

## CSS @layer Discipline

The layer order is: `reset < tokens < base < recipes < utilities`.

- `reset` / `base` — `globalStyle` rules in `reset.css.ts` and `base.css.ts`
- `recipes` — component `style()` and `recipe()` output (target destination)
- `utilities` — `sx()` sprinkles; always overrides component styles

**Migration path:** To place a style in the `recipes` layer, wrap properties inside
`'@layer': { recipes: { ... } }`:

```ts
export const foo = style({
  '@layer': {
    recipes: {
      color: vars.foreground,
      selectors: { '&:hover': { backgroundColor: vars.surfaceHover } },
    },
  },
});
```

> **Important:** Unlayered styles always beat ALL layered styles. The migration must
> be coordinated — mixing layered and unlayered styles for the same property on the
> same element will make the unlayered one always win regardless of intent.
> Migrate an entire property-ownership group at once.

## Overrides Go Through utilities Layer

If a consumer genuinely needs to override a component style (rare), use the
`utilities` layer rather than adding specificity:

```ts
// Correct: opt into utilities layer to predictably win
export const myOverride = style({
  '@layer': {
    utilities: { padding: '0.5rem' },
  },
});
```

Avoid using `!important`. If you find yourself reaching for it, the owning
component should expose a variant or `data-*` hook instead.

## Checklist for New Component Styles

- [ ] One style definition owns each property on the element
- [ ] Interactive states expressed as `data-*`-keyed selectors inside the owning style
- [ ] No `globalStyle` with multi-segment selectors crossing component boundaries
- [ ] SVG sizing via `svgContainer`/`svgDefaultSize`/`svgSmSize` composition
- [ ] Popup containers compose `popupSurface` + a `popupShadow*`
- [ ] List-item rows compose `menuItemBase()`
- [ ] InputGroup inside a popup uses `variant="embedded"`
- [ ] No `!important` — expose a variant or compound variant instead
