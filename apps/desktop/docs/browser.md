# Embedded browser

`src/main/browser/service.ts` owns one native `WebContentsView` per browser tab.
The UI and the session's browser tools operate on that same page. Unmounting a
browser tab hides its native view; it does not navigate, destroy or recreate the
page. Form values, page JavaScript, history and scroll therefore survive tab and
session switches. Closing a browser tab destroys its page. Session archive/deletion and
app shutdown dispose all affected pages. A change of the session's cwd or project
disposes the pages whose scope (session, project, real root) the new workspace no
longer names; pages in a scope it still names survive, and with no workspace left
all of the session's pages close. App restarts restore saved URLs; live
form state is not serialized across restarts.

Every page carries its immutable session ID, directory identity and canonical
workspace root. Browser tools derive all three from the authenticated session;
UI handlers validate the session and its root. IDs cannot be reused across
sessions, including two sessions in the same directory. Listing exposes only the
caller's pages. Storage partitions are hashed from session ID, directory and
root, prefixed with a hash of the session ID alone
(`persist:browser-<sha256(session)>-<scope hash>`, `browser/storage.ts`): pages in
one session share storage, separate sessions do not. Archiving keeps a session's
partitions and `browser-artifacts/<sha256(session)>`; deleting it clears the
partitions' storage and cache and removes the artifacts. A partition an older build named `browser-<sha256(scope)>` is
renamed to the current name on first use, and by the sweep that the first
renderer browser request of a run starts; that sweep also removes partitions and
artifact directories whose session no longer exists. Nothing opened this run is swept. An older partition is judged on
its own: one a live session's scope names (its realpath, or its recorded path when
the worktree is gone) is migrated, and removed when the current name already
exists; one no live session names is removed. Background
browser commands never navigate the user's session selection. A session switch
keeps its pages alive while hiding their presentation; this costs one Chromium
page per live tab.

## Playwright MCP

