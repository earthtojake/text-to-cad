# Workspace integrations

An integration groups a domain's app tools, focused skills and host services.
A tab is a view of a resource. The two are intentionally independent: a file
tab chooses a renderer, while several integrations can act on the same file.
The registry is the composition point, not a new user-visible mode or pane.

## Composition and ownership

[`src/main/integrations/registry.mjs`](../src/main/integrations/registry.mjs)
imports each domain's `module.mjs`. A module declares its ID, description,
skill directories, strict Zod tool contracts and optional renderer command
mapping. An external runtime can declare `runtime` and private `hostTools`
for authenticated bootstrap; its upstream package owns the agent tool catalog.
The browser uses this path for Playwright MCP, with no duplicate Zod catalog.
Registry validation rejects duplicate IDs and method names. The same
modules drive MCP tool registration and `scripts/build-skills.mjs`; changing
one domain does not require maintaining a second tool/skill catalog.

Each session receives separate `hardcore-<domain>` stdio MCP server entries.
They use the same packaged server executable with a different integration ID
and a distinct per-session, per-integration bearer token. The loopback bridge
validates the token, method ownership and input schema before dispatch. A PDF
server token cannot call terminal methods. Browser bootstrap opens a scoped native
CDP connection; subsequent browser actions run through the upstream MCP and that
adapter, rather than the HTTP action relay. Closing a session revokes its tokens.

The generic relay, bridge and skill materialization belong to
`src/main/integrations/`. CAD runtime startup, Python discovery, warm daemons
and viewer backend lifetime remain under `src/main/cad/`. Main owns native
services and filesystem effects. Renderer commands act on app resource stores;
shared UI supplies platform-independent, explicitly bound capabilities. Shared
UI never imports Electron, IPC, session stores or native filesystem code.

## Tabs and integrations

| Tab / renderer | Integration | Resource and operations |
| --- | --- | --- |
| Any scoped tab | `workspace` | Open files, reveal paths, list/show/close tabs, inspect an existing image; discover supplied skills |
| File / `code` or `markdown` | `documents` | Read the editor buffer, replace against a live revision, explicitly save against disk revision |
| File / `pdf` | `pdf` | Read page state/text, select visible page, capture a page from the same PDF.js document |
| File / `cad` | `cad` | Read actual model/selection/camera state, select/clear topology references, control camera/mode, capture the mounted viewport |
| File / `image` or unsupported | `workspace` | Open/reveal the file; image renderer or explicit unsupported presentation |
| Browser | `browser` | Navigate and inspect the actual embedded page, input through its accessibility/CDP nodes, capture it |
| Terminal | `terminals` | Create/read/write/stop an app-owned PTY using the same terminal identity as the tab |
| Drawing | `drawings` | Open/name/rename a sketch, read its identity/element count, capture it for visual context |
| Review | Workspace navigation | Existing git review workflow; it does not create a separate review MCP integration |

File kind remains `file`. CAD and PDF are renderer choices, not sibling tab
kinds. `list_open_tabs` returns the tab ID and renderer where applicable. IDs
are scoped by project and workspace root, and a reused file tab must also match
the resource path before a live capability or retained snapshot is accepted.
Paths on disk are resolved against the session's project/worktree using main's
normal realpath boundary. A matching filename in another root is not the same
resource.

## Lifetimes and conflict behavior

Removing a project revokes its integration credentials and releases retained app resources.
Switching tabs or projects does not mean closing their resources. Opening or
showing a tab explicitly changes focus; background state reads do not select
another project or redirect the person's current view.

| Resource | Inactive behavior | Close behavior |
| --- | --- | --- |
| Text | Unsaved buffers remain in window memory; read returns a retained snapshot with `active: false`. Editing/saving requires reactivation. | Dirty tabs refuse ordinary/tool close. The UI offers explicit discard; clean closure releases records. |
| PDF | Retains the last page/selection snapshot, marked inactive; page extraction/capture/navigation requires the mounted document. | Releases worker, loading task, text layer and capability. |
| CAD | Retains serializable last-view state, marked inactive; viewport changes and capture require the mounted model. | Releases controller registration and inactive snapshot; shared CAD cache policy remains separate. |
| Browser | Main retains the actual page and its navigation state; presentation can detach without destroying it. Tools address that page even in the background. | Destroys the app-owned page. |
| Terminal | The PTY and bounded output buffer continue independently of the mounted xterm view. | Releases the app-owned process and terminal resources. Stop keeps its output available until close. |
| Drawing | Renderer memory retains the serialized scene. | Discards the sketch. Drawings are also discarded on reload or app exit. |

