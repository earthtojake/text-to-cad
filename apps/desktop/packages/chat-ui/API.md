# @emdash/chat-ui — Public API

A Solid-based chat transcript renderer with a pretext layout engine. It
virtualizes long conversations, renders markdown/code/diffs/tool calls, and
exposes three primitives modeled on the CodeMirror `EditorState`/`EditorView`
split for fine-grained lifecycle control.

The package ships a single entry point:

- `@emdash/chat-ui` — the three factory functions `createChatContext`,
  `createChatState`, and `createChatView`.

The React wrapper (`ChatTranscript`) and theme adapter (`chat-theme.css`) now
live in `@emdash/ui/react/chat-ui`. See that package for React integration docs.

Everything below is the supported surface. Internals (components, layout
engine, stores) are not exported and may change without notice.

---

## Installation & styles

```ts
import { createChatContext, createChatState, createChatView } from '@emdash/chat-ui';
import '@emdash/chat-ui/style.css';
```

The mount container must have a **fixed height** — the virtualizer measures the
scroll viewport, so a zero-height or auto-height container renders nothing.

---

## Architecture overview

```
ChatContext (global singleton)
  └─ owns: theme, Shiki highlighter, content-addressed caches, measureEpoch

ChatState (per conversation)
  └─ owns: transcript (history + active turn), messageId-keyed parse caches

ChatView (per mount)
  └─ owns: Solid root, virtualizer, scroll, hardened scheduler, collapse state,
          composer slot + ResizeObserver → padBottom
```

These three objects map to the CodeMirror `EditorState`/`EditorView` model:
- `ChatContext` is the shared language server / environment.
- `ChatState` is the `EditorState` — the model, independent of any DOM mount.
- `ChatView` is the `EditorView` — the DOM owner, created and destroyed on demand.

A `ChatState` survives across `ChatView` mount/unmount cycles, so re-attaching a
view (e.g. after a tab becomes visible) reuses warm measurement caches and
preserves transcript state without re-fetching.

---

## Quick start (Solid / vanilla)

```ts
import { createChatContext, createChatState, createChatView } from '@emdash/chat-ui';
import '@emdash/chat-ui/style.css';

// Once per app (or per conversation set):
const ctx = createChatContext({ stickToBottom: true });

// Once per conversation:
const state = createChatState(ctx);

// Once per mount (re-creatable on show/hide):
const view = createChatView({
  context: ctx,
  state,
  parent: document.getElementById('chat')!,
  composer: 'slot',    // internal sticky slot; ResizeObserver drives padBottom
  stickToBottom: true,
  commands: {
    onOpenFile: ({ path }) => openInEditor(path),
  },
  onViewMounted: (v) => {
    // Portal a React/HTML composer into the sticky slot:
    ReactDOM.createPortal(<ChatComposer />, v.composerSlot!);
  },
});

// Seed historical items directly through the state (works before view mounts):
state.transcript.history.seed([
  { kind: 'message', id: 'u1', role: 'user', text: 'Hello!' },
]);

// Stream a turn:
state.transcript.activeTurn.set(
  applyTurnEvent([], { type: 'message_chunk', id: 'a1', role: 'assistant', text: 'Hi ' }),
  'generating'
);
state.transcript.activeTurn.commit('done');

// Scroll to bottom:
view.scrollToBottom({ behavior: 'smooth' });

// Tear down in reverse order:
view.dispose();    // tears down Solid root and DOM; does NOT dispose context or state
state.dispose();   // clears parse caches and Solid reactive root
ctx.dispose();     // clears shared caches and Solid reactive root
```

---

## Quick start (React)

```tsx
import { createChatContext, createChatState, ChatTranscript } from '@emdash/ui/react/chat-ui';
import '@emdash/chat-ui/style.css';

// Create once at app startup:
const chatCtx = createChatContext();

function Chat() {
  const chatState = useMemo(() => createChatState(chatCtx), []);
  useEffect(() => () => chatState.dispose(), [chatState]);

  useEffect(() => {
    chatState.transcript.history.seed(initialItems);
  }, [chatState]);

  return (
    <div style={{ height: '100%' }}>
      <ChatTranscript
        context={chatCtx}
        state={chatState}
        composer="slot"
        stickToBottom
        onReady={(view) => {
          // view.composerSlot is available here
        }}
      />
    </div>
  );
}
```

---

## `createChatContext(opts?)`

```ts
function createChatContext(opts?: ChatContextOptions): ChatContext;
```

Creates a global-services singleton. Safe to create once per app and reuse
across all conversations. Owns the Shiki highlighter, content-addressed caches
(highlight / diff / mermaid / richInline), and a `measureEpoch` signal that
invalidates geometry caches on font load or typography changes.

