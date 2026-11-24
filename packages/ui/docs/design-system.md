# Design system

This doc holds the rules below the page's layout: the two scales and their tokens, type, spacing, colour, surfaces,
motion, icons, the one component for each job, and input. It binds every control the viewer draws, in both apps, and a
change to a rule changes this doc in the same change. Where things go and how the viewer behaves is the companion doc,
[viewer-ux.md](viewer-ux.md). Code paths are under `packages/ui/src`; `kit/` is `renderers/kit/`.

## Principles

- **One component per job** ([Components](#components)). A renderer uses it and extends it, and never draws a copy of
  its own. Why: a fix made once lands everywhere, and a copy drifts.
- **Stock shadcn first.** The primitives (`primitives/`) are shadcn's components as shipped, at the viewer's scale. A
  change to one is made in the primitive, never at a call site. Why: they already work with a finger and a keyboard.
- **The desktop is the reference.** A phone has the same components at a second scale; only the layout differs. Sizes
  come from tokens: no pixel size where a token exists, no `mobile ?` size branch, and a new size is a token in both.
- **Quiet and dense, after Figma**: neutral greys, the brand only for state, text told apart by colour and weight, one
  hairline between groups, and nothing that is only decoration.
- **Even padding.** A box is padded the same across as down. Why: uneven padding reads as a mistake.
- **The picture is not the chrome** ([The viewport's scheme](#the-viewports-scheme)).
- **Every word is translated** through `useI18n().t`; `i18n/locales/en.js` holds every key. Text from a file or the
  engine shows as written.

## Two scales

Every size the chrome draws is a token in `styles/globals.css`: `:root` holds the desktop's values and one switch holds
the phone's. Every primitive and shared class reads them; script that counts pixels reads `lib/scale.js`, its mirror.

- **The phone scale applies while the viewer itself is under 600px wide** (`VIEWER_MOBILE_BREAKPOINT`). The viewer
  says `data-viewer-layout="mobile"` and one page-wide rule switches every token, so a menu portalled out of the
  viewer matches the chrome it came from. A viewer drawn off screen for a picture never flips it.
- **Layout follows the viewer's width, never the window's**: chrome has no `sm:` or `md:` breakpoints.

| Token (Tailwind) | Desktop | Phone | What uses it |
| --- | --- | --- | --- |
| `--cad-control` (`h-control`, `size-control`) | 28 | 36 | strip and sub-toolbar tiles, navbar buttons, panel tabs, head buttons and settings rows, a tab's actions, Quick Edit's buttons, dropdown triggers, fields |
| `--cad-icon-button` (`size-icon-button`) | 24 | 36 | small icon buttons (a card's X), a settings card's controls, the `xs` button |
| `--cad-row` (`min-h-row`), `--cad-row-sm` | 28, 24 | 36 | menu and dropdown items, the panel's tree rows; the explorer's rows |
| `--cad-chip` (`h-chip`) | 20 | 28 | chips |
| `--cad-glyph`, `--cad-glyph-sm` | 16, 14 | 18, 16 | a tile's icon; Quick Edit's action icons, a chip's X button |
| `--cad-pad` (`px-pad`), `--cad-step` (`gap-step`) | 8, 4 | 10, 4 | a control's side padding; the gap between neighbouring tiles |
| `--cad-radius-control` (`rounded-control`) | 4 | 6 | a tile's corners |
| `--cad-switch-w` × `--cad-switch-h` | 24 × 14 | 36 × 20 | a switch |
| `--cad-thumb` (`size-thumb`), `--cad-check` | 12, 14 | 20, 20 | a slider's thumb; a checkbox |
| `--cad-hit` (`.cad-hit`) | 0 | 36 | the least press area round a small mark, invisible and centred on it |
| `--cad-card-min` | 288 | min(320px, 100vw − 8px) | a settings card's least width |

The navbar, Preview's bar, the strip and a sub-toolbar are the control + 12 (40; 48 on a phone); the panel's head row
is the control + 4 (32; 40). Only layout is a phone's own: the panel is a sheet, More holds what does not fit, Quick
Edit spans the view, nothing peeks, no hint opens and row actions always show ([A phone](viewer-ux.md#a-phone)). Why:
the desktop stays as it is, and a phone is read at arm's length and worked with a finger: every control and row is
36px, and a small mark's press area (`.cad-hit`) grows to 36px around it.

## The type scale

Three interface sizes and one heading, each on a fixed line height, as Figma's interface type is: `text-tiny`,
`text-xs`, `text-ui` and `text-heading` (`styles/tokens.css`). On a phone each step is 2px larger, so the hierarchy
holds.

| Step | Desktop | Phone | Used for |
| --- | --- | --- | --- |
| `text-tiny` | 11/16 | 13/18 | tooltips, key hints, small metadata (the zoom's percentage, the app menu's version, the Home's ages) |
| `text-xs` | 12/16 | 14/20 | Quick Edit's bar and chips, sub-toolbars, the update status, every menu, list and context menu, toasts |
| `text-ui` | 13/20 | 15/20 | the navbar and file name, dialogs, the Home, Quick Edit's note, the loading line, status screens; `text-sm` and `text-base` are aliases |
| `text-heading` | 15/20, 600 | 17/22, 600 | the one heading: the Home's without a navbar, its welcome title, the CAD app's notice |
| `--cad-text-panel` | 12/16 | 14/20 | every step inside the panel and the settings cards |

- **No other size**: no 10px step, no `text-[Npx]`, no font size in a stylesheet but the scale's variables.
- **One size per surface.** Inside the panel and the settings cards (`[data-panel-surface]`) and a pick's card
  (`[data-detail-card]`), every step is the panel's size and text is told apart by colour and weight. A menu portalled
  out of them keeps the chrome's scale. Why: nothing there jumps in size, and a pick reads alike in panel and card.
- **A menu item** is its `text-xs` line in 6px of vertical padding, at least the row tall, set by the primitives alone.
- **Weight.** Text is regular. Medium (500) marks a title: the open tab, a card's title and section headings, a chip,
  the Home's names. Semibold (600) is the heading step's and a dialog title's. A list's emphasis is colour, never
  bold; a search's match is `--brand-text` at medium weight. Numbers that change or line up are tabular.
- **The picture's own text** keeps its own sizes, never under 10px: the cube's letters and face names 10px, a
  measurement's label and the snap chip 10px semibold, a drawn text mark 16, 20 or 28px. Why: it is the picture's.
- **Greyscale antialiasing** covers the page while a viewer is on it. Why: subpixel antialiasing draws light text on
  dark a weight heavier. A phone's fields stay at 15px; the page's `maximum-scale=1`, not a 16px font, stops a phone
  zooming into one.

## Spacing and the panel inset

The spacing scale is 4, 8 and 16px, with 12px for a hairline's air and a card's inset. The panel has no 6px or 10px
vertical step.

- **The panel inset**, `--panel-inset` (16px), is one line on each side, on a desktop and a phone. Every text, glyph
  and control starts on the left line; values, switches, sliders and a row's last action end on the right one. The
  navbar's panel toggle puts its icon on the same column. Why: one edge the eye can follow, as in Figma's panels.
- **Only the body pads**, by the inset; no section, list or row sets its own side padding. A box hangs past the line
  by its own padding, so what it holds stays on it: a row's fill by 8px, a tab's pill by 6px, the head's icon buttons
  by 7px (11 on a phone), a value field by 7px.
- **Vertical steps.** The body starts 8px under the head. A slider control is 48px (its 28px line, its 12px band, 8px
  under). A settings row is the control tall with 8px under it; the Animation tab's rows are 4px apart. A tab's
  actions row stands 8px under the last control, with 8px under its buttons.
- **A card's inset is 12px on all four sides**: the panel inset less the card's 4px gap, so its content stands where
  the docked panel's does.
- **Over the view**, the strip and the tool stack stand 8px in (`CHROME_INSET_PX`), the corner's zoom 12px
  (`CORNER_INSET_PX`), a card or a peek 4px (`PANEL_PEEK_GAP_PX`). The navbar has 8px of side padding.

#### The panel's head

- One row, the control + 4 tall, 8px under the panel's top. **Tab pills** are the control tall, 6px in at each side
  (`TAB_PAD_PX`) and 4px apart (`TAB_GAP_PX`). The open one is `bg-accent` with foreground text at medium weight; the
  others are muted, with `bg-accent/50` under the pointer. A pill is as wide as its name at medium weight, so choosing
  a tab moves nothing, and it never shrinks, truncates, wraps or scrolls.
- **With tabs**, the row has 8px under it and then a full-width 1px rule, level with the strip's bottom edge. **One
  tab** is a plain title at medium weight, with no rule and no gap kept for one.
- **The icon buttons** (⋯, search) are the control square with a 14px muted glyph, 4px apart at the right end:
  `bg-accent/50` under the pointer, `bg-accent` while open.
- **The open search replaces the row in place**, with no box (no border, fill or ring): its magnifier on the left
  line, its X ending on the right one. It keeps the head's rule, or its lack of one, so nothing below moves. What the
  head holds, and where a fourth tab goes: [The panel](viewer-ux.md#the-panel).

#### Hairlines

One 1px `bg-border` rule parts groups: a card's sections, a panel tab's blocks (Joints' motion and its joints, a
board's layers and its Layer display). It spans the content width with 12px of air to the nearest ink on each side (a
switch's ink starts 5px into its row, a heading's capitals 4px into their line), and it never stands between rows.
Only the rule under the panel's tabs and a menu's separators run full width. A sub-toolbar parts its groups with a
16px vertical rule, hidden where a phone's row wraps. Why: groups read as groups, without a line under every row.

## Colour

The app's theme (System, Light or Dark, from the app menu) colours the chrome. The viewport's scheme (Display's
Background) colours the picture and what belongs to it.

### The palette

The tokens are shadcn's neutral set (`styles/tokens.css`), greys with no hue, as Figma's and VS Code's themes are.

| Token | Light | Dark | Used for |
| --- | --- | --- | --- |
| `--canvas` | oklch .94 (#ebebeb) | #1e1e1e | the area behind every view, darker than the chrome in both themes |
| `--background` | #ffffff | #2c2c2c | the page, the Home, dialogs |
| `--sidebar` | oklch .985 | #2c2c2c | the navbar, the panel, the cards |
| `--popover`, `--card` | #ffffff | oklch .31 | floating chrome, menus, tooltips |
| `--secondary`, `--muted` | oklch .97 | oklch .34 | secondary buttons, chips, quiet fills |
| `--accent`, `--sidebar-accent` | oklch .92 | #444444 | a hover (at 50%), the open tab, an open trigger, a pressed tile |
| `--border`, `--input` | oklch .922 | white at 12% (15%) | rules, borders, field edges |
| `--foreground`, `--muted-foreground` | oklch .145, .556 | oklch .985, .75 | text and values; labels, details, glyphs |
| `--primary` | oklch .205 | oklch .922 | the one filled button, a switch that is on |
| `--brand`, `--ring` | #249ddd | #62b7ec | focus rings; a text selection (`--selection`, the brand at 30%) |
| `--brand-text`, `--brand-icon` | #2c7197, #1683c7 | #62b7ec | a search's match; the tool in hand's glyph, the changed dot |
| `--brand-subtle` | the brand 12% into the background | 22% | a selected row |
| `--warning`, `--destructive` | amber, red | amber, red | a warning's icon, edge and tint (its words `--warning-foreground`); an error |

- **The brand marks focus and state, never an action**: focus rings and a focused field's edge, a text selection, a
  selected row, the tool in hand's glyph, a search's match, the changed dot, the Home's chosen layout and its focused
  card, and the logo. It is never a button's fill or a link in the chrome, and the panel toggle stays neutral. Why:
  blue says "on" only while nothing else is blue. `--brand-icon` is at least 3:1 on the pressed fill and on white;
  `--brand-text` is darker, for text, as that blue reads dark and odd on a glyph.
- **A link in the chrome** (the app menu's version, "Made by") is muted `text-tiny` that turns the foreground and
  underlined under the pointer or keyboard focus. A slider's colours are its own `--slider-*` tokens.
- **The scene's colours are core's** (`@cad/core/lib/viewportTheme.js`): selection #2979ff (more saturated than the
  brand on purpose: it is read against a model), its fill #4f9dff, hover #8dc5ff, a selected edge #1a73e8, the box
  select #2979ff over a 12% fill, the grid's and axes' colours per scheme. `@cad/core/lib/appTheme.js` writes
  `--canvas`, `--background` and `--foreground` out again for what cannot read a stylesheet; change both together.

### The viewport's scheme

- **Background is the person's, the same in every file of the tab**: Light (the default) or Dark. Light is a grey
  gradient down a 3D view (#f4f5f6 to #dfe2e5) and the light canvas under a flat view; Dark is the dark canvas, flat.
  There is no "follow the app" choice; any other stored value reads as Light. Why: the model area is its own surface,
  as in a CAD program, and never white, so a white part still reads.
- **What belongs to the picture takes its scheme**, drawn inside a `.light` or `.dark` token scope (`ViewFrame.jsx`):
  the scene, grid and axes, the cube, labels and the hover tip, the corner's zoom and its halo, the loading covers
  (the page's own too), the update status, the alert card, and a 2D view's paper.
- **Preview's chrome takes its backdrop's scheme**: its bar, playbar and cover follow Preview's Background where that
  is at least 50% opaque, else the viewport's canvas (`backdropScheme`).
- **What the person works with keeps the app's theme**: the navbar, the strip and sub-toolbars, the panel and the
  phone's sheet, Quick Edit, the Display card and Preview's Settings card, menus, tooltips and dialogs. Why: the
  picture is something to look at and the chrome something to work with, and each keeps its own ground.
- **A page state keeps the app's theme**: a status screen has no picture to take a Background from. A picture taken
  off screen (the Home's) always uses the light viewport.

## Surfaces, layering and motion

Every surface is one of these, defined once (`lib/floatingSurface.js`, `file-viewer/panelPeek.js`); a caller adds
layout, never a surface. Why: chrome reads as chrome over any canvas, light or dark, flat or 3D.

| Surface | How | Look | Used by |
| --- | --- | --- | --- |
| Docked chrome | `bg-sidebar` | opaque, a 1px rule on its inner edge | the navbar, the docked panel, a tab's actions row |
| Floating chrome | `FLOATING_CHROME_SURFACE_CLASS` | the popover colour at 90%, a border, `shadow-md`, `backdrop-blur-sm` | the strip, sub-toolbars, the tool stack, Quick Edit's bar, the bar over picked ink |
| Popups | `FLOATING_SURFACE_CLASS` | the popover colour at 95%, a border, `shadow-sm`, `backdrop-blur-md` | dropdown lists, tool menus, the app menu, the view's menu, the name menu, chip lists |
| Cards | `PANEL_PEEK_CARD_CLASS`, `SettingsCard` | opaque `bg-sidebar`, a border, `shadow-md`, 10px corners | the panel's peek, the Display card, Preview's Settings |
| On the picture | the picture's scheme | the zoom: the foreground at 6% (10% under the pointer, 14% open), haloed; the update status: the background at 95% | the corner's zoom, the update status; Preview's bar has no surface |

Corners: a tile is `rounded-control` (4px; 6 on a phone), and a bar round tiles takes the tile's radius + 6 (10px; 12),
so the curves run parallel. A card is 10px. Rows, pills, fields, menus, chips and tooltips are `rounded-md` (8px).

### Layering

The view's layers, bottom to top (`kit/shell/ViewFrame.jsx`). New chrome joins one of them.

1. **The picture** and what stands on it: the corner, the notice, the loading cover, the alert card, Preview's chrome.
2. **The panel**, docked beside the picture, or its peek over it (`z-40`).
3. **The top layer** (`data-view-top-layer`, `z-50`): the strip, its rows, the tool stack and Quick Edit.
4. **The Display card**, on the same z and drawn after it (`SETTINGS_CARD_LAYER_CLASS`), over the strip and corner.
5. **Portalled popups** at the page's end: menus and lists (a card's own too), tooltips, dialogs and sheets.

### Motion

- **One slide** for every card that comes in at an edge: the panel's peek, the Display card and Preview's Settings
  (from the right) and the phone's sheet. It slides in over 100ms eased out (`PANEL_PEEK_IN_MS`) and out over 80ms
  eased in (`PANEL_PEEK_OUT_MS`), as a transform, and is gone at its end or after 180ms. Its classes live only in
  `file-viewer/panelPeek.js`. Pinning a peek is instant. Why: every card moves alike, and nobody waits for one.
- **Popups** fade and zoom in as shadcn's do (150ms; dialogs 200ms). A popup that a quick second tap must reach
  closes with no exit animation (the value dropdown, tool menus, the app menu, chip lists). Colours, a chevron's turn
  (100ms) and a switch's thumb ease.
- **Progress may move; decoration may not.** An indeterminate bar slides (1.15s a pass), the update status's spinner
  turns and placeholder rows pulse gently. A loading screen has no animated mark or model. Preview's cover and bar
  fade over 300ms.
- **Less motion** (the system's setting): cards and sheets come and go without sliding, fades are cut, placeholder
  rows hold still, and an indeterminate bar stands across its track at 45%, as it does for the host's `reducedMotion`.

## Icons

- **Lucide** (`lucide-react`) is the set. A glyph is drawn for the viewer only where lucide has none (the panel
  toggle, the display modes' spheres, a board's sides, the pick kinds), in lucide's manner: round caps and joins.
- **Sizes**: a tile's icon is the glyph token (16; 18 on a phone) and Quick Edit's the small one (14; 16); a menu
  item's is 16px; the panel head's, a card dropdown's options and Open in's marks 14px; a row's glyph and actions, a
  dropdown's chevron, a card's X and a chip's icon and X 12px. A row's kind glyph has a 1.5 stroke, muted at 70%. A
  document is lucide's Box (a model) or File, 16px.
- **No icon for decoration.** An icon says what the words do not: a tool, a kind, a tone (the alert card's red or
  amber). There is none beside a card's title and none on a status screen.
- **An option's icon shows only where it adds information**: Projection, Style, Side and Background keep theirs; the
  board's Mode (2D, 3D) has none. Why: an icon of the same words says them twice.
- **Display and Preview are a pair**: Display is the plain orthographic cube on every file, Preview a play triangle
  (`PreviewIcon.jsx`, lucide's path at 15/16). Both have a 1.45 stroke on the 24-unit grid, so each shows 12.5px of
  ink, and Preview's settings button wears the cube. Why: lucide's own Play stood taller and heavier than the cube.
- **The changed dot** (`ChangedDot.jsx`) is 4px of `--brand-icon` at the top-right of a tile or a tab's name while
  what it controls is off its default. It moves neither the name nor the tab's width.
- **Open in's marks** are in the row's muted colour: an app's own single-colour mark where its licence allows, else
  lucide's AppWindow. Nothing in the chrome is a hand-drawn copy of an app's mark.

## Components

One component for each job. A renderer brings its tools, rows, tabs and state, built from these.

| Job | Component | Where |
| --- | --- | --- |
| A button | `Button`; on a toolbar, `ToolbarButton` | `primitives/button.jsx`, `primitives/toolbar-button.jsx` |
| Picking one value from a list | `ValueDropdown` | `primitives/value-dropdown.jsx` |
| A menu of actions | `DropdownMenu`; a tree row's right-click, `ContextMenu` | `primitives/dropdown-menu.jsx`, `primitives/context-menu.jsx` |
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
| A control's label; a scroll region | `FieldLabel`; `ScrollArea` | `primitives/field-label.jsx`, `primitives/scroll-area.jsx` |
| Loading | `LoadingStep`, over `Progress` | `loading/LoadingStep.jsx` |
| A status screen | `EmptyState` with a `StatusAction` | `file-viewer/navigation/EmptyState.jsx` |
| A dialog, a sheet | `Dialog` or `AlertDialog`; `Sheet` | `primitives/dialog.jsx`, `primitives/sheet.jsx` |

- **Label and value.** A control's label is `FieldLabel`: muted, regular, the size of where it stands, truncating.
  Its value is the foreground. No control styles its own label. Why: Figma's rule; the eye finds values by colour.
- **Scrolling.** Every chrome scroll region is a `ScrollArea`, with thin overlay bars in the theme's colours; chrome
  has no native `overflow-auto` or `overflow-scroll`. The Home is a page and scrolls with the platform's scrollbar.

### Buttons

Buttons stay neutral: ghost, outline or secondary. At most one button in a place is filled (`default`), and only while
it can act (Params' Save, Quick Edit's rightmost); one that cannot act is drawn as a disabled ghost, never as a filled
grey. No button is filled with the brand. A disabled button is at 50% with no hover (Back and Forward at 40%). Why: a
quiet button reads as a button and nothing more, and the one filled button is the action at hand.

| Kind | How | Look |
| --- | --- | --- |
| A toolbar tile | `ToolbarButton`, `TOP_STRIP_BUTTON_CLASS` | the control square, `rounded-control`, its glyph the glyph token at 70% of the foreground; `sidebar-accent` under the pointer (dark: the foreground at 10%) |
| The tool in hand | `ToolbarButton active` | the neutral pressed fill (dark: the foreground at 16%), its glyph `--brand-icon`, no hint |
| A tool with a menu | the tile and `ToolSettingsMenu`'s chevron | one control under one fill, no divider; the chevron half a tile wide, touching it |
| Navbar items (logo, Back, Forward, the name, ⋯); Display and Preview | `NAV_ITEM_CLASS`; `NAVBAR_VIEW_BUTTON_CLASS` | the control tall, transparent at rest, `bg-accent` under the pointer and while open; Display and Preview a 16px muted glyph |
| A tab's actions | `PANEL_ACTION_CLASS` | the control tall, 8px in, regular weight; Reset ghost, Save `default` while it can save |
| A status screen's action; the Home's Open | `StatusAction`; `Button variant="outline"` | outline, the control tall, `text-ui` at regular weight (Open with a 16px FolderOpen), never a filled primary |
| Quick Edit's actions | `Button`, `size-control` | square and icon only, 4px apart; the rightmost `default`, the others `secondary` |
| A small icon button (a card's X) | `size-icon-button` | a 12px muted glyph; the foreground and `bg-accent` under the pointer |

- **The strip** has Figma's toolbar proportions at a 28px tile: a 40px bar with its 1px border, 5px of padding, 4px
  between tiles, 10px corners, 16px icons; a phone's uses the same classes at 36px. **A sub-toolbar** is a row at the
  strip's proportions, 240px wide on a desktop (`SUB_TOOLBAR_WIDTH_CLASS`; a slider row is 20rem on a phone). Why:
  the column under the strip keeps its width from one tool to the next.
- **Draw's sub-toolbar** is two rows of seven `ToolbarButton` tiles: the seven drawing tools (Pen, Highlighter, Line,
  Arrow, Rectangle, Ellipse, Text), then the Eraser, Colour, Stroke width, Placement (the globe), Undo, Redo and Clear.

### Dropdowns

`ValueDropdown` is the one way to pick one value from a list: panel rows, the settings cards, a board's Layer display,
the Home's type filter. It is built on `DropdownMenu`; there is no Radix Select and no native `<select>`. Why: one
popup, one keyboard and one touch rule, so a fix lands in every picker.

- **The trigger** shows the chosen option's icon (where the options have icons), its label in the foreground and a
  12px chevron at 60%. It is bordered as a field (`border-input`, `shadow-xs`), the control tall, at least 6rem wide
  and 8px in, and `bg-accent` while open. Its accessible name is "Label: value".
- **The list** holds radio items, the chosen one ticked at the right, disabled options dimmed, and a `fallback`
  ("Custom") on the trigger where no option matches. It is at least the trigger's width, end-aligned, 4px under it.
- **Half the row.** A dropdown takes half its row and its label the rest
  (`grid-cols-[minmax(max-content,1fr)_minmax(50%,max-content)]`), growing past half only where its value needs it. A
  colour field, and a dropdown set to fit (the Home's ghost filter, a picker on a toolbar tile), are as wide as their
  content. Why: one as wide as its value reads ragged, and one wider than half for no reason crowds its label.
- **In a settings card every dropdown is one width**: half the content (132px in a desktop's 288px card, 148px in a
  phone's 320px one) or the card's widest
  option (`fixedWidth`, so the width never changes with the choice), 24px tall (36 on a phone), 6px in, 14px icons.

### Menus

- **A menu of actions is a `DropdownMenu`**: the file's ⋯, the app menu, the view's menu, a tab's overflow, a tool's
  chevron, the zoom. A tree row's right-click menu is `ContextMenu`, with the same items. A picker drawn as a toolbar
  tile (Draw's colour and stroke, Clip's axis, Preview's routines) keeps its tile and opens a `DropdownMenu`.
- **The menu** is `rounded-md` with 4px of padding, at least 8rem wide, 4px to 6px from its trigger and 8px from the
  window's edges. A menu taller than its room scrolls in a `ScrollArea`.
- **An item** is `text-xs`, at least the row tall, `--cad-pad` in, with a 16px muted icon 8px before its words. It
  takes the accent fill under the pointer or the keyboard, is at 50% when disabled, and is worded in sentence case.
- **Checks sit on the right** (a dash for some-of), so every item's words start on one edge. Choosing a value closes
  the menu; ticking a box keeps it open.
- **Separators** run the menu's full width. **A key hint** is `text-tiny`, muted, at the item's right, and is left
  out on a touch screen.
- **A submenu** opens beside its row. A phone has no room beside a menu, so there it opens in place
  (`DropdownMenuInlineSub`): its items under its row, indented 20px, its chevron turned down.

### Rows

One primitive draws every list in the panel and the explorer: `TreeRowSurface` with `TreeRowGlyph` or
`TreeRowToggle`, `TreeRowName`, `TreeRowDetail`, `TreeRowActions` and `TreeRowHeading`, long lists through
`VirtualRows`. Only it sets a row's horizontal geometry: no list pads a row, draws a chevron or sets a text size.
Why: a fix to the row lands in every list. What a row does: [Trees](viewer-ux.md#trees).

- **The box** is the row tall and `rounded-md`, its fill hanging 8px past the inset. Under the pointer it is
  `bg-accent/50`; selected, `bg-brand-subtle`; holding the pick without being it, `bg-accent/30`. Its text is the
  panel's size at regular weight.
- **One glyph slot** comes first: 12px wide on the inset, 10px further in for each level, with a 1px guide under each
  owner's slot. It holds a chevron (at half strength where the tree's shape is locked), a kind icon, a colour marker,
  or nothing, the slot kept. Why: every name at a level starts on one column.
- **Name and detail.** The name starts 4px after the slot and stays whole; a muted detail follows 4px on and
  truncates first. Text ends 8px before the row's end.
- **Actions** float over the row's right end: 12px glyphs in 16 × 20 buttons, 2px apart, the last ending on the
  inset. They show under the pointer or keyboard focus, always where nothing hovers, and stay while one is on; the
  name fades out under them.
- **A heading** (`TreeRowHeading`) is a muted line the control tall, on the inset, at regular weight. **Placeholder
  rows** (`TreeRowsLoading`) stand on the rows' lines while a tab loads, in the muted colour at 20%.
- **The explorer's rows** are the same primitive at 24px (36 on a phone) in `text-xs`, 5px in, padding themselves.
- **Settings rows.** `PanelSelectRow` is a `FieldLabel` and a `ValueDropdown`, the control tall, the dropdown at least
  half the row and 6rem. `PanelSwitchRow` is an optional 16px icon, the label and the switch at the right end; the
  whole row is the switch's label. A parameter with no range is `FileSheetSettingRow`, its field in a 5.5rem column.

### The slider control

`SliderField` is the one control for a number a slider sets: its label, its number field and its slider. Only it and
the playback scrubber import the slider primitive. Why: no site brings its own slider and number.

- **In the panel** it is a line the control tall (the label at the left, the value at the right), then the slider's
  12px band across the full width, then 8px: 48px a control, its label and band on the inset lines. **Compact**, in a
  card, it is a 24px line over the band (36px). **Inline**, in a toolbar row, the label, slider and value share a line.
- **The look** is a 6px round track and a `size-thumb` thumb, in `--slider-*` colours only: the track the foreground
  at 9% (12% in dark), the fill 28% (32%), and 38% (42%) under the pointer; a white thumb (light grey in dark) ringed
  in black at 45% (55%), with a small shadow. Keyboard focus rings the thumb at 3px. Why: Figma's quiet sliders,
  never the primary's bar or an accent.
- **An origin**: a slider whose rest is mid-range (a joint) fills from it to the value, with a 1px tick at it.
  **Disabled**, the slider alone goes to 50%, its thumb flat; the label and the value keep their colours.
- **Scrubbing.** Dragging the label sideways moves the value one step per pixel (Shift, ten) after 3px of slop. A
  finger's press on the label scrolls the panel instead. A long label truncates and shows whole as a hint.

### Number fields

**The slider's value field** (`kit/inspector/SliderValueField.jsx`) is Figma's number field.

- It is as wide as its number and unit (32px to 96px), the icon button less 2px tall, 6px in, with 5px corners. Its
  text ends where the slider does, so a longer value grows to the left. The number is the foreground, tabular and
  right-aligned; the unit (mm, °, %) is muted and outside the input.
- It has no fill at rest, a 1px outline (the foreground at 20%) under the pointer, and while edited the background with
  a brand edge and inner ring; a destructive edge marks what is not a number. Why: nothing moves between rest, hover
  and editing.
- A click selects the number; a later click places the caret. Enter or leaving commits, Escape puts back, and a value
  left as it shows commits nothing. Up and Down step it (Shift, ten). A length or angle in another unit converts.
- A problem shows as a hint under the field ("Unknown unit: kg", "Max 9 mm", "Enter a number, 3–9 mm"). Disabled,
  the value keeps its colour; only the pointer says it is off.

**A number with no range** (Params') is `FileSheetNumberProperty`: a bordered field the control tall, a muted fill at
30%, 8px in, its number tabular. Focus selects it, Enter or leaving commits, Escape puts back; disabled, it is at 50%.

### Switches and checkboxes

- **On or off is a `Switch`**: shadcn's, 24 × 14 (36 × 20 on a phone), the primary colour when on and the muted
  foreground at 35% when off, at its row's right end. **A section that turns on and off carries its switch on its
  heading row** and folds to the heading alone while off (Preview's Orbit and Floor).
- **In a menu, on or off is a checkbox item**: a tick at the right, the menu kept open. The app menu's host settings
  draw a 14px box at their row's right end, filled with the primary colour while on.
- `Checkbox` (`primitives/checkbox.jsx`) is shadcn's box at `--cad-check`; no viewer surface draws one today.

### Chips

- **A chip is shadcn's `Badge`**, secondary, with an edge (`border-border`): the chip token tall, `rounded-md`,
  `text-xs` at medium weight, 8px in, its 12px icon first. `ReferenceChips.jsx` draws every chip: Quick Edit's
  attachments and Measure's measurements. Why: a chip reads as a chip, the way shadcn draws one.
- Its label and its X are two buttons; the X is a muted 12px glyph in a `size-glyph-sm` box with `.cad-hit`. A part's
  name is cut to 16 characters. A reference pasted into Quick Edit's note is an inline pill on the note's 20px line.

### The settings cards

`SettingsCard` is the one card for settings over the view: the Display card and Preview's Settings. Why: one family,
so the two look and move alike.

- **The box mirrors the peek card**: a 1px border, opaque `bg-sidebar`, `shadow-md` and 10px corners, 4px from the
  view's right edge, from what it docks under (the navbar, or Preview's bar) and, when taller than the view, the bottom.
- **The width** is at least 288px on a desktop and min(320px, 100vw − 8px) on a phone. Why: half the content then
  holds the longest option of any card (a 3D file's "Orthographic", 123px on a desktop), so every dropdown is half its
  row on either; at the panel's 224px it was not, and every dropdown in the card grew past half to match it. The card
  grows to fit its widest label and value rather than cut either, never past the view less 8px.
- **Inside**, a 12px inset all round and the panel's one type size (`data-panel-surface="card"`). The head is the
  title (medium) and its X on one line, the X's 12px glyph ending on the inset, with no icon beside the title. The
  body scrolls in a `ScrollArea` between the head and Reset. Its rows are a grid, the label column taking the rest and
  the control column at least half; controls are 24px (36 on a phone), 8px apart.
- **Sections** are parted by one hairline, never a line between rows. A section heading is the foreground at medium
  weight; the Display card has none. Under a heading a label is short ("Opacity"), its accessible name whole.
- **Reset** is a ghost button at the bottom right, the control tall, its text ending on the inset, off while nothing
  differs. What it puts back: [The Display card](viewer-ux.md#the-display-card),
  [Camera, animation and Preview](viewer-ux.md#camera-animation-and-preview).

### A tab's actions

`PanelActions` is a panel tab's last row: its Reset, and Params' Save.

- The buttons sit at the right, 8px apart, the last ending on the right inset, with 8px under them. They are the
  control tall at regular weight (`PANEL_ACTION_CLASS`): Reset is ghost, and Save is `default` only while it can save.
- The row sticks to the panel's bottom edge, full width on the panel's colour, while the tab scrolls, and stands under
  the last row when the tab is short. The body drops its bottom padding under it, so it is flush at the end too. Why:
  an action is never scrolled away from what it acts on.
- A tab has one Reset, at its bottom right. While it is enabled, the tab's name carries the changed dot. Words that
  explain the buttons stand right-aligned above them. Which tabs have actions: [Parameters](viewer-ux.md#parameters),
  [Joints](viewer-ux.md#joints), [Animation](viewer-ux.md#animation).

### Tooltips

Every hint is a `TooltipHint`, never a native `title` (Quick Edit's chip list still shows a reference's full name
with one).

- **The look**: `text-tiny` on the popover surface with a border and an arrow, 12px by 6px in, at most 16rem wide,
  6px from its control. It opens after 400ms and closes on a press. On focus it opens only when the focus came by
  Tab, never when code moved it, and a finger never opens one.
- **The words** are one or two. A tool's hint is its name, then its key muted ("Measure M"); the key is also its
  `aria-keyshortcuts`. A truncated name shows whole in a hint (`overflowOnly`).
- **No hint** on a disabled control, the tool in hand or an open trigger, except one that says why a control is off
  and what to do (`explainsDisabled`: Params' Save). A control that says what it is needs none.
- The picture's hover tip (`kit/shell/HoverTip.jsx`) is the picture's own label: the same type and surface in the
  picture's scheme, after 450ms. Which controls have hints, and where:
  [Tooltips and feedback](viewer-ux.md#tooltips-and-feedback).

### Dialogs and sheets

- **Dialogs** are shadcn's `Dialog` and `AlertDialog` as shipped, on `text-ui`: one centred card, at most 28rem and
  1rem in from the window's sides, 24px in, `rounded-lg`, over a black overlay at 50%. A dialog has no corner X; it
  closes by its own buttons, Escape or a press outside. The viewer's are What's new and the Home's Delete.
- **Sheets** are shadcn's `Sheet`: three quarters of the window wide, at most 20rem. The phone's panel is one, 85%
  wide, with no scrim (its overlay is clear, so a press beside it closes it and reaches nothing under it), sliding with
  the peek's timings and closed by a 48px swipe towards its edge ([A phone](viewer-ux.md#a-phone)).
- **No window breakpoints**: a dialog or a sheet sizes itself by its caps, never by `sm:` or `md:`, as the viewer is
  often a pane in a wider window.
- **Toasts** come only from an export: shadcn's Sonner, one line of `text-xs` at regular weight, 10px by 6px in, a
  14px icon, as wide as its text up to 30rem (under a 600px window, Sonner's own layout spans it). What a toast says:
  [Tooltips and feedback](viewer-ux.md#tooltips-and-feedback).

## Input

### Touch

- **One trigger rule for every menu and dropdown** (`DropdownMenuTrigger`). A mouse or a pen opens it at the press. A
  finger toggles it at the tap's click, from its state when the finger landed, so a second tap shuts it; iOS's late
  focus on the trigger is not focus outside. Why: a menu opened at a finger's press was shut by the rest of the tap.
- **Hover is for pointers that hover.** A hover fill shows only where the pointer can hover (Tailwind's `hover:`) or
  while a menu is open, and a ring only on `:focus-visible`, so a tap leaves neither. Where nothing hovers, row
  actions always show. A small mark (a chip's X, a slider's band, a row's action) keeps its drawn size and takes
  `.cad-hit`, a finger's 36px on a phone.
- **The picture's gestures become mouse events in one place** (`kit/viewport/touchGestures.js`). A double tap is a
  double-click (each tap within 350ms and 10px, the second within 300ms and 24px). A press held 500ms within 10px is a
  right-click, opening the menu at the finger. A second finger or more movement is neither. One finger orbits, two
  pan and zoom, and a tap picks, adding as Shift does; a pinch or a camera drag never picks. A press that would take
  something out of the selection waits the double-click window (`DOUBLE_CLICK_WAIT_MS`, 220ms; a finger's
  `DOUBLE_TAP_MS`, 300ms), and the double-click drops it: a 3D view's pick (`kit/tools/select/usePointerPick.js`) and a
  flat view's canvas (`kit/viewport/useFlatCanvasView.js`) alike, each asking its view's `takesAway`. What each gesture
  does: [Selection and gestures](viewer-ux.md#selection-and-gestures).
- **A finger reaches further on the picture**: an edge within 20px (within 16px it wins over the face under it), ink,
  a measurement or the eraser within 16px (`TOUCH_HIT_PX`), a joint's knob within 22px.
- **The pointer's kind never sets the layout**; only the viewer's width does. It may change how input is read (reach,
  slop, zoom speed, when a menu opens) and what waits for a hover (row actions, a peek, key hints). A canvas shows no
  iOS callout and selects no text.

### Keyboard focus

- **A ring only for the keyboard**, on `:focus-visible`, in `--ring`. shadcn's primitives keep their 3px ring at 50%
  (the slider's thumb at 40%); the chrome's own controls (tiles, tabs, navbar items, dropdown triggers, a card's X)
  draw 2px at 45%.
- **Focus goes back where it came from.** A closing menu, card or sheet hands it to its trigger (the peek and the
  phone's sheet to the panel toggle), and a hint does not open on focus handed back.
- **Tabs and trees.** A tab list is one Tab stop; ← and → move between tabs and wrap. Tree rows follow the WAI-ARIA
  tree pattern (`primitives/tree-keys.js`): ↓ and ↑ the next and previous row, Home and End, → opens or enters a
  branch, ← shuts it or goes to its parent, Enter and Space press the row.
- **The panel's grip** is a separator in the Tab order: ← and → by 16px, Home and End to its bounds.
- **Escape closes the innermost thing first**: a popup opened inside a card or the panel closes before the card or
  peek (`hasOpenPopup`), and an element marked `data-escape-owner` spends its own Escape. The rest of the order:
  [Keyboard](viewer-ux.md#keyboard).

## Checking a change

A rule changes here in the same change as its code, along with the test that holds its number. Tests exercise real
transitions and drawn sizes, not class names, and a test of a layout that is gone is replaced. Paths that start with
`scripts/test/` or `tests/python/` are the repository's.

| Test | What it holds |
| --- | --- |
| `designSystem.test.js` | the type tokens at both scales, no 10px step, no `text-[Npx]` and no stylesheet font size; no window breakpoint in chrome; every chrome scroll region a `ScrollArea`; menus at `text-xs` on the row, tooltips at `text-tiny`; the Home's type; the navbar's row; rows padded by the row primitive alone; only `SliderField` and the scrubber import the slider |
| `lib/scale.test.js` | `scale.js` equals the stylesheet's tokens, at both scales |
| `styles/canvas.test.js` | core's written-out colours equal the tokens, and every view's canvas is `--canvas` |
| `kit/look/sceneColors.test.js` | no view hard-codes a selection, hover or box blue |
| `file-viewer/panelPeek.test.js` | the slide's classes carry its duration constants; the fallback outlasts the slide |
| `kit/inspector/FieldLabels.test.tsx` | every control's label is `FieldLabel`, its value the foreground |
| `kit/shell/PanelInset.browser.test.mjs` | every piece of the panel's content on the 16px inset, in every tab of several files, placeholder rows too |
| `RendererShell.browser.test.mjs`: "a phone's scale", "every control and every text on the walk is its scale's" | 36px controls and each text 2px up on a phone, and no fill or ring left by a tap; on a phone and a desktop, every control and text on the view, the Display card, each tab, a menu, Quick Edit and Preview's Settings is its scale's |
| … "every popup trigger opens on one tap and shuts on a second tap on it" | the touch rule in the navbar, the strip, the Display card, the sheet and Preview's Settings |
| … "the type scale and the strip's proportions, as drawn" | the 40px strip of 28px tiles, the 32px head with its rule under the strip, panel and menu text 12/16, the navbar 13/20, a tooltip 11/16 |
| … "a toolbar button under the pointer is seen…", "Preview's bar takes the backdrop's ink…" | hover fills and ink read on their surface |
| … "three tabs and the search fit the 232px panel…", "Display's card is the peek card's mirror…" | the tab budget; the card's top, gaps and 12px inset, its 288px width, its dropdowns one width, nothing cut |
| `scripts/test/check-ui-strings.mjs`, `i18n/i18n.test.mjs` | no English literal in the chrome; the locales mirror `en.js` |
| `tests/python/global/test_document_links.py` | every relative link and `#anchor` in these docs lands on a heading |

Run the units with `scripts/test/test-js.sh --select ui-units` (the checks, the type check, the Node tests and Vitest)
and the browser specs with `--select ui-browser`. One file runs with
`npm --prefix packages/ui test -- src/designSystem.test.js`; a browser spec reads the built package, so run
`npm run build:packages` first. The link test is in `scripts/test/test-global.sh`.