Text's live revision is an opaque buffer token, separate from `diskRevision`.
An edit compares the live token synchronously, including two commands arriving
before React renders. A save separately uses the existing atomic filesystem
write and disk-revision check. Conflicts preserve the draft and never force a
write. Cancellation revokes pending relay work and prevents later admission; an already
issued filesystem write cannot be rolled back. External edits mark dirty drafts stale; clean views refresh normally.
Explicit reload discards the current draft. Draft retention is not recovery
across application exit and never serializes source bytes into camera settings.

Browser page text, accessibility labels, terminal output and document content
are untrusted data. They cannot change integration scopes or become tool
instructions. Playwright MCP includes page evaluation and short Playwright scripts
in its stdio subprocess; native target scope is enforced by the host adapter.
It is not an OS sandbox for agent code (see [browser](browser.md)). Terminal writes require the
observed output sequence and input revision; new output or intervening user
input requires another read.

The PDF renderer and its agent tools share one real Mozilla PDF.js document,
worker and text layer. Page reads are bounded to 50 pages/one million
characters and canvases to 4096 pixels on the longest side. Extraction does not
perform OCR. See the [PDF domain notes](../src/main/integrations/pdf/README.md)
for the upstream MCP assessment and the independently reused, Apache-licensed
OpenAI PDF skill.

## Prompt context is a separate operation

A capture tool returns an image to the agent. An **Add to prompt** action
prepares a draft through the existing `PromptContextPort`; neither submits a
prompt. The producer freezes file/revision, selected range or page, and capture
identity before asynchronous encoding. Desktop binds the compatible draft
destination before awaiting bytes and rechecks it before accepting them.
Switching chats cannot deliver an in-flight capture into the new chat.
Workspace mismatches use the existing explicit “Start chat here” recovery.

Code and Markdown source selections carry zero-based UTF-16 ranges and selected
text. PDF context includes a page image and any selected text. Browser context
preserves its URL/generation; CAD context preserves model/selection identity.
Terminal context contains the frozen selected output and its working directory.
Drawing context is a temporary sketch description and PNG. See the shared
[viewer host contract](../../../packages/ui/docs/viewer-host.md) for portable
bundles, delivery receipts and capability limits.

## Skills and provider tools

Skills are focused instructions, composed as real files into the session's
additional skills root. There is no required umbrella `hardcore-app-use` skill,
plugin install, marketplace entry or edit to an agent's global configuration.
The registry supplies browser, PDF, documents, terminals, drawings and the
embedded `cad-viewer` skill. Other repository CAD authoring skills still ship;
the standalone viewer-launching skill is replaced by the embedded handoff.
Native skill loaders receive the root on session creation/load, while other
adapters receive the concise existing skill preamble and workspace skill-read
tools. Vendored upstream skills retain their license and provenance.

A provider's built-in filesystem and shell tools still work on disk. They are
not the live-document API and cannot observe an unsaved editor buffer. Likewise,
a provider-owned terminal/process ID is not an app-owned PTY ID. Use document
integration tools when the task concerns the person's live draft; use the
provider's disk tools for ordinary repository work, then open completed results
through workspace tools. Watchers reconcile changed disk artifacts with views.
The bundled CAD runtime remains on session PATH; integrations do not install
another runtime or replace the person's agent configuration.

## Adding a domain

1. Add `src/main/integrations/<domain>/module.mjs` using `definition.mjs`'s
   `tool` helper. Declare strict bounded schemas, JSON/image result kind and
   unique method names. Supply focused skill paths relative to `apps/desktop`,
   or an empty list when the domain needs no skill.
2. Import the module in `registry.mjs`. The manager then supplies its own MCP
   server identity; the server and skill build consume the same registration.
3. Implement a domain service/actions factory and compose its handlers in
   `initIntegrations` in `src/main/integrations/index.ts`. Resolve session project/root in
   main, and check concrete resource identity again in the service. Use scoped
   file APIs for disk access. Keep generic bridge code free of domain branches.
4. If the operation needs renderer state, declare its typed command under
   `src/shared/ipc/integrations.ts` and dispatch through
   `src/renderer/state/integration-commands.ts`. Bind shared capabilities via an
   explicit host port. Do not discover another tab's DOM or instantiate a second
   hidden copy of its document just to answer tools.
5. Define mount, inactive read, close, project removal and cancellation behavior.
   Decide whether a stale result is refused or returned as a named snapshot;
   never silently substitute a different revision or current tab. Mutations
   need conflict/ownership policy and truthful completion receipts.
6. Add tests for scope, wrong path/revision, background reads, cleanup and late
   results. Exercise the real underlying renderer/service in an integration
   test. Rebuild shared exports, the desktop and composed skills/MCP bundle;
   run the dependency boundary check and affected test runners.

New integrations do not require a new tab kind or a new sidebar section.
Expose user-facing controls only where that domain's existing view needs them.