### `ChatContextOptions`

| Option | Type | Description |
| --- | --- | --- |
| `theme` | `ChatTheme` | Full resolved theme. Defaults to `DEFAULT_THEME`. |
| `config` | `ChatConfig` | Typography + chip geometry. Ignored when `theme` is set. |
| `highlighter` | `ChatHighlighter` | Syntax-highlighting adapter. Defaults to the bundled Shiki adapter. |
| `mentionProvider` | `MentionProvider` | Synchronous @-mention resolver. |

### `ChatContext`

| Member | Type | Description |
| --- | --- | --- |
| `theme` | `ChatTheme` | Resolved theme used for all views sharing this context. |
| `config` | `ChatConfig` | Config that produced the theme. |
| `mentionProvider` | `MentionProvider \| undefined` | The @-mention resolver. |
| `sharedCaches` | `SharedCaches` | Content-addressed caches shared across conversations. |
| `measureEpoch` | `() => number` | Reactive accessor. Bump to invalidate all geometry caches. |
| `bumpEpoch()` | `void` | Bump `measureEpoch`. Call after font or typography changes. |
| `dispose()` | `void` | Dispose reactive root. Safe to call after all views are disposed. |

---

## `createChatState(ctx)`

```ts
function createChatState(ctx: ChatContext): ChatState;
```

Creates per-conversation state. Wraps `createTranscript()` and the
messageId-keyed parse caches under a `createRoot` so both survive across
`ChatView` mount/unmount cycles.

### `ChatState`

| Member | Type | Description |
| --- | --- | --- |
| `transcript` | `TranscriptApi` | Reactive transcript (history + active turn). Seed/stream through here. |
| `parseCaches` | `ParseCaches` | Per-messageId parse caches. Provides object-stable `Block` identities for WeakMap measurement hits. |
| `dispose()` | `void` | Clear parse caches and dispose the Solid reactive root. |

---

## `createChatView(opts)`

```ts
function createChatView(opts: ChatViewOptions): ChatView;
```

Renders a Solid root into `opts.parent` and returns a `ChatView` handle.
The view reads `context` and `state` for theme, caches, and transcript data.

Call `view.dispose()` to unmount. The context and state are NOT disposed — the
host manages their lifetimes independently.

### `ChatViewOptions`

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `context` | `ChatContext` | — | **Required.** Global services. |
| `state` | `ChatState` | — | **Required.** Per-conversation model. |
| `parent` | `HTMLElement` | — | **Required.** DOM element to render into. |
| `composer` | `'slot' \| 'none'` | `'none'` | When `'slot'`: renders a sticky bottom slot; internal ResizeObserver drives `padBottom`. Use `view.composerSlot` to portal content into it. |
| `stickToBottom` | `boolean` | `false` | Auto-scroll to bottom as content streams in. |
| `pinUserMessages` | `boolean` | `false` | Pin the active turn's user message to the top while scrolling. |
| `class` | `string` | — | Extra class on the scroll container. |
| `contentClass` | `string` | — | Class for the centered content column. |
| `padTop` | `number` | `0` | Top padding (px) baked into the virtualizer coordinate space. |
| `padBottom` | `number` | `0` | Bottom padding. Ignored when `composer === 'slot'`. |
| `commands` | `ChatCommands` | `{}` | Initial command callbacks. Update via `view.setCommands`. |
| `onReachStart` | `() => void` | — | Called when scrolled near the top. |
| `onAtBottomChange` | `(b: boolean) => void` | — | Called when the "at bottom" state changes. |
| `onViewMounted` | `(view: ChatView) => void` | — | Called once after mount. `view.composerSlot` is available here. |

### `ChatView`

| Member | Type | Description |
| --- | --- | --- |
| `composerSlot` | `HTMLElement \| null` | Sticky bottom slot element (non-null only when `composer === 'slot'` and after mount). Portal a composer into this element. |
| `setCommands(c)` | `void` | Replace command callbacks without remounting. |
| `scrollToBottom(opts?)` | `void` | Scroll to the bottom of the transcript. |
| `scrollToItem(id, opts?)` | `void` | Scroll to the row for the given item id. |
| `loadOlder(items)` | `void` | Prepend older history items without losing scroll position. |
| `toggleCollapsed(id)` | `void` | Toggle the collapsed state of an item by id. |
| `setContentPadding(p)` | `void` | Update canvas padding without remounting (`bottom` ignored when `composer === 'slot'`). |
| `saveState()` | `ChatViewSnapshot` | Snapshot collapsed items and expanded-user-id. |
| `restoreState(snap)` | `void` | Restore a previously snapshotted view state. |
| `dispose()` | `void` | Tear down the Solid root. Does NOT dispose context or state. |

