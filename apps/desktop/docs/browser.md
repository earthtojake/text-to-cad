# Embedded browser

`src/main/browser/service.ts` owns one native `WebContentsView` per browser tab.
The UI and the session's browser tools operate on that same page. Unmounting a
browser tab hides its native view; it does not navigate, destroy or recreate the
page. Form values, page JavaScript, history and scroll therefore survive tab and
session switches. Closing a browser tab destroys its page. Session archive/deletion and
app shutdown dispose all affected pages. App restarts restore saved URLs; live
form state is not serialized across restarts.

Every page carries its immutable session ID, directory identity and canonical
workspace root. Browser tools derive all three from the authenticated session;
UI handlers validate the session and its root. IDs cannot be reused across
sessions, including two sessions in the same directory. Listing exposes only the
caller's pages. Storage partitions are hashed from session ID, directory and
root: pages in one session share storage, separate sessions do not. Background
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

Electron exposes PDF printing through `WebContents.printToPDF`, so the adapter
bridges that one operation with bounded in-memory CDP streams.
The adapter handles browser discovery and tab lifetime; page-domain calls go to
the owned `WebContents.debugger`. Create/select/close calls use the same renderer
commands as the tab strip. Other workspace targets, fabricated sessions and new
browser contexts are refused. Connection close detaches debugger sessions but
keeps tabs alive. Deleting a session/project or changing its workspace revokes
the endpoint and cancels pending app commands. A change already applied to a page
cannot be undone by cancellation.

`build-mcp.mjs` bundles the app bridge entry and copies the pinned upstream MCP,
Playwright and Playwright Core distributions beside it, including their runtime
assets and notices. `out/hardcore-mcp/**` ships unpacked; the Electron binary runs
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
provided. Hardcore owns pane size and partitions: browser resizing, installing a
browser, creating contexts and extensions are unsupported. Playwright's download
artifact API is not bridged; native downloads keep the host's behavior. These
constraints are reported rather than implemented as successful no-ops.

The stock MCP exposes JavaScript evaluation and file upload; its subprocess runs
with the agent's ordinary OS permissions. Target scoping protects app pages and
workspace partitions, not all filesystem or network effects of agent code.
Page content remains untrusted. A typed reference is an observation of a page,
not authorization to act on it.

The native view is positioned inside the explorer content slot. Renderer chrome
hides it while app dialogs and popover menus are open so native layers cannot
cover the app's controls. Presentation leases prevent a stale tab's cleanup from
hiding its newer presentation. The URL, loading/navigation state and bounded
console are read from main, including agent and page-initiated navigation.

## Adding page context to a prompt

The browser toolbar offers selected text and page screenshot actions. Both add a
URL reference plus a text/PNG attachment through the same desktop prompt port
used by files and drawings. Selection is a `.txt` attachment so native capture
can finish asynchronously after the port has bound the tab's owner session. Capture
checks the page URL and navigation generation before and after reading it. A
changed page fails explicitly. Switching chats during capture cannot redirect
the attachment, existing draft text is preserved, and nothing is submitted.
Deleting or archiving the owner cancels delivery. A workspace mismatch fails
without redirecting context into another chat.

## Validation

`tests/e2e/browser-mcp.spec.ts` builds the shipping MCP directory in a temporary
location, starts it against hidden Electron/local fixtures, and exercises stock
tools, forms, shadow DOM, screenshots, PDF, app tab lifecycle, reconnect and scope
revocation. It rejects foreign targets and forbidden schemes. It needs no browser
download. `integrations.spec.ts` additionally creates/closes a browser tab through
a real ACP session and the built renderer command relay.

`browser-service.spec.ts` covers native presentation, input, context capture,
partition isolation and cleanup. `browser-app.spec.ts` checks the actual explorer
and browser IPC share one page across tab/project switches and add context to the
existing draft. Unit tests cover bridge authentication/cancellation, connection
lifetimes, presentation leases and prompt delivery after chat switches.
