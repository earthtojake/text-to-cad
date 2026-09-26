# Browser Use control bindings

`generated.ts` is an unmodified copy of `sdk/generated.ts` from the MIT-licensed
[browser-use/browser-harness-js](https://github.com/browser-use/browser-harness-js/tree/2d9a5ed37ed11f31b2622cd69c4b55f979cb905f)
commit `2d9a5ed37ed11f31b2622cd69c4b55f979cb905f`.
`generated.ts` SHA-256: `17d8b3718863d4a07046c6badc7e497c2d165d745a2cf9f04324ebb9acedf893`. Its `bindDomains(Transport)` is
the Browser Use runtime control API used by Hardcore, with Electron's target-local
`webContents.debugger` implementing its transport. This preserves the upstream
protocol implementation without its Bun REPL, browser discovery, installation
script or unrestricted browser-level WebSocket. The app only calls page-local
methods; agents receive the scoped operations in `shared/browser.ts`.

The accompanying MIT license ships with packaged app notices. To update, copy
these two upstream files from a reviewed exact commit, update this pin, and run
the browser service unit and real Electron browser tests. No network or package
installation occurs at app startup.
