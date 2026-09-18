# Embedded browser

`src/main/browser/service.ts` owns one native `WebContentsView` per browser tab.
The UI and the session's browser tools operate on that same page. Unmounting a
browser tab hides its native view; it does not navigate, destroy or recreate the
page. Form values, page JavaScript, history and scroll therefore survive tab and
project switches. Closing a browser tab destroys its page. Project removal and
app shutdown dispose all affected pages. App restarts restore saved URLs; live
form state is not serialized across restarts.

Every page carries the project ID and a canonical workspace root. Browser tool
handlers derive these from the authenticated session, and UI handlers validate
roots with `rootOf`. IDs cannot be reused across roots. Listing only returns the
caller's root. Storage partitions are hashed from project ID plus canonical root:
tabs in one root share cookies and storage, while projects and worktrees do not.
A project switch keeps the background pages alive, even when no browser chrome
is mounted. This costs one Chromium page per live tab.

## Browser Use runtime

Control uses `bindDomains(Transport)` from the MIT open-source
[Browser Use JavaScript harness](https://github.com/browser-use/browser-harness-js/tree/2d9a5ed37ed11f31b2622cd69c4b55f979cb905f),
pinned at `2d9a5ed37ed11f31b2622cd69c4b55f979cb905f`.
The unmodified generated bindings are checked into `src/main/browser/vendor`.
`harness.ts` implements the transport with the owned page's Electron debugger.
No application-wide remote-debugging endpoint, Chrome profile discovery, Bun
runtime, cloud API, paid account or first-run install is involved. Electron-vite
bundles the bindings into main; electron-builder includes their MIT notice in
`Resources/notices/browser-use-browser-harness-js-LICENSE`.

The upstream Session class assumes a browser-wide WebSocket and optional Bun
profile discovery. We use its exported transport boundary instead: the upstream
typed domain methods execute directly on a page we own, with no ability to
attach to the app shell or another root. This is a browser control integration;
it does not embed Browser Use's separate model loop.

## Operations and observation

`shared/browser.ts` declares `list`, `open`, `state`, `screenshot`, `navigate`,
`input` and `close`. A service invocation receives a trusted scope separately
from its validated arguments. `state` supplies visible accessibility nodes with
backend IDs, roles, names, values and properties, a bounded page text extract,
and viewport/scroll information. Returned page content is untrusted. A screenshot
captures the same page as PNG. Input supports node clicks/focus, coordinates,
text insertion/replacement, common keys and scrolling. Inspect state again after
navigation; old node IDs are not reusable document references. `open` with an
existing tab ID reacquires the page; explicit navigation uses `navigate`.

Navigation permits HTTP(S) and the internal initial `about:blank` page. Guests
have no Node, preload or app IPC, use sandbox and context isolation, and cannot
open unmanaged windows: a popup navigates its owning tab. Permission prompts are
denied until the app supplies a user-facing permission workflow. The browser
integration does not expose arbitrary JavaScript, raw CDP, filesystem uploads,
external browser profiles, extensions, PDF printing or credential APIs.
Accessibility state may omit cross-origin frame content; screenshots and point
input remain available. Site-specific unsupported controls report CDP errors.

The native view is positioned inside the explorer content slot. Renderer chrome
hides it while app dialogs and popover menus are open so native layers cannot
cover the app's controls. Presentation leases prevent a stale tab's cleanup from
hiding its newer presentation. The URL, loading/navigation state and bounded
console are read from main, including agent and page-initiated navigation.

## Adding page context to a prompt

The browser toolbar offers selected text and page screenshot actions. Both add a
URL reference plus a text/PNG attachment through the same desktop prompt port
used by files and drawings. Selection is a `.txt` attachment so native capture
can finish asynchronously after the port has bound the destination. Capture
checks the page URL and navigation generation before and after reading it. A
changed page fails explicitly. Switching chats during capture cannot redirect
the attachment, existing draft text is preserved, and nothing is submitted.
A workspace mismatch uses the shared Start chat here recovery.

## Validation

`tests/e2e/browser-service.spec.ts` launches hidden Electron against a local HTTP
fixture, invokes the real Browser Use bindings on the displayed native target,
changes a form and clicks its button, captures PNG, hides and re-presents the
page across root changes, checks stale presentation cleanup, rejects another
root and non-web URL, checks partition isolation and closes project pages.
`browser-app.spec.ts` verifies the actual built explorer and browser IPC share
one native page through tab/project switches, captures page/selection into the
existing composer draft, and closes the native page with its strip tab.
`browser-store.test.ts` covers presentation leases, overlay hiding, late mounts
and close; `browser-prompt.test.tsx` verifies selection and screenshot delivery
to the original draft after a chat switch without submitting.
It needs Electron already installed by the workspace; it downloads no browser.
