# chat-ui — Technical Architecture

`@emdash/chat-ui` is a framework-agnostic, high-performance chat transcript
renderer built on **SolidJS**. It is designed to render very long, continuously
streaming AI conversations (10k+ rows) at 60fps without layout thrash.

It achieves this by separating three concerns that most chat UIs entangle:

1. **Measurement** — computing the exact pixel height/geometry of every row in
   pure JavaScript _before_ touching the DOM (using [`pretext`](#3-pretext--off-dom-text-measurement) for text shaping).
2. **Virtualization** — only mounting the handful of rows currently on screen,
   using a [Fenwick tree](#4-the-fenwick-tree-virtualizer) for O(log n) scroll math.
3. **Projection** — rendering each visible row by walking a precomputed
   [layout tree](#5-the-measurecomposeproject-rendering-pipeline) and applying
   geometry via inline styles (no CSS-driven reflow).

The result is a renderer where adding a token to a streaming message, or
scrolling through thousands of rows, costs `O(log n)` rather than `O(n)`, and
where the browser never re-flows content it has already laid out.

---

## Table of contents

- [1. High-level architecture](#1-high-level-architecture)
- [2. SolidJS — the reactive substrate](#2-solidjs--the-reactive-substrate)
- [3. pretext — off-DOM text measurement](#3-pretext--off-dom-text-measurement)
- [4. The Fenwick tree virtualizer](#4-the-fenwick-tree-virtualizer)
- [5. The measure/compose/project rendering pipeline](#5-the-measurecomposeproject-rendering-pipeline)
- [6. The data model & transcript store](#6-the-data-model--transcript-store)
- [7. End-to-end flow: a streaming token](#7-end-to-end-flow-a-streaming-token)
- [8. Scroll virtualization in motion](#8-scroll-virtualization-in-motion)
- [9. Caching strategy](#9-caching-strategy)
- [10. How the concepts interact](#10-how-the-concepts-interact)

---

## 1. High-level architecture

The package exposes three primitives modeled on the CodeMirror `EditorState`/`EditorView`
split (`src/index.tsx`). Everything else is internal.

```
ChatContext (global singleton, process-long)
  theme, Shiki highlighter, content-addressed caches, measureEpoch

ChatState (per conversation, survives view mounts)
  transcript (history + active turn), messageId parse caches

ChatView (per mount, DOM-scoped)
  Solid root, virtualizer, scroll, scheduler, composer slot
```

```mermaid
flowchart TD
  Host["Host app"]
  Host -->|"createChatContext()"| Ctx["ChatContext<br/>(theme, caches, measureEpoch)"]
  Host -->|"createChatState(ctx)"| State["ChatState<br/>(transcript + parse caches)"]
  Host -->|"createChatView(ctx, state, parent)"| View["ChatView<br/>(scroll, collapse, composerSlot)"]
  Host -->|"state.transcript.history.seed(items)"| State
  Ctx --> View
  State --> View

  subgraph Engine["ChatRoot (Solid root, owned by ChatView)"]
    Transcript["transcript signals"] --> CountEffect["count-sync effect<br/>virt.setCount(estimate)"]
    CountEffect --> Virt["Virtualizer<br/>(Fenwick tree)"]
    Scroll["scroll / resize signals"] --> VisRange["visibleRange memo"]
    Virt --> VisRange
    VisRange --> For["For each visible index"]
    For --> Row["Row"]
    Row -->|measure| Measure["ComponentDef.measure()"]
    Measure -->|"Measured tree"| Project["Project (tree walker)"]
    Measure -->|"exact height"| Virt
    Project --> DOM["Positioned DOM"]
    Slot["Composer slot<br/>(sticky bottom)"] -->|ResizeObserver| PadBottom["padBottom signal"]
  end

  subgraph Support["Cross-cutting services"]
    Pretext["pretext<br/>(glyph measurement)"]
    Caches["ChatCaches<br/>(SharedCaches ∪ ParseCaches)"]
    Theme["ChatTheme<br/>(fonts + density)"]
  end

  Measure -.uses.-> Pretext
  Measure -.uses.-> Caches
  Measure -.reads.-> Theme
```

The key architectural inversion: **layout is computed first, in JS, and the DOM
is a pure projection of that layout.** The browser is never asked to measure or
wrap text — `pretext` does that off-DOM, and every element is positioned with an
explicit `top`/`left`/`height`.

### State-view separation

`ChatState` outlives `ChatView`. A view can be disposed and re-created (e.g.
when a tab is shown/hidden) without losing the transcript. Block object identities
are stable across view cycles, so WeakMap measurement caches continue to hit on
re-mount.

Collapse state is owned by `ChatView` (it is view state, not model state). The
`view.saveState()` / `view.restoreState()` API snapshots and restores it across
re-mounts.

### Hardened scheduler

`ChatRoot` runs a three-phase measure cycle (`read → animate → write`) driven by
`requestAnimationFrame`. The scheduler is created eagerly (before any row
mounts), is exception-safe (phases run in `try/finally`), and includes a bounded
converge check (halts after `MAX_CONVERGE` consecutive write-requests to prevent
infinite loops). A `forceReconcile()` call is fired on visibility regain so the
view self-heals after being hidden or inert.

### Cache split

| Cache type | Owner | Key | Lifetime |
| --- | --- | --- | --- |
| `SharedCaches` | `ChatContext` | Content hash | Process-long |
| `ParseCaches` | `ChatState` | messageId | Conversation lifetime |

`SharedCaches` are safe to share across conversations because they are keyed by
content (a different conversation with the same code block reuses the highlight
result). `ParseCaches` are messageId-keyed and provide object-stable `Block`
identities so WeakMap measurement caches hit across streaming updates.

---

## 2. SolidJS — the reactive substrate

The renderer is built on Solid because Solid's **fine-grained reactivity** maps
perfectly onto "only re-run the computation whose specific input changed."

Unlike React's re-render-the-component-tree model, Solid components run **once**;
afterward, only the individual reactive computations (`createMemo`,
`createEffect`, JSX expressions) that read a changed signal re-execute.

### Primitives in use

| Primitive | Where | Purpose |
| --- | --- | --- |
| `createSignal` | `ChatRoot` (`scrollTop`, `viewHeight`, `totalHeight`, `containerWidth`) | Scalar reactive state driving the visible range. |
| `createStore` | `state/transcript.ts` | Fine-grained nested reactivity: mutating one item's `text` only notifies readers of that path. |
| `createMemo` | `ChatRoot` (`visibleRange`, `visibleIndexes`), `Row` (`layout`) | Cached derived values; recompute only when dependencies change. |
| `createEffect` | `Row` (height bridge), `ChatRoot` (count-sync, width flush) | Side effects synchronizing JS state into the virtualizer / DOM. |
| `createContext` / `useContext` | `ThemeContext`, `CachesContext`, `CommandsContext` | Dependency injection without prop drilling. |
| `createRoot` | `createChatState`, `createChatContext` | Owner-scoped reactive roots; `dispose()` cleans up all signals and effects. |
| `<For>` | `ChatRoot` (visible rows), `Project` (placed children) | Keyed list rendering — reuses DOM nodes by key. |
| `<Switch>/<Match>` | `Project` | Dispatch a layout node to the right sub-renderer by `layout.kind`. |

### The "Lane A / Lane B" state split

A core discipline (documented in `src/core/define.ts`) divides state into two lanes:

- **Lane A — layout-affecting state.** Only `width`, `theme.version`, and
  resolved `expanded` state may flow into `measure()`/`estimate()`. These are the
  _only_ inputs allowed in the memo fingerprint and the _only_ things that can
  trigger `virt.setSize`.
- **Lane B — presentational/ephemeral state.** Copy-button "copied" flags, hover,
  shimmer, timer ticks — these live as local signals inside `Render` components
  and **never** enter measurement.

This separation is what guarantees that a hover or a copy-click can never
invalidate a height and cause a scroll jump.

```mermaid
flowchart LR
  subgraph LaneA["Lane A — affects height"]
    W[width] --> Measure
    TV[theme.version] --> Measure
    EX["expanded(id)"] --> Measure
    Measure["measure() / estimate()"] --> Fingerprint["memo fingerprint"]
    Fingerprint --> Virt["virt.setSize"]
  end
  subgraph LaneB["Lane B — never affects height"]
    Hover[hover] --> Render
    Copied[copied] --> Render
    Tick[timer tick] --> Render
    Render["Render component (local signals)"]
  end
```

---

## 3. pretext — off-DOM text measurement

**The problem:** to virtualize, you must know each row's height _before_ you
render it. For text, height depends on line-wrapping, which depends on glyph
widths — normally only the browser knows these, and only after layout.

**The solution:** `@chenglou/pretext` measures glyph widths and computes
line-breaking entirely off-DOM (via `OffscreenCanvas` text metrics), so the
engine can compute exact prose height in pure JS.

### The measurement contract

Because measurement happens off-DOM, the rendered DOM must reproduce pretext's
metrics _exactly_. This is enforced by:

- **Font shorthands** in `FontConfig` (`src/core/measure/fonts.ts`) that exactly
  match the CSS `font` applied to each fragment variant (body/bold/italic/code/…).
- **Geometry-coupled CSS** in `prose.module.css` (`font-size`, `font-family`,
  `white-space: pre`, `line-height: 1`, inline-code chip padding) that pretext
  also accounts for via `extraWidth`.
- **Browser contract tests** (`*.contract.test.tsx`) that mount the real
  component and assert `def.measure(...).height === element.offsetHeight`.

### The pipeline for one prose block

```mermaid
flowchart LR
  MD["markdown string"] -->|"remark parse"| Blocks["Block[]<br/>(document model)"]
  Blocks -->|"ProseBlock.runs"| R2R["runsToRichItems()"]
  R2R -->|"RichInlineItem[]<br/>(text + font + extraWidth)"| Prep["prepareRichInline()"]
  Prep -->|"PreparedRichInline"| Walk["walkRichInlineLineRanges(width)"]
  Walk -->|"per-line ranges"| Mat["materializeRichInlineLineRange()"]
  Mat -->|"fragments + x offsets"| Laid["ProseLaidOut<br/>(lines, fragments, height)"]
```

`layoutProse` (`src/components/prose/layout.ts`) drives this:

1. Splits `runs` at `{ kind: 'break' }` markers into independently-shaped segments.
2. For each segment, converts runs → `RichInlineItem[]` (mapping bold/italic/
   code/mention to the matching font shorthand + extra width).
3. Calls `prepareRichInline` (memoized — see [§9](#9-caching-strategy)).
4. `walkRichInlineLineRanges(prepared, effectiveWidth, …)` yields each wrapped
   line; `materializeRichInlineLineRange` gives the fragments and their x offsets.
5. Produces a `ProseLaidOut` with absolute per-line `top` and per-fragment `x` —
   pure geometry, no DOM.

`measureProseNaturalWidth` runs the same shaping with an unbounded width to get
the intrinsic content width — used by the user-bubble hug algorithm.

The `Prose` renderer (`src/components/prose/Prose.tsx`) then just emits absolutely
positioned `<span>`s at the precomputed `(x, top)` — no wrapping, no reflow.

---

## 4. The Fenwick tree virtualizer

`src/core/virtualizer.ts` is the heart of scroll performance. It maintains every
row's pixel height in a **Fenwick tree** (Binary Indexed Tree) so the operations
the scroll loop needs are all `O(log n)`:

| Operation | Meaning | Complexity |
| --- | --- | --- |
| `setSize(i, h)` | a row was measured; update its height | `O(log n)` |
| `top(i)` | prefix sum — pixel offset of row `i` | `O(log n)` |
| `total()` | total canvas height | `O(1)` (running sum) |
| `findIndex(offset)` | binary-lift: which row is at pixel `offset` | `O(log n)` |
| `range(scrollTop, viewH)` | inclusive visible `{start, end}` | `O(log n)` |

### Why a Fenwick tree?

A naive virtualizer recomputes cumulative offsets in `O(n)` whenever any row's
height changes — catastrophic when a streaming row's height changes every token.
The BIT makes both the update (`setSize`) and the reverse lookup (`findIndex` via
**binary lifting** over the tree) logarithmic.

```mermaid
flowchart TD
  subgraph BIT["Fenwick tree (1-indexed)"]
    direction TB
    Sizes["sizes[]: per-row truth (Float64Array)"]
    Tree["bit[]: range partial sums"]
    Total["totalSize: running O(1) sum"]
  end

  setSize["setSize(i, h)"] -->|"delta = h - old"| Tree
  setSize --> Total
  top["top(i)"] -->|"prefix sum [0,i)"| Tree
  findIndex["findIndex(offset)"] -->|"binary lift"| Tree
  Total --> total["total()"]
```

### Growth strategy

Streaming appends one message per turn, so `setCount` is tuned for the
append-at-tail case: growing keeps existing BIT entries valid and builds only the
new high-index nodes from their children — `O(log n)` per appended row.
`prepend` (history pagination) shifts sizes and rebuilds the BIT in one `O(n)`
pass, which is acceptable for user-paced "load older" actions.

### Scroll-anchor correction

`setSize` returns the signed pixel delta `(newH - oldH)`. When a row _above_ the
viewport changes height (e.g. a collapsed thinking row expands off-screen, or an
estimated row settles to its real height), `ChatRoot.onHeightChanged` adds that
delta to `scrollTop` so the content the user is looking at doesn't jump.

---

## 5. The measure/compose/project rendering pipeline

Every row kind (message, thinking, diff, tool, file-op, execute) and every block
tier (prose, code, table) is described by a **`ComponentDef`** (`src/core/define.ts`):

```ts
type ComponentDef<TNode, L> = {
  kind: string;
  padY?: number;
  collapse?: CollapseDecl;
  estimate(node, ctx: MeasureCtx): number;          // O(1) heuristic
  measure(node, ctx: MeasureCtx): Measured<L>;       // exact geometry
  Render: Component<{ item; layout: Measured<L>; ctx }>;
};
```

All defs are gathered in a single `REGISTRY` (`src/components/registry.ts`) keyed
by node kind. `Row.tsx` dispatches through it; composite rows dispatch their
block children through the same map.

### Step 1 — `estimate`: cheap height for every row

When the item count changes, `ChatRoot` seeds the virtualizer with an `O(1)`
character-count heuristic for **every** row (visible or not). This gives a
plausible total canvas height instantly without measuring off-screen content.

### Step 2 — `measure`: exact geometry for visible rows only

`measure` runs only for rows in the visible range. It returns a `Measured<L>`:

```ts
type Measured<L> = { height: number; width: number; layout: L };
```

Rather than each def hand-rolling its geometry, layout is assembled from **pure
combinators** in `src/core/compose.ts`. Each returns a `Measured` whose
`layout.kind` discriminates its payload:

| Combinator | Builds |
| --- | --- |
| `stack(children, {padY, gap})` | vertical sequence; accumulates child heights |
| `pad(child, {padX, padY, border})` | uniform padding + border |
| `bubble(child, {padX, variantClass, width})` | hug-width user message bubble |
| `collapsible({headerH, headerSlot, expanded, body})` | header + optional body |
| `scrollWindow(child, maxH, {overlay, autoScrollBottom})` | clip tall content to a viewport |
| `slot(name, height)` | named placeholder for non-generic chrome (headers/footers) |

> **Width flows down, height flows up.** Callers narrow the width budget before
> calling `measure`; combinators sum child heights upward. This is the
> single invariant that keeps the whole tree consistent.

For example, an assistant message's `measure` produces:

```mermaid
flowchart TD
  msg["messageDef.measure()"] --> stack["stack"]
  stack --> bs["layoutBlockStack(blocks)"]
  stack --> footer["slot('message:footer')"]
  bs --> p1["prose leaf"]
  bs --> c1["code leaf"]
  bs --> p2["prose leaf"]
```

### Step 3 — `Project`: render the tree

`src/components/Project.tsx` is a generic tree-walker. Given the `Measured` tree,
it recurses by `layout.kind` through a Solid `<Switch>`:

- **Combinator nodes** (stack/pad/bubble/collapsible/window) → positioned `<div>`s
  with explicit geometry, recursing into children.
- **Slot nodes** → resolved from the `slots` map the Render shell supplies
  (this is how non-generic chrome like a diff header or message footer is injected
  into the otherwise-generic walk).
- **Block leaves** (prose/code/table) → `renderBlockLeaf`, which uses the `raw`
  back-reference on each leaf to construct `Prose`/`Code`/`Table` without a
  second lookup.

So a `Render` component is a thin shell: it sets the row height, supplies slots,
and delegates the entire body to `<Project>`.

```mermaid
flowchart TD
  Render["ComponentDef.Render (shell)"] --> Project["Project(node, slots)"]
  Project -->|"kind === 'stack'"| PStack["ProjectStack"]
  Project -->|"kind === 'collapsible'"| PColl["ProjectCollapsible"]
  Project -->|"kind === 'window'"| PWin["ProjectWindow (auto-scroll)"]
  Project -->|"kind === 'slot'"| Slots["slots[name] → header/footer chrome"]
  Project -->|"block leaf"| Leaf["renderBlockLeaf → Prose / Code / Table"]
  PStack --> Project
  PColl --> Project
  PWin --> Project
```

### The height bridge (`Row.tsx`)

`Row` ties measurement to the virtualizer:

```ts
const layout = createMemo(() => cachedMeasure(item, isActiveTurn, measureCtx()));
const reserved = () => layout().height + 2 * padY();
createEffect(() => {
  const delta = virt.setSize(index, reserved());
  if (delta !== 0) onHeightChanged(index, delta);
});
```

When measurement yields a new height, the effect writes it into the Fenwick tree
and triggers scroll-anchor correction if needed — closing the loop.

---

## 6. The data model & transcript store

`src/state/transcript.ts` is a Solid `createStore` with a **two-tier** structure:

- `committed: readonly ChatItem[]` — finalized rows; never mutated.
- `activeTurn: ChatItem[] | null` — the in-flight turn; accumulates streaming
  deltas.

Writes go through a single `dispatch(event)` reducer. Events are deltas
(`message_chunk`, `thinking_chunk`, `diff_update`, …); `turn_done` migrates the
active turn into `committed`.

```mermaid
flowchart LR
  Ev["dispatch(event)"] --> Reducer["produce() reducer"]
  Reducer -->|"streaming deltas"| AT["activeTurn[]"]
  Reducer -->|"turn_done"| Commit["committed[]"]
  AT -->|"item.text += chunk"| Path["fine-grained path-set"]
  Path --> Solid["Solid notifies only<br/>readers of that path"]
```

The two-tier split is a **performance boundary**: committed items are stable
object references, which lets the identity-based memo (`nodeMemo`, a `WeakMap`
keyed by the item object) skip re-measuring them entirely. Only `activeTurn` rows
— the ones actually changing — bypass that cache and re-measure each tick.

Collapse flags are owned by `ChatView` as view state (a `createStore` keyed by
item id). They survive within a view's lifetime and can be snapshotted via
`view.saveState()` / `view.restoreState()` when the view is torn down and re-created.

---

## 7. End-to-end flow: a streaming token

This sequence shows what happens when the host appends one token to a streaming
assistant message — the hot path that must stay cheap.

```mermaid
sequenceDiagram
  participant Host
  participant Store as Transcript store
  participant Root as ChatRoot
  participant Row
  participant Def as messageDef
  participant Pretext
  participant Virt as Virtualizer
  participant DOM

  Host->>Store: dispatch(message_chunk)
  Store->>Store: activeTurn item.text += chunk (path-set)
  Store-->>Row: reactive: item.text changed
  Row->>Def: measure(item, ctx)  (activeTurn → bypass nodeMemo)
  Def->>Def: parseBlocks(id, text) (cached; reuses old Block refs)
  Def->>Pretext: prepareRichInline(last block only)
  Note over Def,Pretext: earlier blocks hit blockMemo (WeakMap by Block identity)
  Pretext-->>Def: line geometry
  Def-->>Row: Measured tree (new height)
  Row->>Virt: setSize(index, height) → delta
  alt row above viewport
    Virt-->>Root: onHeightChanged → adjust scrollTop
  end
  Row->>DOM: Project walks tree → positioned spans
  alt stuck to bottom
    Root->>DOM: scroll to bottom
  end
```

The reason this is cheap despite firing on every token:

- **`parseBlocks`** reuses Block object references for unchanged content, so only
  the last (growing) block is new.
- **`blockMemo`** (a `WeakMap` keyed by Block identity) means every earlier block
  is a measurement cache hit; only the last block is reshaped by pretext.
- **`setSize`** is `O(log n)` regardless of transcript length.

---

## 8. Scroll virtualization in motion

When the user scrolls, only signals change — no data is touched.

```mermaid
sequenceDiagram
  participant User
  participant Scroll as scroll listener (rAF)
  participant Root as ChatRoot
  participant Virt as Virtualizer
  participant For as For (visible rows)
  participant Row

  User->>Scroll: scroll event
  Scroll->>Root: setScrollTop / setScrollVelocity (rAF-batched)
  Root->>Virt: range(scrollTop, viewH, before, after)
  Note over Root,Virt: direction-aware overscan<br/>(more buffer ahead of travel)
  Virt-->>Root: { start, end } (binary lift, O(log n))
  Root->>For: visibleIndexes memo updates
  For->>Row: mount entering rows / unmount leaving rows
  Row->>Row: measure on first appearance
  Row->>Virt: setSize (estimate → exact); settle scroll
```

Key details:

- The scroll handler is **rAF-batched** and writes only signals; the visible
  range is a `createMemo` so it recomputes only when `scrollTop`/`velocity`/
  `totalHeight` change.
- **Direction-aware overscan**: a larger leading buffer in the direction of
  travel (`OVERSCAN_LEADING = 12`) and a small trailing one (`OVERSCAN_TRAILING = 3`)
  pre-mount rows just before they enter, avoiding blank flashes.
- Rows are positioned with `transform: translateY(top)` against an absolutely
  sized canvas (`totalHeight + padTop + padBottom`), and carry
  `contain: layout paint style` to isolate their reflow.

---

## 9. Caching strategy

Caching is layered, and **all mutable data caches are per-instance** (owned by a
`ChatCaches` bundle created in `ChatRoot`, `src/core/caches.ts`) so two mounted
chats never share state and teardown is a single `caches.clear()`.

```mermaid
flowchart TD
  subgraph PerInstance["ChatCaches (per ChatRoot)"]
    PB["parseBlocks — markdown→Block[] by id"]
    RI["prepareRichInline — pretext shaping by content"]
    HL["highlight — Shiki tokens (LRU 200)"]
    DF["computeDiff — Myers rows (LRU 100)"]
  end

  subgraph Identity["Identity memos (WeakMap, GC'd)"]
    NM["nodeMemo — by ChatItem (Row.tsx)"]
    BM["blockMemo — by Block (block-stack.ts)"]
  end

  subgraph Global["Shared global (stateless / immutable)"]
    Engine["Shiki highlighter engine"]
    Consts["fonts, lang tables, metrics"]
  end

  Measure["measure path"] -->|ctx.caches| PerInstance
  Render["render leaves (Code, Diff)"] -->|useCaches()| PerInstance
  Row --> NM
  BlockStack["layoutBlockStack"] --> BM
  PerInstance -.token engine.-> Engine
```

| Layer | Key | Bound | Reach |
| --- | --- | --- | --- |
| `nodeMemo` | `ChatItem` identity | `WeakMap` (auto-GC) | skips whole-row re-measure for committed rows |
| `blockMemo` | `Block` identity | `WeakMap` (auto-GC) | skips per-block re-measure inside streaming rows |
| `parseBlocks` | `messageId` + text | per-instance Map | identity-stable Block refs across re-renders |
| `prepareRichInline` | shaped content | per-instance Map | reuse pretext shaping; flushed on width/font change |
| `highlight` | `lang + code` | per-instance LRU(200) | Shiki tokenisation |
| `computeDiff` | `oldText + newText` | per-instance LRU(100) | Myers diff rows |

Two reach channels exist because caches are touched in two execution contexts:

- **Measure path** has a `MeasureCtx` → reached via `ctx.caches`.
- **Render leaves** (`Code`, `Diff`) live deep in `Project` with no `MeasureCtx`
  → reached via a Solid `CachesContext` + `useCaches()`.

**Invalidation:** on container-width or font-load change, `caches.clearTextMeasure()`
drops the rich-inline cache _and_ flushes pretext's internal global metrics (which
are keyed only by font string and would otherwise hold stale fallback-font widths
from before the webfont loaded). The identity memos self-invalidate via their
fingerprint (`theme.version | width | collapsed | expanded`).

The **Shiki highlighter engine** stays a global singleton — it is stateless and
expensive to initialize (grammar/theme construction); only its token _results_
are cached per-instance.

---

## 10. How the concepts interact

Putting it together, the four pillars compose into one tight loop:

```mermaid
flowchart TB
  subgraph Data["Data layer (SolidJS stores)"]
    TS["Transcript store (committed + activeTurn)"]
    VS["View state (collapse flags, expandedUserId)"]
  end

  subgraph MeasureLayer["Measurement (pure JS, off-DOM)"]
    Parse["markdown → Block[]"]
    PT["pretext: glyph metrics + line-breaking"]
    Comp["compose combinators → Measured tree"]
  end

  subgraph VirtLayer["Virtualization"]
    FT["Fenwick tree: heights, offsets, visible range"]
  end

  subgraph RenderLayer["Projection (SolidJS DOM)"]
    Pr["Project: walk tree, position via inline styles"]
  end

  TS -->|"item count"| FT
  TS -->|"visible item text"| Parse
  Parse --> PT
  PT --> Comp
  Comp -->|"exact height"| FT
  Comp -->|"Measured tree"| Pr
  VS -->|"expanded/collapsed"| Comp
  FT -->|"which rows + offsets"| Pr
  Pr --> Screen["Screen"]
  Screen -->|"scroll / resize"| FT
```

1. **SolidJS** stores hold the conversation and view state, and notify exactly the
   computations that read changed paths.
2. **pretext** turns text into exact geometry _before_ the DOM exists, satisfying
   the precondition for virtualization.
3. The **Fenwick tree** uses those heights to answer "what's on screen?" and
   "where does row _i_ sit?" in `O(log n)`, and absorbs height changes without
   `O(n)` recomputation.
4. **Projection** renders only the visible rows by walking the precomputed
   `Measured` tree and applying geometry as inline styles — so the browser never
   re-wraps or re-flows content the engine already laid out.

The discipline that makes it hold together is the **Lane A / Lane B** split and
the **width-down / height-up** invariant: measurement depends only on layout
inputs, geometry is computed purely, and the DOM is a faithful projection of that
geometry — never a source of truth.

---

## Adding a new row kind

This recipe walks through adding a hypothetical `'status'` row kind. Replace `status` / `ChatStatus` / `StatusLayout` with your actual names throughout.

### 1. Define the model type

Add your item shape to `src/model.ts`:

```ts
export type ChatStatus = {
  kind: 'status';
  id: string;
  text: string;
};

export type ChatItem = ChatMessage | ChatThinking | ChatDiff | ChatFileOpToolCall | ChatStatus;
```

### 2. Implement the `ComponentDef`

Create `src/components/status/status.def.tsx`. A `ComponentDef<Item, Layout>` requires:

| Member | Role |
| --- | --- |
| `kind` | String literal matching `ChatItem.kind` |
| `padY` | Symmetric vertical padding (px) around the row |
| `estimate(item, ctx)` | O(1) height heuristic; used before measure for scroll-thumb sizing |
| `measure(item, ctx)` | Exact geometry; returns `Measured<Layout>` (may use compose combinators) |
| `Render` | SolidJS component `(props: { item, layout, ctx }) => JSX.Element` |

Example skeleton:

```tsx
import { defineComponent, type Measured, type MeasureCtx, type RenderCtx } from '../../core/define';
import type { ChatStatus } from '../../model';

type StatusLayout = { kind: 'status'; height: number };

export const statusDef = defineComponent<ChatStatus, StatusLayout>({
  kind: 'status',
  padY: 4,

  estimate(_item, ctx: MeasureCtx): number {
    return ctx.theme.fonts.body.lineHeight;
  },

  measure(item, ctx: MeasureCtx): Measured<StatusLayout> {
    const height = ctx.theme.fonts.body.lineHeight;
    return { height, width: ctx.width, layout: { kind: 'status', height } };
  },

  Render(props: { item: ChatStatus; layout: Measured<StatusLayout>; ctx: RenderCtx }) {
    return (
      <div style={{ height: `${props.layout.height}px` }}>
        {props.item.text}
      </div>
    );
  },
});
```

#### Using slots

If your row needs injected chrome (a header, footer, or side-panel):

1. Add a new entry to `SLOT_NAMES` in `src/core/compose.ts`:

   ```ts
   STATUS_HEADER: 'status:header',
   ```

2. Use it in `measure()`:

   ```ts
   import { SLOT_NAMES, slot, stack } from '../../core/compose';

   const headerSlot = SLOT_NAMES.STATUS_HEADER;
   const tree = stack([
     { id: `${item.id}:header`, measured: slot(headerSlot, headerH) },
     { id: `${item.id}:body`,   measured: body },
   ], { gap: 0 });
   ```

3. Supply the slot renderer in `Render`:

   ```tsx
   <Project
     node={props.layout.layout.tree}
     slots={{ [SLOT_NAMES.STATUS_HEADER]: () => <StatusHeader item={props.item} /> }}
   />
   ```

### 3. Register the def

Add one line to `src/components/registry.ts`:

```ts
import { statusDef } from './status/status.def';

export const REGISTRY: Record<string, ComponentDef<ChatItem, any>> = {
  // … existing entries …
  status: statusDef,
};
```

### 4. Add fixtures

Add representative `ChatStatus` items to the mock transcript fixture
(`src/mock-transcript.ts` or the fixture generator) so that the benchmark
and visual snapshot tests cover the new kind:

```ts
{ kind: 'status', id: 'status-1', text: 'Indexing…' },
```

### 5. Add a height contract test

Create `src/tests/status.contract.test.tsx`. The contract test verifies that
`measure()` returns an exact height, protecting against slot-height drift:

```tsx
import { describe, expect, it } from 'vitest';
import { DEFAULT_THEME } from '../core/theme';
import { createChatCaches } from '../core/caches';
import { makeContractCtx, renderAndMeasure } from './contract';
import { statusDef } from '../components/status/status.def';

const ctx = makeContractCtx({ width: 640 });
const item: ChatStatus = { kind: 'status', id: 's1', text: 'Indexing…' };

describe('statusDef height contract', () => {
  it('measure height matches rendered height', async () => {
    const layout = statusDef.measure(item, ctx);
    const renderedH = await renderAndMeasure(
      <statusDef.Render item={item} layout={layout} ctx={/* RenderCtx */} />,
      layout.height
    );
    expect(renderedH).toBe(layout.height);
  });
});
```

The `renderAndMeasure` helper (see `src/tests/contract.tsx`) mounts the
component in a headless browser, reads the actual DOM height, and compares
it to the engine's prediction. A failing test here means a slot height
constant or padding value is wrong.

---

## File map

| Concern | Files |
| --- | --- |
| Public API | `src/index.tsx` |
| Global context | `src/chat-context.ts` |
| Per-conversation state | `src/state/chat-state.ts`, `src/state/transcript.ts` |
| Per-mount view | `src/chat-view.tsx`, `src/ChatRoot.tsx` |
| Data model | `src/model.ts` |
| Markdown | `src/core/markdown/{document,parse,plain-text}.ts` |
| Measurement | `src/core/measure/*`, `src/components/prose/layout.ts` (pretext) |
| Virtualization | `src/core/virtualizer.ts`, `src/core/stick-to-bottom.ts` |
| Frame scheduler | `src/components/engine/frame-scheduler.ts`, `src/core/tween-registry.ts` |
| Layout system | `src/core/define.ts`, `src/core/compose.ts`, `src/core/layout/*` |
| Rendering | `src/components/Project.tsx`, `src/components/Row.tsx`, `src/components/*/` |
| Registry | `src/components/registry.ts` |
| Slot names | `src/core/compose.ts` (`SLOT_NAMES`, `SlotName`) |
| Caching | `src/core/caches.ts`, `src/components/CachesContext.ts` |
| Theme | `src/core/theme.ts`, `src/core/metrics.ts`, `src/core/measure/fonts.ts` |
| Contexts | `src/components/{ThemeContext,CachesContext,CommandsContext}.ts` |