---

## `ChatCommands`

Callbacks injected by the host to respond to user actions:

| Callback | Signature | Description |
| --- | --- | --- |
| `onOpenFile` | `({ path, itemId, source }) => void` | User clicked a file path (diff, file-op, resource-link, prose-link). |
| `onViewImage` | `({ attachment, itemId, source }) => void` | User clicked an image attachment or generated-image card. |
| `onStop` | `({ itemId }) => void` | User clicked the stop button during generation. |
| `classifyLink` | `(href) => { kind: 'workspace-file'; path: string } \| { kind: 'external' }` | Classify a markdown `href` at render time (must be synchronous). |
| `onViewMermaid` | `({ chart, blockId, source }) => void` | User clicked a Mermaid diagram preview. |

---

## `TranscriptApi`

Accessed via `state.transcript`.

### History

```ts
state.transcript.history.seed(items: ChatItem[]): void;
state.transcript.history.prepend(items: ChatItem[]): void;
state.transcript.history.get(): ChatItem[];
```

`seed()` replaces the entire history and is idempotent for the same array.
`prepend()` adds items before existing history (for infinite-scroll pagination;
triggers scroll-position correction).

### Active turn

```ts
state.transcript.activeTurn.set(items: ChatItem[], status: TurnStatus): void;
state.transcript.activeTurn.commit(finalStatus: 'done' | 'cancelled'): void;
state.transcript.activeTurn.get(): ChatItem[];
```

The active turn is the in-progress assistant response. `set` drives streaming
updates; `commit` finalizes it and moves items into committed history.

---

## Scroll helpers

### `ScrollToItemOptions`

```ts
type ScrollToItemOptions = {
  align?: 'start' | 'center' | 'end';  // default: 'start'
  offset?: number;                      // default: 0
  behavior?: ScrollBehavior;            // default: 'auto'
};
```

---

## Theme

```ts
import { buildChatTheme, DEFAULT_CONFIG, DEFAULT_THEME } from '@emdash/chat-ui';
import type { ChatTheme, ChatConfig } from '@emdash/chat-ui';

const theme = buildChatTheme(myConfig);          // build from config
const ctx   = createChatContext({ theme });      // or pass directly
```

The `ChatTheme` drives all typography constants used during measurement. Changing
it after context creation requires calling `ctx.bumpEpoch()` to invalidate
geometry caches. Color changes are free (CSS-variable themed; no re-measurement
needed).

---

## Highlighter

```ts
import { createDefaultHighlighter } from '@emdash/chat-ui';

const highlighter = await createDefaultHighlighter();
const ctx = createChatContext({ highlighter });
```

`createDefaultHighlighter` returns the bundled Shiki adapter (em-light/em-dark
themes, common languages). Pass a custom `ChatHighlighter` implementation to
override.

---

## Mention provider

```ts
import type { MentionProvider } from '@emdash/chat-ui';

const provider: MentionProvider = {
  resolve(token: string) {
    return { id: token, label: token, name: token, kind: 'file' };
  },
};

const ctx = createChatContext({ mentionProvider: provider });
```

---

## Data model

See [`src/model.ts`](src/model.ts) for the full `ChatItem` discriminated union.
Key kinds:

| `kind` | Description |
| --- | --- |
| `'message'` | User or assistant chat message (supports markdown, image attachments). |
| `'tool'` | Tool/function call row. |
| `'file-op'` | File read/write/patch operations. |
| `'execute'` | Shell command execution. |
| `'thinking'` | Expandable thinking block. |
| `'diff'` | Code diff (before/after). |
| `'resource-link'` | Single-line file/URL/opaque reference. |
| `'plan'` | Structured plan with status entries. |

---

## Exported values

- Functions: `createChatContext`, `createChatState`, `createChatView`, `buildChatTheme`, `DEFAULT_THEME`, `DEFAULT_CONFIG`, `createDefaultHighlighter`, `createTranscript`, `applyTurnEvent`, `finalizeTurn`, `createStreamSmoother`, `generateMockTranscript`, `mockMentionProvider`, `createChatCaches`.
- Types: `ChatContext`, `ChatContextOptions`, `ChatState`, `ChatView`, `ChatViewOptions`, `ChatViewSnapshot`, `ChatCommands`, `ScrollToItemOptions`, `ChatItem` and variants, `TranscriptApi`, `ChatTheme`, `ChatConfig`, `ChatHighlighter`, `MentionProvider`, `ChatCaches`, `SharedCaches`, `ParseCaches`.