The browser registry entry selects the unmodified, pinned
[`@playwright/mcp`](https://github.com/microsoft/playwright-mcp) runtime (0.0.81).
Its published tool catalog, locators, actionability waits, snapshots, form input,
JavaScript/Playwright execution, file upload, screenshots and PDF capture run in
the agent's stdio subprocess. Core, PDF and coordinate/vision capabilities are
enabled. `snapshot.mode: none` and `codegen: none` keep action responses compact;
read snapshots or targeted `browser_find` results explicitly. Action timeout is
5 seconds, navigation 60 seconds, and post-action settling 500 milliseconds.

The manual local benchmark compared stock/compact Playwright MCP, Playwright CLI,
Browser Use's harness MCP/CLI and the previous adapter. Compact MCP passed all
fixture workflows and actionability probes while producing substantially smaller
responses than full accessibility dumps. Benchmarks and raw timing reports stay
under ignored `tmp/`; the durable acceptance tests are described below. These
measure tool overhead on local pages, not model reasoning or internet latency.

`browser_connection` is a private bridge bootstrap method, not an agent tool.
After authentication, `browser/connections.ts` resolves the session's real
workspace and returns a capability URL for `browser/cdp.ts`. That adapter exposes
only that workspace's native views through a loopback WebSocket with an
unguessable path and rejects browser-origin handshakes. Production never enables
Electron's process-wide remote-debugging port. Chromium target IDs remain intact
because Playwright uses them as main-frame identities; app tab IDs are mapped
inside the adapter. Each client gets independent native debugger sessions.
When the session's cwd or project changes, the bridge revokes the endpoint and
calls `BrowserConnections.disposePages`, which closes only the pages the new
workspace no longer names. Each call takes the next number of a per-session
generation that only rises (a revoke does not reset it), and after its
`realpath` only the newest call acts: changes A to B to C can finish out of
order, and B's late answer must not keep B's pages and close C's.

A tab id can be re-opened over new contents (archive, then a quick unarchive)
before Chromium reports the old ones destroyed. So the service's `destroyed`
handler ignores a target that a later page has replaced under the same id, and
the adapter keys its bookkeeping to the owning contents: a session bound to a
destroyed page is not the re-opened tab's, and the tab's live target id is kept
apart from the old page's until that one's detach is heard. When the debugger
detaches (DevTools taking the page over, or its contents closing) the adapter
forwards `Target.detachedFromTarget` for the native sessions of those contents,
so the client is told rather than left waiting; a crashed renderer does not
detach, and the client hears `Inspector.targetCrashed`. `service.events`, the
`opened` and `closed` stream, carries one listener pair per scoped CDP
connection and has a cap of 100 before Node warns of a leak. The console reads
`console-message`'s event details (`level`, `message`) and falls back to the
deprecated positional arguments. Closing a tab drops the `closed` listener it
put on the window presenting it.

Electron exposes PDF printing through `WebContents.printToPDF`, so the adapter
bridges that one operation with bounded in-memory CDP streams.
The adapter handles browser discovery and tab lifetime; page-domain calls go to
the owned `WebContents.debugger`. Create/select/close calls use the same renderer
commands as the tab strip. Other workspace targets, fabricated sessions and new
browser contexts are refused. Connection close detaches debugger sessions but
keeps tabs alive. Deleting, archiving or closing a session, or changing its
workspace, revokes the endpoint and cancels pending app commands. A change already applied to a page
cannot be undone by cancellation.

`build-mcp.mjs` bundles the app bridge entry and copies the pinned upstream MCP,
Playwright and Playwright Core distributions beside it, including their runtime
assets and notices. `out/text-to-cad-mcp/**` ships unpacked; the Electron binary runs
that entry as Node. Nothing downloads a second browser or installs agent config.
When upgrading, test the shipped directory outside the checkout: upstream uses
runtime assets that must not be reduced to a single esbuild bundle.

The native UI's existing typed CDP helpers still use the MIT Browser Use generated
bindings under `browser/vendor`; those bindings provide protocol types, not an
agent loop or MCP tool catalog. The previous custom browser MCP action layer has
been removed. Browser navigation, native context capture and IPC remain app-owned.

Navigation permits HTTP(S) and the initial `about:blank` page. Guests have no
Node, preload or app IPC and use sandbox/context isolation. Popups navigate their
owning tab; permission prompts are denied until a native permission workflow is
provided. text-to-cad owns pane size and partitions: browser resizing, installing a
browser, creating contexts and extensions are unsupported. Playwright's download artifact API is not bridged, and both
`Browser.` and `Page.setDownloadBehavior` are refused. A download the person starts keeps the native save dialog: the page
is shown and focused in the focused window, a real key or mouse press reached it
within the last two seconds, and no agent sent it input (CDP `Input.*` or the
app's input method) in that time. CDP input can reach the same input hooks as a
real press, so a page an agent is driving never passes; any other download (an agent in a
background session, a page's script while the person works elsewhere) is
cancelled rather than opening that dialog over their work, and counted as an
error in the page's console. These
constraints are reported rather than implemented as successful no-ops.

An address the tab cannot open is answered in words, and the answer stays: a
typed `file://` address is refused with "Only http and https addresses can be
opened here.", and a load that fails reaches the tab as "<host> could not be
reached: <error>". The tab keeps that sentence until the next navigation succeeds;
the poll that refreshes the page's title and history does not clear it.

A page that opens a window the tab cannot show (a `mailto:` link, a blocked scheme) adds
"Only http and https addresses can be opened here: <address> was not opened." to the tab's
console, and a refused download adds "Downloads are not supported in this browser tab.
Blocked: <file>." A `window.open` or `_blank` link to a web address still replaces the current
page: opening a second tab from main needs a new event channel to the renderer's tab strip,
which this tab does not have.

The stock MCP exposes JavaScript evaluation and file upload; its subprocess runs
with the agent's ordinary OS permissions. Target scoping protects app pages and
workspace partitions, not all filesystem or network effects of agent code.
Page content remains untrusted. A typed reference is an observation of a page,
not authorization to act on it.

The native view is positioned inside the explorer content slot. Renderer chrome
hides it while app dialogs and popover menus are open so native layers cannot
cover the app's controls. Presentation is measured at most once per animation
frame, and the metadata poll carries console lines only while the console panel
is open; a poll the workspace refuses (session inactive, workspace missing
or different) — or the tab is gone — stops polling until
a navigation or the console wakes it, and a repeated failure publishes no new
state. When the app window's own document navigates (a reload that got
past its unsaved-drafts question), fails a main-frame load (a dev server that is
down) or its renderer crashes, main hides every page that window
presented until a remounted tab presents it again. Cmd+R reloads the focused
browser page and nothing else; the app renderer has no reload accelerator in a
packaged build, and an unload with unsaved drafts asks first. Presentation leases prevent a stale tab's cleanup from
hiding its newer presentation. The URL, loading/navigation state and bounded
console are read from main, including agent and page-initiated navigation.

The address bar treats text with a scheme as a URL, and a dotted name, `localhost`,
an IP literal or `word:port` as an address; anything else is a search. It adds
`http://` for localhost, IP literals, `*.local` and any explicit port except 443
and 8443, and `https://` otherwise. `word:port` is an address because
docker-compose services, hosts aliases and MagicDNS names are far more common here
than searches shaped like `note:1`.

The field holds a draft while the person types, and the draft outlives blur, as
in Chrome and Safari. It is dropped by Escape, or by the page's URL moving while
the field is not focused; while the field is focused a URL change under it
never disturbs it. Enter commits: the resolved address then shows until the
page moves on to another URL, and an Enter that picks a candidate during input
method composition is ignored.

## Adding page context to a prompt

The browser toolbar offers selected text and page screenshot actions. Both add a
URL reference plus a text/PNG attachment through the same desktop prompt port
used by files and drawings. Selection is a `.txt` attachment so native capture
can finish asynchronously after the port has bound the tab's owner session. Capture
checks the page URL and navigation generation before and after reading it. The
generation counts new documents only — a single-page app's pushState or fragment
change is not one. A changed page fails explicitly. Switching sessions during capture cannot redirect
the attachment, existing draft text is preserved, and nothing is submitted.
Deleting or archiving the owner cancels delivery. A workspace mismatch fails
without redirecting context into another session.

## Validation

`tests/e2e/browser-mcp.spec.ts` builds the shipping MCP directory in a temporary
location, starts it against hidden Electron/local fixtures, and exercises stock
tools, forms, shadow DOM, screenshots, PDF, app tab lifecycle, reconnect and scope
revocation. It rejects foreign targets and forbidden schemes. It needs no browser
download. `integrations.spec.ts` additionally creates/closes a browser tab through
a real ACP session and the built renderer command relay.

`browser-service.spec.ts` covers native presentation, input, context capture,
partition isolation and cleanup. `explorer.spec.ts` checks the actual explorer
and browser IPC share one page across tab/project switches and add context to the
existing draft. Unit tests cover bridge authentication/cancellation, connection
lifetimes, presentation leases, owner reload/crash hiding, download refusal,
partition cleanup and prompt delivery after session switches.
