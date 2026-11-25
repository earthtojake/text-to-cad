# Wordmarks

`logo-c.svg` (the navbar's logo, over the home and over a document alike, which opens the app
menu) and `logo-cad.svg` (copied with the set; nothing in the viewer draws it yet) are copies of
the docs site's committed `public/brand/` marks of the same names, so every app draws the same marks from this package (the TEXTTOCAD wordmark stays the
docs site's: nothing in the viewer draws it). Refresh them with
`node scripts/brand/export-logos.mjs` rather than editing them by hand.

# Open in's marks

`file-viewer/navigation/appMarks.jsx` draws each app Open in offers by its own mark where one is
published under a licence this package can ship, one colour (the text's), each path copied unchanged:

- Visual Studio Code: `vscode.svg` of [Codicons](https://github.com/microsoft/vscode-codicons)
  0.0.46 (`@vscode/codicons`), © Microsoft Corporation, licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Cursor, Zed, PyCharm, Sublime Text, FreeCAD, Bambu Studio (Bambu Lab's mark), Blender and Rhino: the
  `cursor`, `zedindustries`, `pycharm`, `sublimetext`, `freecad`, `bambulab`, `blender` and
  `rhinoceros` icons of [Simple Icons](https://simpleicons.org) 16.37.0, CC0.

Every other app (Autodesk Fusion, SolidWorks, Solid Edge, OrcaSlicer, PrusaSlicer, Plasticity,
and KiCad, whose mark Simple Icons lists under GPL-3.0) is drawn with Lucide's
`AppWindow` until a mark under such a licence exists; no mark is drawn here by hand. The places
are Lucide's `Globe` (the browser), `Folder` (the file manager) and `ExternalLink` (the default app).
The marks are their owners' trademarks, shown only to name the app a file opens in.
