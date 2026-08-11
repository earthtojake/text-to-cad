# smui — Terminal Theme for the CAD Viewer UI

Local copy of the **smui** ("spacemolt") design system
(<https://smui.statico.io/skill.md>), adapted for the text-to-cad CAD Viewer.
smui is a Nord-inspired terminal aesthetic for shadcn/ui with light and dark
modes: sharp edges, monospace everything. Read this whole document before
restyling viewer UI.

The design rules below are kept agnostic so they transfer to any shadcn/ui app.
The **"In this app"** section is the only viewer-specific part — most notably,
this app keeps **translucent frosted-glass surfaces** instead of smui's flat
opaque panels, because viewer panels float over a live 3D scene.

---

## In this app (text-to-cad viewer)

This app is **Vite + Tailwind v4**, not Next.js, so ignore the upstream
`next/font` and `next-themes` instructions — the equivalents here are:

- **Tokens live in [`viewer/src/client/styles/globals.css`](../../src/client/styles/globals.css).**
  The shadcn CSS variables are set directly in `:root` (light "Snow Storm") and
  `.dark` (dark "Polar Night"); the Tailwind v4 `@theme inline` block maps them
  to utilities and sets `--radius` to `0`. Do **not** run `npx shadcn add` —
  edit `globals.css` by hand.
- **Font (app divergence): this app does NOT adopt smui's monospace.** It keeps
  the viewer's previous typeface — `--font-sans: "IBM Plex Sans", "Aptos",
  "Segoe UI", sans-serif`. So skip smui's "monospace everything" rule and the
  JetBrains Mono setup; everything else (palette, sharp edges) still applies.
- **Light/dark** is driven by the viewer's own color-scheme system, which
  toggles the `.dark` class on `<html>` — no `next-themes`.

### App modification: translucent frosted-glass surfaces

smui ships **flat, opaque** surfaces. This app intentionally keeps its
**frosted-glass** look so the 3D model shows through panels. Honor that:

- Surfaces read their background from `--ui-glass-surface` / `--ui-glass-popover`
  / `--ui-glass-control`, which are **translucent** (`color-mix(... <pct>%,
  transparent)`) and tinted by the smui `--sidebar` / `--popover` / `--background`
  tokens. They are applied through the `cad-glass-surface`, `cad-glass-popover`,
  and `cad-glass-control` classes, which also add `backdrop-filter: blur(...)`.
- **Do not** hardcode opaque panel backgrounds (`bg-card`, `bg-sidebar`, solid
  hex) on the sidebar shell, popovers, or floating toolbars — use the
  `cad-glass-*` classes / `--ui-glass-*` tokens so translucency + blur are kept.
- Surfaces that are **not** over the 3D scene (dialogs, menus on a solid
  backdrop) can use the solid smui tokens normally.
- The upstream per-scene `data-glass-tone` overrides were removed — they used
  monochrome white/black translucency that washed out the Nord palette. The
  glass tint now comes straight from the smui tokens regardless of scene tone.

Everything below this section is the agnostic smui guide.

---

## Core Rules

1. **Light + dark mode.** `:root` = light (Snow Storm), `.dark` = dark (Polar
   Night). All CSS variables have light/dark variants — just toggle the `.dark`
   class.
2. **Zero border radius.** `--radius: 0rem`. All components have sharp corners.
   The only `rounded-full` elements are status dots, toggle knobs, and avatars.
3. **Monospace everything.** JetBrains Mono is the only font. No serif, no
   sans-serif. *(This app diverges — it keeps its previous sans-serif font; see
   "In this app".)*
4. **No emoji.** Use [lucide-react](https://lucide.dev/) icons instead.
5. **Labels are uppercase.** Labels, card titles, and status text use
   `uppercase` with wide letter-spacing.
6. **(This app) Surfaces over the 3D scene are translucent frosted glass.**
   See "In this app" above.

## Color Palette

> Exact values applied here are the source of truth in `globals.css`; the tables
> below are the smui reference (a couple of hexes differ by a shade).

### Semantic Variables (shadcn)

Dark mode (`.dark`):

| Variable | Hex | Usage |
|---|---|---|
| `--background` | `#1a1e24` | Page background |
| `--foreground` | `#d8dee9` | Primary text |
| `--card` | `#21262e` | Card/panel backgrounds |
| `--primary` | `#88c0d0` | Primary accent (frost blue) |
| `--muted-foreground` | `#8e99a8` | Secondary/muted text |
| `--border` | `#3b4252` | Borders |
| `--destructive` | `#d4737c` | Error/danger |

Light mode (`:root`):

| Variable | Hex | Usage |
|---|---|---|
| `--background` | `#eceff4` | Page background (Snow Storm 3) |
| `--foreground` | `#2e3440` | Primary text (Polar Night 1) |
| `--card` | `#e5e9f0` | Card/panel backgrounds (Snow Storm 2) |
| `--primary` | `#4c6d94` | Primary accent (darkened for contrast) |
| `--muted-foreground` | `#48505c` | Secondary/muted text |
| `--border` | `#c9cfda` | Borders |
| `--destructive` | `#a3303d` | Error/danger |

### Extended SMUI Colors

Raw HSL triplets. Use with `hsl()` and optional alpha:
`text-[hsl(var(--smui-green))]`, `border-[hsl(var(--smui-yellow)/0.3)]`,
`bg-[hsl(var(--smui-frost-2)/0.04)]`.

| Variable | Hex | Usage |
|---|---|---|
| `--smui-frost-1` | `#8fbcbb` | Teal accent |
| `--smui-frost-2` | `#88c0d0` | Primary frost blue (= `--primary`) |
| `--smui-frost-3` | `#81a1c1` | Steel blue |
| `--smui-frost-4` | `#4c6d94` | Deep blue |
| `--smui-green` | `#a3be8c` | Success, online, nominal |
| `--smui-yellow` | `#ebcb8b` | Warning, standby, caution |
| `--smui-orange` | `#d08770` | Alert, degraded |
| `--smui-red` | `#d4737c` | Critical, error, danger |
| `--smui-purple` | `#b48ead` | Info, special, rare |

> Not registered in this app's `globals.css` yet. To enable `bg-smui-*` /
> `text-smui-*` utilities, add the `--smui-*` HSL vars to `:root`/`.dark` and the
> `@theme inline` block from "Extended Palette in Tailwind" below.

### Surface Hierarchy

Four background levels for depth (values differ light/dark):

Dark (Polar Night): `--smui-surface-0` `#1a1e24` (page) · `-1` `#21262e` (cards)
· `-2` `#282e37` (elevated) · `-3` `#2f3640` (highlights/active).

Light (Snow Storm): `--smui-surface-0` `#eceff4` · `-1` `#e5e9f0` · `-2`
`#d8dee9` · `-3` `#c8ced9`.

> In this app, panels over the 3D scene draw from the translucent `--ui-glass-*`
> tokens rather than these opaque surfaces — see "In this app".

## Typography Patterns

### Typography Scale

| Tailwind Class | Size | Usage |
|---|---|---|
| `text-label` | 11px | Labels, badges, status text |
| `text-ui` | 13px | Buttons, nav, table body |
| `text-xs` | 12px | Card titles, small text |
| `text-sm` | 14px | Body text, list items |
| `text-heading` | 22px | Section headings |
| `text-stat` | 26px | Big stat numbers |
| `text-hero` | 42px | Hero display text |

Register the custom sizes in Tailwind v4:

```css
@theme {
  --text-label: 11px;
  --text-ui: 13px;
  --text-heading: 22px;
  --text-stat: 26px;
  --text-hero: 42px;
}
```

### Recurring Class Patterns

- **Card title:** `text-xs text-muted-foreground tracking-[1.5px] uppercase font-normal`
- **Field label:** `text-label text-muted-foreground tracking-[1.5px] uppercase block mb-1`
- **Status/role text:** `text-label text-muted-foreground tracking-wider`
- **Big stat number:** `text-stat font-medium text-foreground tracking-tight`
- **Status badge:** `text-label tracking-wider uppercase px-1.5 py-px border text-[hsl(var(--smui-green))] border-[hsl(var(--smui-green)/0.3)]`
- **Section eyebrow:** `text-xs text-muted-foreground tracking-[2px] uppercase mb-1.5`

## Component Patterns

### Card Structure

Use `card-glow` for the hover-border effect:

```tsx
<Card className="card-glow">
  <CardHeader className="flex flex-row items-center justify-between py-2.5 px-3.5">
    <CardTitle className="text-xs text-muted-foreground tracking-[1.5px] uppercase font-normal">
      section title
    </CardTitle>
    <CardDescription className="text-xs text-muted-foreground flex items-center gap-1">
      <span className="inline-block w-[5px] h-[5px] rounded-full bg-[hsl(var(--smui-green))]" />
      status
    </CardDescription>
  </CardHeader>
  <CardContent>{/* content */}</CardContent>
</Card>
```

### Status Colors in Alerts

```tsx
{/* Info — frost blue */}
<Alert className="border-[hsl(var(--smui-frost-2)/0.25)] bg-[hsl(var(--smui-frost-2)/0.04)] [&>svg]:text-[hsl(var(--smui-frost-2))]">
{/* Warning — yellow */}
<Alert className="border-[hsl(var(--smui-yellow)/0.25)] bg-[hsl(var(--smui-yellow)/0.04)] [&>svg]:text-[hsl(var(--smui-yellow))]">
{/* Success — green */}
<Alert className="border-[hsl(var(--smui-green)/0.25)] bg-[hsl(var(--smui-green)/0.04)] [&>svg]:text-[hsl(var(--smui-green))]">
{/* Error — variant="destructive" */}
<Alert variant="destructive">
```

### Status Dot

```tsx
<span className="inline-block w-[5px] h-[5px] rounded-full bg-[hsl(var(--smui-green))]" />
```

### Utility CSS

```css
.card-glow { transition: border-color 0.15s; }
.card-glow:hover { border-color: hsl(var(--smui-border-hover)); }

::selection {
  background: hsl(193 44% 67% / 0.2);
  color: hsl(193 44% 67%);
}
```

## Extended Palette in Tailwind

Register colors in `globals.css` so you can use `bg-smui-frost-2`,
`text-smui-red`, etc.:

```css
@theme inline {
  --color-smui-frost-1: hsl(var(--smui-frost-1));
  --color-smui-frost-2: hsl(var(--smui-frost-2));
  --color-smui-frost-3: hsl(var(--smui-frost-3));
  --color-smui-frost-4: hsl(var(--smui-frost-4));
  --color-smui-red: hsl(var(--smui-red));
  --color-smui-orange: hsl(var(--smui-orange));
  --color-smui-yellow: hsl(var(--smui-yellow));
  --color-smui-green: hsl(var(--smui-green));
  --color-smui-purple: hsl(var(--smui-purple));
  --color-smui-surface-0: hsl(var(--smui-surface-0));
  --color-smui-surface-1: hsl(var(--smui-surface-1));
  --color-smui-surface-2: hsl(var(--smui-surface-2));
  --color-smui-surface-3: hsl(var(--smui-surface-3));
  --color-smui-border-hover: hsl(var(--smui-border-hover));
}
```

## tailwind-merge Fix

Custom text sizes conflict with tailwind-merge. Extend the app's `cn()`
(`viewer/src/client/ui/utils`):

```ts
import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": ["text-label", "text-ui", "text-heading", "text-stat", "text-hero"],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

## Quick Reference

- Theme: light + dark, Nord-inspired, zero radius, monospace (this app keeps its
  own sans-serif font — see below).
- Primary accent: dark `#88c0d0` / light `#4c6d94` (frost blue).
- Status: green=success, yellow=warning, red=error, purple=info.
- Labels: always uppercase with wide tracking.
- Cards: use `card-glow`, `py-2.5 px-3.5` header padding.
- No emoji — use lucide-react icons.
- **This app:** translucent frosted-glass surfaces over the 3D scene; keeps its
  previous sans-serif font (not JetBrains Mono); tokens in `globals.css`; Vite +
  Tailwind v4 (no next/font, no next-themes).
- Live examples: <https://smui.statico.io>
