# Design system

This doc holds the rules for everything below the page's layout: the two scales and their tokens, type, spacing,
colour, surfaces, motion, icons, the one component for each job, and input. It binds every control the viewer draws,
in both apps. A change to a rule changes this doc in the same change. Where things go on the page and how the viewer
behaves is the companion doc, [viewer-ux.md](viewer-ux.md). Code paths are under `packages/ui/src`; `kit/` is
`renderers/kit/`.

## Principles

- **One component per job.** Each job has one component ([Components](#components)), built on the shared primitives
  in `primitives/`. A renderer uses it and extends it, and never draws a copy of its own. Why: a fix made once lands
  everywhere, and a copy drifts.
- **Stock shadcn first.** The primitives are shadcn's components as shipped, at the viewer's scale. A change to how
  one looks or behaves is made in the primitive, never at a call site. Why: the stock components already work with a
  finger and a keyboard.
- **The desktop is the reference.** A phone gets the same components at a second scale ([Two scales](#two-scales)).
  Only the layout differs.
- **Sizes come from tokens.** No pixel size where a token exists, and no `mobile ?` size branch. A new size is a new
  token, in both scales at once.
- **Quiet and dense, after Figma.** Neutral greys, the brand only for state, text told apart by colour and weight, one
  hairline between groups. Nothing is there for decoration: no icon beside a title, no icon on a status screen, no
  motion that says nothing.
- **Even padding.** A box is padded the same across as down. A card's content is 12px in on all four sides; a tab's
  pill is as padded across as above and below its text. Why: uneven padding reads as a mistake.
- **The picture is not the chrome.** What belongs to the picture takes the picture's scheme. What the person works the
  view with keeps the app's theme ([The viewport's scheme](#the-viewports-scheme)).
- **Every word is translated.** Chrome text goes through `useI18n().t`. `i18n/locales/en.js` holds every key and the
  other locales mirror it. Text from a file or the engine shows as written.

## Two scales

The chrome has two scales, a desktop's and a phone's. Both are defined once, as tokens in `styles/globals.css`: `:root`
holds the desktop's values and one switch holds the phone's. Every primitive and shared class reads them.

- **The phone scale applies when the viewer itself is narrower than 600px** (`VIEWER_MOBILE_BREAKPOINT`,
  `file-viewer/responsive.js`). The viewer then says `data-viewer-layout="mobile"`, and one page-wide rule
  (`:root:has([data-viewer-layout="mobile"] …)`) switches every token. Why: a menu or hint portalled out of the viewer
  is the size of the chrome it opened from.
- **Layout follows the viewer's width, never the window's.** Chrome has no `sm:` or `md:` breakpoints, and a narrow
  desktop window works as a phone. A viewer drawn off screen for a picture pins its layout and never flips the switch.
- **Script reads `lib/scale.js`** (`DESKTOP_SCALE`, `PHONE_SCALE`) where it must count pixels, such as a virtual
  list's row height. `scale.test.js` holds it equal to the stylesheet.

| Token (Tailwind) | Desktop | Phone | What uses it |
| --- | --- | --- | --- |
| `--cad-control` (`h-control`, `size-control`) | 28 | 36 | strip and sub-toolbar tiles, navbar buttons, panel tabs and head buttons, panel rows, a tab's actions, Quick Edit's buttons, dropdown triggers, fields |
| `--cad-icon-button` (`size-icon-button`) | 24 | 36 | small icon buttons (a card's X), a settings card's controls, the `xs` button |
| `--cad-row` (`min-h-row`) | 28 | 36 | menu and dropdown items, the panel's tree rows |
| `--cad-row-sm` | 24 | 36 | the explorer's and the name menu's rows |
| `--cad-chip` (`h-chip`) | 20 | 28 | chips |
| `--cad-glyph`, `--cad-glyph-sm` (`size-glyph`, `size-glyph-sm`) | 16, 14 | 18, 16 | a tile's icon; a small button's icon, a chip's X |
| `--cad-pad` (`px-pad`) | 8 | 10 | a control's side padding, a menu item's |
| `--cad-step` (`gap-step`) | 4 | 4 | the gap between neighbouring tiles |
| `--cad-radius-control` (`rounded-control`) | 4 | 6 | a tile's corners |
| `--cad-switch-w` × `--cad-switch-h` | 24 × 14 | 36 × 20 | a switch |
| `--cad-thumb` (`size-thumb`) | 12 | 20 | a slider's thumb |
| `--cad-check` | 14 | 20 | a checkbox |
| `--cad-hit` (`.cad-hit`) | 0 | 36 | the least press area round a small mark, invisible and centred on it |
| `--cad-card-min` | 224 | min(320px, 100vw − 8px) | a settings card's least width |

Some sizes derive from these. The navbar, Preview's bar, the strip and a sub-toolbar are the control + 12 (40; 48 on a
phone). The panel's head row is the control + 4 (32; 40). A tool's menu chevron is half a control wide, and a number
field is the icon button less 2px (22; 34).

The padding rules are the same at both scales. Only layout is a phone's own: the panel is a sheet, tools that do not
fit go into More, Quick Edit spans the view, nothing peeks, no hint opens and row actions always show
([A phone](viewer-ux.md#a-phone)).

Why: the desktop sizes are the reference and stay as they are. A phone is read at arm's length and worked with a
finger, and 36px is Apple's and Material's touch target.

## The type scale

Three interface sizes and one heading, each on a fixed line height, as Figma's interface type is. The Tailwind tokens
are `text-tiny`, `text-xs`, `text-ui` and `text-heading` (`styles/tokens.css`); their values are `globals.css`'s
`--cad-text-*` and `--cad-leading-*`. On a phone every step is 2px larger, so the hierarchy holds.

| Step | Desktop | Phone | Used for |
| --- | --- | --- | --- |
| `text-tiny` | 11/16 | 13/18 | tooltips, shortcut hints, small metadata: the zoom's percentage, the app menu's version, the Home's ages and badges |
| `text-xs` | 12/16 | 14/20 | Quick Edit's chips and buttons, sub-toolbars, the update status, every menu, dropdown list and context menu, the export toast |
| `text-ui` | 13/20 | 15/20 | the navbar and the file's name, dialogs, the Home, Quick Edit's note, the loading step line, status screens. `text-sm` and `text-base` resolve to it |
| `text-heading` | 15/20, 600 | 17/22, 600 | the one heading: the Home's heading where it has no navbar, its welcome title, the CAD app's notice title |
| `--cad-text-panel` | 12/16 | 14/20 | every step inside the panel and the settings cards (below) |

- **No other size.** There is no 10px step, no `text-[Npx]`, and no font size in a stylesheet but the scale's
  variables.
- **One size per surface.** Inside the panel and the settings cards (`[data-panel-surface]`) and a pick's card
  (`[data-detail-card]`), every step resolves to the panel's size. Text there is told apart by colour and weight,
  never by size. A menu portalled out of them keeps the chrome's scale. Why: a heading, a label and a value never
  jump in size, and a pick reads alike in the panel and in its card.
- **A menu item** is its line of `text-xs` in 6px of vertical padding, at least the row tall. The primitives set this;
  no menu or item brings its own size.
- **Weight.** Text is regular. Medium (500) marks a title: the open tab and a lone tab's title, a card's title and its
  section headings, a chip's label, the Home's names. Semibold (600) is the heading step's and a dialog title's.
  Emphasis in a list is colour, never bold; a search's match is `--brand-text` at medium weight.
- **Figures.** Numbers that change or line up are tabular: value fields, the zoom, counts.
- **The picture's own text** keeps its own pixel sizes, never under 10px: the cube's axis letters and square-on face
  names 10px; a measurement's label and the snap chip 10px semibold on a 14px line; a drawn text mark 16, 20 or 28px by
  stroke width. Why: it is part of the picture, not the chrome.
- **Rendering.** While a viewer is on the page, all its text, portalled menus included, uses greyscale antialiasing.
  Why: macOS's subpixel antialiasing draws light text on a dark ground a weight heavier.
- A phone's fields stay at 15px. The page's viewport (`maximum-scale=1`), not a 16px font, stops a phone zooming in.

## Spacing and the panel inset

The spacing scale is 4, 8 and 16px, with 12px for the air round a hairline and for a card's inset. The panel has no
6px or 10px vertical step.

- **The panel inset.** The panel has one horizontal line, `--panel-inset` (16px), on both sides, on a desktop and a
  phone. Every text, glyph and control starts on the left line. Values, switches, sliders and a row's last action end
  on the right line. The navbar's panel toggle puts its icon on the same column. Why: one edge the eye can follow down
  the panel, as Figma's panels have.
- **A box hangs out past the line by its own padding**, so what it holds stays on the line: a row's fill by 8px, a
  tab's pill by 6px, the head's icon buttons by 7px (11px on a phone), a value field by 7px.
- **Nothing inside the body pads itself.** The body pads by the inset; no section, list or row sets side padding.
  `PanelSurface.jsx` hands the rows their geometry (`PANEL_ROW_VARIABLES`: half the inset each for the row's padding
  and its hang, and half the inset less 2px for its actions).
- **The panel's vertical steps.** The body starts 8px under the head. A slider control is 48px: its 28px line, its
  12px band and 8px under it. A settings row is the control tall, with 8px under it before the next control; the
  Animation tab's rows stand 4px apart. A tab's actions row stands 8px under its last control, with 8px under its
  buttons.
- **A card's inset is 12px on all four sides**: the panel inset less the card's 4px gap to the edge it docks to, so a
  card's content stands where the docked panel's does.
- **Over the view**, the strip and the tool stack stand 8px in from the view's edges (`CHROME_INSET_PX`), and the
  corner's zoom 12px (`CORNER_INSET_PX`, 4px more for the shadow below the strip's). A card or a peek stands 4px in
  (`PANEL_PEEK_GAP_PX`). The navbar has 8px of side padding.

#### The panel's head

- The head is one row, the control + 4 tall, 8px below the panel's top.
- **Tab pills** are the control tall, 6px in at each side (`TAB_PAD_PX`), 4px apart (`TAB_GAP_PX`), `rounded-md`. The
  open tab is `bg-accent` with foreground text at medium weight; the others are muted, with `bg-accent/50` and
  foreground text under the pointer. Each pill is as wide as its name at medium weight, so choosing a tab moves
  nothing. A pill never shrinks, truncates, wraps or scrolls.
- **With tabs**, the row has 8px under it and then a full-width 1px rule, level with the strip's bottom edge.
- **One tab is a plain title** on the pills' text line, at medium weight, with no rule under it and no gap kept for
  one: the body's 8px follows the title row directly.
- **The head's icon buttons** (⋯ and search) are the control square with a 14px muted glyph, 4px apart, at the row's
  right end: `bg-accent/50` under the pointer, `bg-accent` while open.
- **The open search replaces the row in place**: the same height, place and padding, with no box (no border, fill or
  ring), its magnifier on the left line and its X's glyph ending on the right line. It keeps the head's rule, or its
  lack of one, so nothing below moves.

What the head holds, and where a fourth tab goes: [The panel](viewer-ux.md#the-panel).

#### Hairlines

- One 1px `bg-border` rule separates groups: between a card's sections, and between blocks of a panel tab (Joints'
  motion and its joints, a board's layers and their Layer display). It spans the content width, with 12px of air to
  the nearest ink on each side. A switch's ink starts 5px into its row and a heading's capitals 4px into their line,
  and the air is measured from them. Why: groups read as groups, with no line between every row.
- A rule never stands between rows. Only two rules run full width: the one under the panel's tabs, and a menu's
  separators.
- A sub-toolbar parts its groups with a 1px vertical rule, 16px tall. Where a phone's row wraps, the rule is hidden
  and keeps its room.

## Colour

Two schemes are in play. The app's theme (System, Light or Dark, chosen in the app menu) colours the chrome. The
viewport's scheme (Display's Background) colours the picture and what belongs to it.

### The palette

The tokens are shadcn's neutral set (`styles/tokens.css`), on greys with no hue, as Figma's and VS Code's themes are.

| Token | Light | Dark | Used for |
| --- | --- | --- | --- |
| `--canvas` | oklch .94 (#ebebeb) | #1e1e1e | the area behind every view, a step under the chrome |
| `--background` | #ffffff | #2c2c2c | the page, the Home, dialogs |
| `--sidebar` | oklch .985 | #2c2c2c | the navbar, the panel, the cards |
| `--popover`, `--card` | #ffffff | oklch .31 | floating chrome, menus, tooltips |
| `--secondary`, `--muted` | oklch .97 | oklch .34 | secondary buttons, chips, quiet fills |
| `--accent`, `--sidebar-accent` | oklch .92 | #444444 | a hover (at 50%), the open tab, an open trigger, a pressed tile |
| `--border`, `--input` | oklch .922 | white at 12% (15%) | rules, borders, field edges |
| `--foreground` | oklch .145 | oklch .985 | text and values |
| `--muted-foreground` | oklch .556 | oklch .75 | labels, details, glyphs (at 70% in a tree) |
| `--primary` | oklch .205 | oklch .922 | the one filled button, a switch or box that is on |
| `--brand`, `--ring` | #249ddd | #62b7ec | focus rings, a focused field's edge |
| `--brand-text` | #2c7197 | #62b7ec | a search's match |
| `--brand-icon` | #1683c7 | #62b7ec | the tool in hand's glyph, the changed dot |
| `--brand-subtle` | the brand 12% into the background | 22% | a selected row's fill |
| `--selection` | the brand at 30% | the same | a text selection |
| `--warning`, `--warning-foreground` | amber | amber | a warning's icon, edge and tint; its words |
| `--destructive`, `--foreground-error` | red | red | an error, a destructive action |
| `--slider-*` | | | the slider's colours ([The slider control](#the-slider-control)) |

- **The canvas is darker than the chrome in both themes**, so the navbar and the panel stand off it.
- **The brand marks focus and state, never an action.** It is the focus ring and a focused field's edge, a text
  selection, a selected row, the tool in hand's glyph, a search's match, the changed dot, the Home's chosen layout
  and its focused card, and the logo. It is never a button's fill and never a link in the chrome; the panel toggle
  stays neutral open or shut. Why: blue says "this is on" only while nothing else is blue.
- `--brand-icon` is at least 3:1 on the pressed fill and on white, the minimum for graphics. `--brand-text` is darker,
  for text. Why: the text blue reads dark and odd on a glyph.
- **A link in the chrome** (the app menu's version, "Made by") is muted `text-tiny` that turns the foreground and
  underlined under the pointer or keyboard focus.
- **The scene's colours are core's**, written once in `@cad/core/lib/viewportTheme.js`: selection #2979ff (more
  saturated than the brand on purpose, as it is read against a model), a selected fill #4f9dff, hover #8dc5ff, a
  selected edge #1a73e8, the box select #2979ff over a 12% fill, and the grid's and the XYZ axes' colours per scheme.
  No view hard-codes one.
- `@cad/core/lib/appTheme.js` writes `--canvas`, `--background` and `--foreground` out once more, for what cannot read
  a stylesheet. Change both together.

### The viewport's scheme

- **Background is the person's choice, the same in every file of the tab** (`viewportBackground`): Light, the default,
  or Dark. Light is a grey gradient down a 3D view (#f4f5f6 to #dfe2e5) and the light canvas (#ebebeb) under a flat
  view. Dark is the dark canvas (#1e1e1e), flat. There is no "follow the app" choice; any other stored value reads as
  Light (`normalizeViewportBackground`). Why: the model area is its own surface, as in a CAD program, and never white,
  so a white part still reads.
- **What belongs to the picture takes the picture's scheme**: the scene, the grid and axes, the cube, labels and the
  hover tip, the corner's zoom and its halo, the loading covers (the view's, and the page's before the view is up),
  the update status, the alert card, and a 2D view's paper. Each is drawn inside a `.light` or `.dark` token scope
  (`ViewFrame.jsx`).
- **Preview's chrome takes its backdrop's scheme**: its bar, its playbar and its "Preparing preview…" cover. The
  backdrop is Preview's Background where that is at least 50% opaque, otherwise the viewport's canvas
  (`backdropScheme`, `kit/tools/PreviewChrome.jsx`).
- **What the person works the view with keeps the app's theme**: chrome on a surface of its own, such as the navbar,
  the strip and sub-toolbars, the panel and the phone's sheet, Quick Edit, the Display card and Preview's Settings
  card, menus, tooltips and dialogs.
- **A page state keeps the app's theme.** A status screen ("CAD is not running", a missing file) has no picture to
  take a Background from, and a host with no viewport loads in the app's theme.
- A picture taken off screen (the Home's) always uses the light viewport, in both themes.
- Tailwind's `dark:` applies inside `.dark` unless a `.light` scope is nearer (`tokens.css`), so a light viewport in a
  dark app draws its light look.

Why: the picture is something to look at and the chrome is something to work with. Each keeps its own ground, so
neither flashes when the other changes.

## Surfaces, layering and motion

Every surface is one of these, defined once (`lib/floatingSurface.js`, `file-viewer/panelPeek.js`). A caller adds
layout, never a surface of its own. Why: chrome reads as chrome over any canvas, light or dark, flat or 3D.

| Surface | How | Look | Used by |
| --- | --- | --- | --- |
| Docked chrome | `bg-sidebar` | opaque, a 1px rule on its inner edge | the navbar, the docked panel, a tab's actions row |
| Floating chrome | `FLOATING_CHROME_SURFACE_CLASS` | the popover colour at 90%, a border, `shadow-md`, `backdrop-blur-sm` | the strip, sub-toolbars, the tool stack's panels, Quick Edit's bar, the bar over picked ink |
| Popups | `FLOATING_SURFACE_CLASS` | the popover colour at 95%, a border, `shadow-sm`, `backdrop-blur-md` | dropdown lists, tool menus, the app menu, the view's menu, the name menu, chip lists |
| Cards | `PANEL_PEEK_CARD_CLASS`, `SettingsCard` | opaque `bg-sidebar`, a border, `shadow-md`, 10px corners, 4px from the edges it docks to | the panel's peek, the Display card, Preview's Settings |
| On the picture | the picture's scheme | the zoom: the foreground at 6% (10% under the pointer, 14% open), haloed; the update status: the background at 95% | the corner's zoom, the update status; Preview's bar has no surface at all |

Corners: a tile is `rounded-control` (4px; 6 on a phone). A bar round tiles takes the tile's radius + 6 (10px; 12),
so the two curves run parallel. Cards are 10px. Other boxes (rows, pills, fields, menus, chips, tooltips) are
`rounded-md` (8px).

### Layering

The view's layers, bottom to top (`kit/shell/ViewFrame.jsx`):

1. **The picture** and everything drawn on it: the canvas, ink, measurements and the hover tip; the corner, the
   host's notice, the loading cover and the alert card; and Preview's bar, card and cover.
2. **The panel**: docked beside the picture, or its peek over it (`z-40`).
3. **The view's top layer** (`data-view-top-layer`, `z-50`): the strip, the sub-toolbar, the tool stack and Quick
   Edit. It stands over the panel where they meet.
4. **The Display card**, on the top layer's z and drawn after it (`SETTINGS_CARD_LAYER_CLASS`), so it covers the
   strip, the corner and the picture.
5. **Portalled popups**, at the page's end on the same z: menus and dropdown lists (a card's own among them),
   tooltips, dialogs and sheets. They stand over everything, cards included.

New chrome joins one of these layers.

### Motion

- **One slide for every card that comes in at an edge**: the panel's peek (from the left), the Display card and
  Preview's Settings (from the right), and the phone's panel sheet (from the left). It slides in over 100ms, eased out
  (`PANEL_PEEK_IN_MS`), and out over 80ms, eased in (`PANEL_PEEK_OUT_MS`), as a transform, so nothing is laid out
  again. The classes live in `file-viewer/panelPeek.js` and nowhere else. A card that leaves is gone at its
  animation's end, or after 180ms (`PANEL_PEEK_EXIT_FALLBACK_MS`). Pinning a peek is instant. Why: one source, so
  every card moves alike, and quick enough that nobody waits for it.
- **Popups** fade and zoom in as shadcn's do (tw-animate's 150ms); dialogs take 200ms. A popup that a quick second
  tap must reach closes with no exit animation: the value dropdown, tool menus, the app menu, chip lists.
- **Small changes of state ease**: colours (`transition-colors`), a chevron's quarter turn (100ms), a switch's thumb.
- **Progress may move; decoration may not.** An indeterminate bar's segment slides (1.15s a pass), the update
  status's spinner turns, and placeholder rows pulse gently. A loading screen has no animated mark or model. Preview's
  cover fades over 300ms as it lifts, and its bar and playbar fade as they come and go.
- **Less motion.** Where the system asks for less motion, cards, peeks and sheets appear and go without sliding,
  Preview's fades are cut, placeholder rows hold still, and an indeterminate bar stands across its track at 45%
  opacity. The host's `reducedMotion` stills the bar too.

## Icons

- **The set is lucide** (`lucide-react`). A glyph is drawn for the viewer only where lucide has none for the job (the
  panel toggle, the display modes' spheres, a board's sides, the pick kinds), on lucide's 24-unit grid with round caps
  and joins.
- **Sizes.** A tile's icon is the glyph token (16px; 18 on a phone). A menu item's icon is 16px. A small tile's or the
  panel head's icon, and a card dropdown's option icon, is 14px. A row's kind glyph and its actions, a dropdown's
  chevron, a card's X and a chip's icon are 12px. A row's kind glyph is drawn at a 1.5 stroke in the muted colour at
  70%. A document's glyph is 16px: lucide's Box for a model, File for any CAD file.
- **No icon for decoration.** An icon is there because it says something the words do not: a tool, a kind, a tone
  (the alert card's red or amber mark). There is none beside a card's title and none on a status screen.
- **An option's icon shows only where it adds information.** In a dropdown's value and list, Projection, Style, Side
  and Background keep their icons; the board's Mode (2D, 3D) has none. Why: an icon of the same words says them twice.
- **Display and Preview are one pair.** Display is the plain orthographic cube on every file, whatever is on screen.
  Preview is a play triangle (`PreviewIcon.jsx`: lucide's path at 15/16 of its size). Both are drawn on the 24-unit
  grid at a 1.45 stroke, so each shows the same 12.5px of ink. Preview's settings button wears the same cube. Why:
  lucide's own Play stood a pixel taller and a third heavier than the cube.
- **The changed dot** (`kit/tools/ChangedDot.jsx`) is a 4px `--brand-icon` dot at the top-right of a tile or a tab's
  name while what it controls is off its default. It moves neither the name nor the tab's width.
- **Open in's marks** are 14px, in the row's muted colour: an app's own single-colour mark where its licence lets the
  package ship it, else lucide's AppWindow; the browser is Globe, the file manager Folder, the default app
  ExternalLink. None is drawn by hand.

## Components

One component for each job. A renderer brings its tools, their rows, its panel's tabs and its document's state, and
builds them from these. The kit never asks which file format it is showing.

| Job | The one component | Where |
| --- | --- | --- |
| A button | `Button`; on a toolbar, `ToolbarButton` | `primitives/button.jsx`, `primitives/toolbar-button.jsx` |
| Picking one value from a list | `ValueDropdown` | `primitives/value-dropdown.jsx` |
| A menu of actions | `DropdownMenu`; a tree row's right-click menu, `ContextMenu` | `primitives/dropdown-menu.jsx`, `primitives/context-menu.jsx` |
| A row of a list | `TreeRowSurface` and its parts | `primitives/tree-row.jsx` |
| A labelled setting in the panel | `PanelSelectRow`, `PanelSwitchRow` | `kit/inspector/panelRows.jsx` |
| A number a slider sets | `SliderField` | `kit/inspector/SliderField.jsx` |
| A number with no range | `FileSheetNumberProperty` | `kit/inspector/FileSheet.js` |
| On or off | `Switch` | `primitives/switch.jsx` |
| A chip | `Badge`, as `ReferenceChips` draws it | `kit/tools/quick-edit/ReferenceChips.jsx` |
| Settings over the view | `SettingsCard` | `kit/view-settings/SettingsCard.jsx` |
| A tab's Reset and Save | `PanelActions` | `kit/inspector/PanelActions.jsx` |
| A tool's row under the strip | `SubToolbar` | `kit/tools/SubToolbar.jsx` |
| A hint | `TooltipHint` | `primitives/tooltip.jsx` |
| A control's label | `FieldLabel` | `primitives/field-label.jsx` |
| A scroll region | `ScrollArea` | `primitives/scroll-area.jsx` |
| Loading | `LoadingStep`, over `Progress` | `loading/LoadingStep.jsx` |
| A status screen | `EmptyState` with a `StatusAction` | `file-viewer/navigation/EmptyState.jsx` |
| A dialog, a sheet | `Dialog` or `AlertDialog`, `Sheet` | `primitives/dialog.jsx`, `primitives/sheet.jsx` |

Two rules hold for every control:

- **Label and value.** A control's label is `FieldLabel`: muted, regular weight, the size of where it stands, and it
  truncates. Its value (the number, the chosen option, a field's text) is the foreground. No control styles its own
  label. Why: Figma's rule; the eye finds the values by their colour.
- **Scrolling.** Every scroll region in the chrome is a `ScrollArea`: thin overlay bars in the theme's colours, shown
  while the pointer is over it. Chrome has no native `overflow-auto` or `overflow-scroll`. The Home is a page and
  scrolls with the platform's scrollbar.

### Buttons

Buttons stay neutral: ghost, outline or secondary. At most one button in a place is filled (`default`, the primary
colour), and only while it can act: Params' Save, Quick Edit's rightmost action. A Save that cannot act is drawn as a
disabled ghost, never as a filled grey that reads as pressable. No button is filled with the brand. A disabled button
is at 50% with no hover (Back and Forward at 40%).

| Kind | How | Look |
| --- | --- | --- |
| A toolbar tile | `ToolbarButton`, `TOP_STRIP_BUTTON_CLASS` | the control square, `rounded-control`, the glyph token; the glyph muted at rest; `sidebar-accent` under the pointer (in dark, the foreground at 10%) |
| The tool in hand | `ToolbarButton active` | the neutral pressed fill (in dark, the foreground at 16%), its glyph `--brand-icon`, no hint |
| A tool with a menu | the tile and `ToolSettingsMenu`'s chevron | one control under one fill, no divider; the chevron half a tile wide, touching the tile, its glyph 0.6 of the glyph token at a 3 stroke |
| Navbar items (logo, Back, Forward, the name, ⋯) | `NAV_ITEM_CLASS` | the control tall, transparent at rest, `bg-accent` under the pointer and while open |
| Navbar view buttons (Display, Preview) | `NAVBAR_VIEW_BUTTON_CLASS` | the control square, a 16px muted glyph, `bg-accent` while open |
| A tab's actions | `PANEL_ACTION_CLASS` | the control tall, 8px in, regular weight; Reset ghost, Save `default` while it can save |
| A status screen's action | `StatusAction` | outline, the control tall, `text-ui` at regular weight, no shadow |
| Quick Edit's actions | `Button`, `size-control` | square and icon only, 4px apart; the rightmost `default`, the others `secondary` |
| A small icon button (a card's X) | `size-icon-button` | a 12px muted glyph, the foreground and `bg-accent` under the pointer |

- **The strip** has Figma's toolbar proportions at a 28px tile: a 40px bar including its 1px border, 5px of padding,
  4px between tiles, corners of 10px and 16px icons. A phone's strip uses the same classes at 36px tiles.
- **A sub-toolbar** is one row on the strip's surface at the strip's proportions. On a desktop every tool's row is one
  width, 240px (`SUB_TOOLBAR_WIDTH_CLASS`); a slider row is 20rem on a phone. Why: the column under the strip keeps
  its width from one tool to the next.
- The Home's Open is outline at the control's height with a 16px FolderOpen icon, never a filled primary. Why: on a
  page with nothing else on it, a quiet button reads as a button and nothing more.

### Dropdowns

`ValueDropdown` is the one way to pick one value from a list: in panel rows, in the settings cards, in a board's Layer
display, in the Home's type filter. It is built on the one `DropdownMenu`. There is no Radix Select and no native
`<select>`. Why: one popup, one keyboard and one touch rule, so a fix lands in every picker.

- **The trigger** shows the chosen option's icon (where the options have icons), its label in the foreground, and a
  12px chevron at 60%. It is bordered as a field (`border-input`, `shadow-xs`), the control tall, at least 6rem wide,
  8px in, with 6px between its parts, and it fills with `bg-accent` while open. Its accessible name is "Label: value".
- **The list** holds radio items, the chosen one ticked at the right. A disabled option is dimmed. Where no option
  matches, the trigger shows a `fallback` ("Custom"). The list is at least as wide as its trigger, aligned to its end,
  4px under it, and closes with no exit animation.
- **Width: half the row.** A dropdown takes half its row and its label keeps the rest
  (`grid-cols-[minmax(max-content,1fr)_minmax(50%,max-content)]`). It grows past half only where its value needs the
  room. A colour field, and a dropdown set to fit (the Home's ghost type filter, a picker on a toolbar tile), are as
  wide as their content. Why: a dropdown as wide as its value reads ragged, and one wider than half for no reason
  crowds its label.
- **In a settings card, every dropdown is one width**: half the content (100px in the desktop's 224px card), or the
  card's widest option where that is wider (`fixedWidth`, so the width never changes with the choice). It is the small
  control (`h-icon-button`: 24px; 36 on a phone), 6px in, with 4px between its parts and 14px icons.
- **Option icons** follow [Icons](#icons): only where they say more than the word.

### Menus

- **A menu of actions is a `DropdownMenu`**: the file's ⋯, the app menu, the view's menu, a tab's overflow, a tool's
  chevron, the zoom. A tree row's right-click menu is the `ContextMenu` primitive, with the same items. A picker drawn
  as a toolbar tile (Draw's colour, stroke, line style and placement, Clip's axis, Preview's routines) keeps its tile
  and opens its own `DropdownMenu`.
- **The menu** is the popup surface where it opens over the view, `rounded-md`, 4px of padding, at least 8rem wide,
  4px from its trigger (6px under a tool's chevron) and 8px from the window's edges. A menu taller than its room
  scrolls in a `ScrollArea`.
- **An item** is `text-xs`, at least the row tall, `--cad-pad` in at the sides and 6px above and below, with 8px
  between a 16px muted icon and its words. It takes the accent fill under the pointer or the keyboard; disabled, it is
  at 50%; a destructive item is in the destructive colour. Labels are in sentence case.
- **Checks sit on the right.** A radio or checkbox item shows its tick (a dash for some-of) at the right, so every
  item's words start on one edge. Why: a row's text never shifts because it is ticked.
- **Choosing a value closes the menu; ticking a box keeps it open** (a filter, Clip's settings, Loop).
- **Separators** run the menu's full width, with 4px above and below. **A key hint** is `text-tiny`, muted, at the
  item's right (the zoom's menu), and is left out on a touch screen.
- **A submenu** opens beside its row, marked by a right chevron. A phone has no room beside a menu, so there a submenu
  opens in place (`DropdownMenuInlineSub`): its items under its row, indented 20px, its chevron turned down, shut
  again each time the menu opens.

### Rows

One row primitive draws every list in the panel and the explorer: `TreeRowSurface` with `TreeRowGlyph` or
`TreeRowToggle`, `TreeRowName` and `TreeRowDetail`, `TreeRowActions` and `TreeRowHeading`. Long lists go through
`VirtualRows`, and a search's matches through `primitives/tree-filter.jsx`. Only the primitive sets a row's horizontal
geometry: no list pads a row, draws its own chevron or sets its own text size. Why: a fix to the row lands in every
list.

- **The box** is the row tall (28; 36 on a phone) and `rounded-md`, its fill hanging 8px past the inset. Under the
  pointer it is `bg-accent/50`; selected, `bg-brand-subtle`; holding the pick without being it, `bg-accent/30`. Text is
  the panel's size at regular weight, the names at full strength.
- **One glyph slot**, the row's first child: 12px wide, on the inset, 10px further in for each level, with a 1px
  `bg-border` guide under each owner's slot. It holds a branch's chevron (at half strength where the tree's shape is
  locked), a leaf's kind icon, a colour marker, or nothing, the slot kept. A second marker goes after the name. Why:
  every name at a level starts on one column.
- **Name and detail.** The name starts 4px after the slot (32px from the panel's edge at the top level) and stays
  whole. A muted detail (a count, a page, an owner) follows 4px on and truncates first. Text ends 8px before the row's
  end.
- **Actions** (Isolate, the eye) float over the row's right end: 12px glyphs in 16 × 20 buttons, 2px apart, the last
  glyph ending on the right inset. They show under the pointer or keyboard focus, always where nothing hovers (a touch
  screen, the phone's sheet), and stay while one is on. The name fades out under them; nothing is drawn behind them.
- **A heading** over a run of rows (`TreeRowHeading`) is a muted line the control tall, on the inset, at regular
  weight: a label for the rows under it, never one of them.
- **While a tab loads**, it shows six placeholder rows on the rows' own lines (`TreeRowsLoading`), in the muted colour
  at 20%, fading downwards.
- **The explorer's and the name menu's rows** use the same primitive with their own numbers: 24px (36 on a phone),
  12px text, 5px in, padding themselves. Their document glyph is 16px, overhanging the 12px slot by 2px each side.

What a row does (picking, search, folds): [Trees](viewer-ux.md#trees).

#### Settings rows

- **`PanelSelectRow`** is a `FieldLabel` and a `ValueDropdown` on one row the control tall, the dropdown at least half
  the row (and 6rem), the label the rest: Joints' Position, Animation's routine and Speed, a board's Others.
- **`PanelSwitchRow`** is an optional 16px icon, the label, and the switch at the row's right end. The whole row is the
  switch's label, so a press anywhere on it turns it.
- **A parameter with no range** is `FileSheetSettingRow`: its name in a `1fr` column and the number field in a 5.5rem
  column ending on the inset.

### The slider control

`SliderField` is the one control for a number a slider sets: its label, its number field and its slider. Only it and
the playback scrubber import the slider primitive. Why: no site brings its own slider and number.

- **In the panel** it is two lines: a line the control tall with the label at the left and the value at the right,
  then the slider's 12px band across the full width, then 8px: 48px a control. The label and the band start on the left
  inset; the value's text and the band end on the right one.
- **Compact, in a settings card**: a 24px label line over the 12px band (36px), with the card's 8px gap below.
- **Inline, in a toolbar row** (Explode's, Clip's): the label, the slider and the value on one line.
- **The look** is shadcn's shape at the viewer's scale: a 6px round track and a `size-thumb` thumb. The colours come
  from `--slider-*` only: the track is the foreground at 9% (12% in dark), the fill 28% (32%), the fill under the
  pointer 38% (42%); the thumb is white (a light grey in dark) with a black ring at 45% (55%) and a small shadow.
  Keyboard focus rings the thumb (3px, the ring at 40%). Why: Figma's quiet sliders; never the primary's bar or an
  accent.
- **An origin.** A slider whose rest is mid-range (a joint) fills from its origin to the value, with a 1px tick at the
  origin.
- **Disabled**, the slider alone goes to 50%, its thumb flat, under a not-allowed pointer. The label and the value keep
  their colours.
- **Scrubbing.** Dragging a panel slider's label sideways (an east-west cursor) moves the value one step per pixel,
  ten with Shift, after 3px of slop, written as a slider drag. A finger's press on the label scrolls the panel instead.
- A long label truncates and shows its whole name as a hint. On a phone the band takes `.cad-hit`.

### Number fields

**The slider's value field** (`kit/inspector/SliderValueField.jsx`) is Figma's number field.

- It is as wide as its number and unit (32px at least, 96px at most), the icon button less 2px tall, 6px in, with 5px
  corners. Its text ends where the slider does, so a longer value grows it to the left.
- At rest it has no fill. Under the pointer it has a 1px outline (the foreground at 20%). While edited it takes the
  background, a brand edge and a 1px inset brand ring. An entry that is not a number gets a destructive edge. Why:
  nothing moves between rest, hover and editing.
- The number is the foreground, tabular and right-aligned. Its unit (mm, °, %, EV) is muted and outside the input, so
  it is never selected or typed over.
- A click selects the number (a click on the padding or the unit too); a later click places the caret. Enter or
  leaving the field commits it. Escape puts back the value and the slider. A value left as it shows commits nothing.
  Up and Down step it, ten steps with Shift.
- A length or an angle typed in another unit converts (cm, m, in, ft, µm; rad, deg). A problem shows as a hint under
  the field's right end: "Unknown unit: kg"; past the range, "Max 9 mm", set to the bound on Enter; no number, "Enter
  a number, 3–9 mm", put back on Enter. While a valid number is typed, the slider follows it.
- Disabled, the value keeps its colour; only the pointer and the missing outline say it is off.

**A number with no range** (Params' unranged parameters) is `FileSheetNumberProperty`: a bordered field the control
tall (`border-input`, the muted fill at 30%, 8px in, a ring while focused), its number tabular. Focusing it selects the
value; Enter or leaving commits; Escape puts back what it held. Disabled, the whole field is at 50%.

### Switches and checkboxes

- **A setting that is on or off is a `Switch`**: shadcn's, 24 × 14 (36 × 20 on a phone), its thumb the track's height
  less 2px. It is the primary colour when on and the muted foreground at 35% when off, and 50% when disabled. It stands
  at its row's right end: Show grid, Loop, Pours.
- **A section that turns on and off carries its switch on its heading row** and folds to the heading alone while off
  (Preview's Orbit and Floor). Why: the toggle needs no row of its own.
- **In a menu, on or off is a checkbox item**: a tick at the right, the menu kept open (a filter, Clip's Part colours,
  Loop in Playback settings). The app menu's host settings (Telemetry) draw a 14px box at their row's right end,
  filled with the primary colour while on.
- `Checkbox` (`primitives/checkbox.jsx`) is shadcn's box at `--cad-check`, filled with the primary colour when ticked.
  No viewer surface draws one; on or off in the panel or a card is a switch.

### Chips

- **A chip is shadcn's `Badge`** in its secondary look, given an edge (`border-border`) so it stands off the bar. It is
  the chip token tall (20; 28 on a phone), `rounded-md`, `text-xs` at medium weight, 8px in, its 12px icon first.
  `ReferenceChips.jsx` draws every chip: Quick Edit's attachments, and Measure's measurements in its row. Why: a chip
  reads as a chip, in shadcn's standard look.
- Its label and its X are two buttons: the label is the whole tile left of the X, and the X is the small glyph, muted,
  with `.cad-hit`. A part's name is cut to 16 characters; a count after it is never cut.
- A reference pasted into Quick Edit's note becomes an inline pill on the note's 20px line. A click selects the whole
  pill, in the selection colour.

### The settings cards

`SettingsCard` is the one card for settings over the view: the Display card and Preview's Settings
(`SettingsCardDock` docks and slides it). Why: one family, so the two look and move alike.

- **The box** mirrors the panel's peek card: a 1px border, opaque `bg-sidebar`, `shadow-md` and 10px corners, 4px from
  the view's right edge, from what it docks under (the navbar, or Preview's bar) and, where it is taller than the
  view, from the bottom.
- **The width** is at least 224px on a desktop (the default panel's 232 less the peek's 4px each side) and
  min(320px, 100vw − 8px) on a phone. The card grows to fit its widest label and value rather than cut either short,
  and never past the view less 8px.
- **The inset** is 12px on all four sides. Its type is the panel's one size (`data-panel-surface="card"`).
- **The head** is the title (medium weight) and its X on one line. The X is a small icon button whose 12px glyph ends
  on the right inset, centred on the title's line. There is no icon beside the title.
- **The body** scrolls in a `ScrollArea` between the head and Reset, which stay put. Its rows are a grid: the label
  column takes the rest, the control column at least half. Controls are 24px (36 on a phone), 8px apart. A colour is
  as wide as its value; dropdowns follow [Dropdowns](#dropdowns).
- **Sections** are parted by one hairline, never a line between rows ([Hairlines](#hairlines)). Where a card has
  section headings, they are the foreground at medium weight; the Display card has none. Under a heading a label is
  short ("Opacity" under Floor), while its accessible name stays whole ("Floor opacity").
- **Reset** stands at the bottom right: a ghost button the control tall, its text ending on the inset, off while
  nothing differs. What each card's Reset puts back: [The Display card](viewer-ux.md#the-display-card),
  [Camera, animation and Preview](viewer-ux.md#camera-animation-and-preview).

### A tab's actions

`PanelActions` is a panel tab's last row: its Reset, and Params' Save.

- Its buttons sit at the right, 8px apart, the last one's box ending on the right inset, with 8px under them. They are
  the control tall at regular weight (`PANEL_ACTION_CLASS`). Reset is ghost; Save is `default` only while it can save,
  and otherwise looks like a disabled Reset.
- The row sticks to the panel's bottom edge, full width on the panel's colour, while the tab scrolls under it, and
  stands under the last row when the tab is short. The body drops its own bottom padding under it, so the row stays
  flush on the panel's edge at the end of the scroll too. Why: an action is never scrolled away from what it acts on.
- A tab has one Reset, at its bottom right. While Reset is enabled, the tab's name carries the changed dot (and so do
  its ⋯ item and the ⋯ when the tab is in overflow).
- Words that explain the buttons (Params' status) stand right-aligned directly above them.

Which tabs end in actions: [Parameters](viewer-ux.md#parameters), [Joints](viewer-ux.md#joints),
[Animation](viewer-ux.md#animation).

### Tooltips

Every hint is a `TooltipHint`, alone or through `ToolbarButton`'s `tooltip`, never a native `title` (Quick Edit's
chip list still names a reference's full name with one).

- **The look:** `text-tiny` on its line, on the popover surface with a border and an arrow, 12px by 6px in, at most
  16rem wide, 6px from its control.
- **Timing:** it opens after 400ms of rest and closes on a press. On focus it opens only when the focus came by Tab,
  never when code moved it (a closing menu handing focus back). A finger never opens one.
- **The words** are a word or two, the action's name. A tool's hint is its name, then its key muted ("Measure M"); the
  key is also the button's `aria-keyshortcuts`. A truncated name shows whole in a hint (`overflowOnly`).
- **No hint** on a disabled control, the tool in hand or an open menu's trigger, except a hint that says why a control
  is off and what to do about it (`explainsDisabled`: Params' Save). A control that says what it is needs none.
- The picture's hover tip (`kit/shell/HoverTip.jsx`) is the picture's own label: the same type and surface in the
  picture's scheme, after 450ms, taking no pointer.

Which controls have hints, and on which side: [Tooltips and feedback](viewer-ux.md#tooltips-and-feedback).

### Dialogs and sheets

- **Dialogs** are shadcn's `Dialog` and `AlertDialog` as shipped, on `text-ui`: one centred card, at most 28rem wide
  and never wider than the window less 1rem a side, 24px in, 16px between its parts, `rounded-lg`, with a border and
  `shadow-lg`, over a black overlay at 50%. They fade and zoom in over 200ms. A dialog has no corner X: it closes by its
  own buttons, Escape or a press outside. Its buttons sit at the right, 8px apart. The viewer's dialogs are What's new
  (one primary "Got it", which has the focus) and the Home's Delete ("Delete <name>?": Cancel, Delete).
- **Sheets** are shadcn's `Sheet`, Radix's dialog drawn from an edge, three quarters of the window wide and at most
  20rem. The phone's panel is one: from the left, 85% wide and at most 20rem, under the navbar, with no scrim (its
  overlay is kept but clear, so a press beside it closes it and reaches nothing under it). It slides with the peek's
  100ms and 80ms and closes on a swipe of 48px towards its edge, more across than along. Its layout:
  [A phone](viewer-ux.md#a-phone).
- **No window breakpoints.** A dialog or a sheet sizes itself by its caps and the window's width, never by `sm:` or
  `md:`. Why: the viewer is often a pane in a wider window, and only its own width says which layout it has.

#### Toasts

Only an export makes toasts: shadcn's Sonner, mounted once with the export controls, at the top right, 16px under the
navbar and 16px from the edge. A toast is one line of `text-xs` at regular weight, 10px by 6px in, with a 14px icon,
as wide as its text up to 30rem. Below a 600px window, Sonner's own layout spans the window. What it says:
[Tooltips and feedback](viewer-ux.md#tooltips-and-feedback).

## Input

### Touch

- **One trigger rule for every menu and dropdown** (`DropdownMenuTrigger`). A mouse or a pen opens it at the press. A
  finger toggles it at the tap's click, from the state it had when the finger landed, so a second tap on the trigger
  shuts it. iOS's late focus on a tapped trigger does not count as focus outside. Why: a menu opened at a finger's
  press was shut again by the rest of the tap.
- **Hover is for pointers that hover.** A hover fill shows only under a pointer that can hover (Tailwind's `hover:` is
  `@media (hover: hover)`) or while the control's menu is open, and a focus ring only on `:focus-visible`. A tap leaves
  neither behind. Where nothing hovers (`@media (hover: none)`, the phone's sheet), row actions always show.
- **A small mark takes a finger's area.** A mark smaller than a control (a chip's X, a slider's band, a row's action)
  keeps its drawn size and takes `.cad-hit`: an invisible press area of 36px on a phone, none on a desktop.
- **The picture's gestures become mouse events in one place** (`kit/viewport/touchGestures.js`). A double tap is a
  double-click: each tap within 350ms and 10px, the second within 300ms and 24px of the first. A long press of 500ms
  within 10px is a right-click: the menu opens at the finger and what the press began is cancelled. A second finger or
  a move past the slop makes it neither. One finger orbits, two pan and zoom, and a tap picks; a pinch, a cancelled
  touch or a camera drag never picks.
- **A double-click never takes the selection away.** A press that would take something out of the selection waits for
  the double-click window: 220ms for a mouse (`DOUBLE_CLICK_WAIT_MS`), 300ms for a finger (`DOUBLE_TAP_MS`). A
  double-click drops it; a press on something else lets it act first; a lone one acts when the window ends. A press on
  empty space clears at once.
- **A finger reaches further on the picture.** An edge is within 20px (one within 16px wins over the face under it);
  ink, a measurement and the eraser's ring 16px (`TOUCH_HIT_PX`); a joint's knob 22px. A mouse keeps its few pixels.
- **The pointer's kind never sets the layout**; only the viewer's width does. It may set reach, tap slop, zoom speed,
  whether a menu shows key hints, and whether row actions wait for a hover.
- A canvas shows no iOS callout and selects no text.

What each gesture does: [Selection and gestures](viewer-ux.md#selection-and-gestures).

### Keyboard focus

- **A ring only for the keyboard.** A focus ring shows only on `:focus-visible`, in `--ring`. shadcn's primitives keep
  their 3px ring at 50% (buttons, fields, switches; the slider's thumb at 40%). The chrome's own controls (tiles, tabs,
  navbar items, dropdown triggers, a card's X) draw 2px at 45%. A control built on a primitive keeps the primitive's
  ring.
- **Focus goes back where it came from.** Closing a menu, a card or a sheet hands focus back to what opened it: the
  Display card's to its button, the peek's and the phone sheet's to the panel toggle. A hint does not open on focus
  handed back.
- **Tabs and trees.** A tab list is one stop in the Tab order, and ← and → move between tabs and wrap. Tree rows (the
  Model tree, the name menu's Files) follow the WAI-ARIA tree pattern (`primitives/tree-keys.js`): ↓ and ↑ the next
  and previous row, Home and End the first and last, → opens or enters a branch, ← shuts it or goes to its parent,
  Enter and Space press the row.
- **Menus** take Radix's keys: the arrows, Enter and Space, Escape. → and ← open and shut a submenu, an in-place one
  too.
- **Fields:** Enter commits, Escape puts back, ↑ and ↓ step a number (ten steps with Shift).
- **The panel's grip** is a separator in the Tab order: ← and → change the width by 16px, Home and End go to its
  bounds.
- **Escape closes the innermost thing first.** A popup opened inside a card or the panel closes before the card or
  the peek (`hasOpenPopup`, `lib/popups.js`), and anything marked `data-escape-owner` spends its own Escape. The
  rest of the order: [Keyboard](viewer-ux.md#keyboard).

## Checking a change

A rule changes here in the same change as its code, and the test that holds its number changes with it. Tests
exercise real transitions and drawn sizes, not class names; a test of a layout that is gone is replaced, not kept.
Paths under `scripts/test/` and `tests/python/` are the repository's.

| Test | What it holds |
| --- | --- |
| `designSystem.test.js` | the type tokens at both scales, no 10px step, no `text-[Npx]` and no stylesheet font size; no window breakpoint in chrome; every chrome scroll region a `ScrollArea`; menus at `text-xs` on the row and tooltips at `text-tiny`; the Home's type; the navbar's row and the logo on the 16px line; rows padded by the row primitive alone; only `SliderField` and the scrubber import the slider |
| `lib/scale.test.js` | `scale.js` equals the stylesheet's tokens, at both scales |
| `styles/canvas.test.js` | core's written-out colours equal the tokens, and every view's canvas is `--canvas` |
| `kit/look/sceneColors.test.js` | no view hard-codes a selection, hover or box blue |
| `file-viewer/panelPeek.test.js` | the slide's classes carry its duration constants; the fallback outlasts the slide |
| `kit/inspector/FieldLabels.test.tsx` | every control's label is `FieldLabel`, and its value the foreground |
| `kit/shell/PanelInset.browser.test.mjs` | every piece of the panel's content on the 16px inset, in every tab of several files, placeholder rows too |
| `kit/shell/RendererShell.browser.test.mjs` | the size guards, below |
| `scripts/test/check-ui-strings.mjs`, `i18n/i18n.test.mjs` | no English literal in the chrome; the locales mirror `en.js` |
| `scripts/test/check-kit-boundaries.mjs` | the kit names no file format |
| `tests/python/global/test_document_links.py` | every relative link and `#anchor` in these docs lands on a heading |

The size guards in `RendererShell.browser.test.mjs`, each a browser test by name:

- **"a phone's scale"**: the primitives draw 36px controls and 15/20 text, and a tap leaves no fill or ring.
- **"every control and every text on the walk is its scale's"**, on a phone and on a desktop: it walks the view, the
  Display card, each panel tab, a menu, Quick Edit at rest and with an attachment, and Preview's Settings. Every
  control's height and every text's size is one of its scale's, and on a phone every control is the one 36px.
- **"every popup trigger opens on one tap and shuts on a second tap on it"**: the touch rule, in the navbar, the strip,
  the Display card, the sheet and Preview's Settings.
- **"the type scale and the strip's proportions, as drawn"**: the 40px strip of 28px tiles 5px in, its 10px and 4px
  corners, the panel's 32px head with its rule under the strip, panel rows and menu items at 12/16, the navbar at
  13/20, a tooltip at 11/16.
- **"a toolbar button under the pointer is seen…"** and **"Preview's bar takes the backdrop's ink"**: hover fills and
  ink read on their surface, the bar at 4.5:1 or more.
- **"three tabs and the search fit the 232px panel…"** and **"Display's card is the peek card's mirror…"**: the tab
  budget, and the card's box, gaps and 12px inset, its dropdowns one width, nothing cut short.

Run the units with `scripts/test/test-js.sh --select ui-units` (the checks, the type check, the Node tests and Vitest)
and the browser specs with `--select ui-browser`. One file runs with
`npm --prefix packages/ui test -- src/designSystem.test.js`; a browser spec reads the built package, so run
`npm run build:packages` first. The link test runs in `scripts/test/test-global.sh`.
