# Viewer layout and patterns

This document is the viewer's layout and its patterns: where each control goes and why, what each kind of file shows,
and how the page behaves as it loads, selects, measures, draws and presents. It binds both apps (the web page and the
CAD app). A change to the layout or to a pattern changes this document in the same change. Its companion,
[design-system.md](design-system.md), holds what this one builds with: the two scales, type, colour, surfaces, motion,
one component for each job, and the input rules.

## Where things go, and why

**The placement rule.** What a person changes often stays on screen: a tool, the cube, the zoom. What they change now
and then goes in the panel or behind a menu: how the picture is drawn (the Display card), a board's layer display (the
Layers tab), Zoom to selection (the zoom menu and the view's menu). The screen belongs to the model. The controls
around it are few, and each stands in the same place for every file.

| Region | Holds | Never holds | Why |
|---|---|---|---|
| **Navbar**, across the top | Left: the logo (the way home), the panel toggle, Back and Forward (the CAD app), the project's name, the file's name and its ⋯. Right: a put-away alert, Display, Preview, the host's actions | Tools, a switch for one file type, the camera, a list of documents, the person's settings | One bar, the same over every file and the home, so each control is where the person last found it |
| **Panel**, at the left | Over a file: its structure (Model, Links, Parts, Nets, Layers), then what the file declares (Params, Joints, Animation), and one search over its trees. Over the home: its places. At its foot on both: the app's links (GitHub, Discord, X, Send feedback) and Settings | Tools, how the picture is drawn, what is selected; over a file, other documents | It is where the page on screen is read: a file's structure and its own settings, the home's places. One panel, behaving one way on both pages, leaves the rest of the view to the model or the place. The app's own links and settings have one place, its foot, the same on the home and over a document |
| **Tool strip**, top centre of the view | The file's own tools, and under it the row of the tool in hand | View controls (Display, Preview, projection, zoom), a tool the file cannot use | Tools are used most, so they stay in reach, in the same place and order in every file |
| **The corner**, top right of the view | Camera navigation only: the cube on a 3D view, one "100%" zoom menu on a flat view | Display settings, tools, +/− buttons, a Home button | The corner is where the picture is looked at from. A setting or a tool there would mix moving the camera with changing the picture |
| **Display card**, under the navbar at the right | How the picture is drawn: Projection, Style, Background, Show grid, and a board's Side and Mode | A camera reset, anything changed often | One place for every file type, so a person always finds it. It is changed now and then, so it waits behind a button |
| **Quick Edit**, bottom centre | The note to the agent, what it carries (picks, ink) as chips, and Copy, Queue, Send | Settings, tools | Always there, so it is where the eye left it. The bottom of the view is its alone |
| **Preview**, the whole view | The model presented: its own bar (the name, Settings, Exit), its Settings card, its playbar | Tools, the panel, the corner, Quick Edit | A mode of the whole view, not a setting of it: the picture alone, as it will be seen |

These reasons decide the cases the table does not:

- **How the picture is drawn lives in one place for every file type**: the Display card, opened by the same cube in the
  same place. A model's projection and style, a board's side, mode and style, and any file's Background are its rows,
  so a person who changed the Background on a model finds it again on a drawing.
- **The corner is only for navigating the camera.** Its zoom menu holds zoom commands and nothing else. Zoom to fit is
  already F, a double-click on empty space and an item of every menu, so there is no Home button and no +/−.
- **The panel is for reading the file and setting what it declares.** Parameters, joints and routines are the file's
  own, so they are tabs after its structure. A board's layers and their display are the file's layers, changed now and
  then, so they are the Layers tab's, as in KiCad's Appearance panel.
- **A board's Side and Mode are about how it is drawn,** so they are Display's: not the Layers tab's, which lists the
  board's layers, and not navbar switches, since the navbar is the same for every file.
- **Tools go on the strip, and only tools.** Display and Preview are not tools: pressing one leaves the tool in hand.
- **What is selected is read in Quick Edit's chips,** never in a panel pane: the panel's lists are the hierarchy.
- **The panel is the document's own.** Moving to another document is the navbar's (the project's name), the keys' (`[`
  and `]`, ⌘K) and the search's, never a tab beside the model. Why: a list of other documents leading the panel hid the
  model's own tree, which is what the panel is for.
- **What is the app's, not a file's or a place's, is the panel's foot**: the links out and the person's settings, in
  one row under a rule at the panel's bottom, the same on every page that has a panel
  ([The panel's foot](#the-panels-foot)). Nothing else of the app's is in the panel.
- **The browser's tabs are the viewer's tabs.** There are no document tabs in the page: wherever a document or a project
  is named, opening it in a new tab is laid out plainly (a real link, Open in new tab, ⌘Enter).
- **Nothing moves under the pointer.** The strip and Quick Edit are centred on the whole view and no panel moves them. A
  peek pushes nothing. Search replaces the panel's head row. A card opens over the view and never pushes it.
- **What belongs to the picture takes the picture's colours.** Whatever is drawn over a 2D or 3D view (the loading
  cover, the update line, the corner, Preview's bar and cover) follows the view's Background or Preview's backdrop,
  never the app's theme. Chrome on a surface of its own (the navbar, the panel, the strip, the cards, Quick Edit,
  menus) keeps the app's theme ([The viewport's scheme](design-system.md#the-viewports-scheme)).

## The page

The viewer has two pages. A file's page is the navbar over the view: the panel at the view's left, the picture, and the
chrome that floats over the picture. The home is the navbar over the library: its places in the same panel at the left
([The panel](#the-panel)), and the place on screen.

- `FileViewer.tsx` owns the navbar and its menus. `ViewFrame.jsx`, the one frame every renderer mounts (2D or 3D), owns
  everything in the view: the panel, the strip and the row under it, the update line, the corner, the Display card,
  Quick Edit and Preview's chrome. A renderer brings its canvas, tools, tool rows, tabs and document state, and the
  frame never looks inside a format ([cad-renderer.md](cad-renderer.md#kit)).
- A pick or a tool never opens the panel, and never closes the pinned panel.
- The navbar is always there, over a file and over the home, in every host. Only Preview (which draws its own bar) and
  a compact view are without it: a compact view (a small inline view) draws the model alone, with
  no navbar, panel, tools, corner or Quick Edit.
- An open Display card stands over the strip and covers the cube; menus, tooltips and dialogs stand over everything
  ([Layering](design-system.md#layering)).

### The navbar

- One row, the control's height plus 12px (40px; 48px on a phone), the strip's height, on `bg-sidebar` with a rule
  under it, the same over every file and the home (`ViewerNavbar.jsx`, `navbarRow.js`).
- It is there from the first paint: the web page draws a static bar before its script runs, then `StartingView.tsx`
  draws the real frame, logo, toggle and name included; for the home, its sidebar too, open or shut and as wide as the
  tab kept it, with placeholder rows. Why: nothing appears or moves as the app takes over.
- **Left**, edge to edge: the logo; the panel toggle (over a file that has a panel, and over the home); Back and
  Forward where the host keeps the view's history (the CAD app; desktop only, disabled with nowhere to go); for a
  document in a project, the project's name and a slash, muted, which goes to that project's page on the home, at the
  folder the document is in (Figma's location before a file's name); the file's name (no glyph, no menu of its own); its ⋯. Apart from the toggle (the
  strip's tile), they have no fill at rest, the accent fill on hover and while their menu is open; the name and the ⋯
  have no tooltip, since each says what it is. The Tab key moves through them in that order.
- **The logo comes first.** Why: it is the way home, and a way somewhere stands in the same place on every page. The
  toggle is there only where the page has a panel, so first it would move the logo on every page that has none.
- **The logo is the way home**, wherever the host has a home: over a document, over one still loading or that failed
  to open, and over the home itself, where it goes to Recents. It is a real link where the host gives the home an
  address (the web page): a plain click goes home in this view, and ⌘ or Ctrl and a click, a middle click or the
  link's own menu open the home in a new tab. Elsewhere (the CAD app) it is a button. Its hint says "Home". It opens no
  menu. Why: the mark in a page's corner is where people press to go home, and a menu there hid the way behind a
  second press.
- **A host with no home** (a view that shows one file alone, as the CAD app's file handler does) has no foot in its
  panel ([The panel's foot](#the-panels-foot)), so there the logo opens the app menu itself, with no hint, and the
  menu holds everything: nothing is offered twice.
- **The project's name** is a real link where the host gives the project's page an address (the web page): a plain
  click shows it in this view, and ⌘ or Ctrl and a click, a middle click or the link's own menu open it in a new tab. It
  truncates as the row narrows down to 80px; under that, and always on a phone, it is a control-sized folder tile named
  by the project (its name in a hint), so the way to the project is never lost, and the file's name keeps its width.
- **Right**, from the inside out: a put-away alert's icon (red for an error, amber for a warning), Display, Preview,
  then the host's actions (the CAD app's Full size).
- The first glyph is always the logo's drawn mark, 16px in, on the page's gutter and the panel's 16px line (the row's
  8px, the tile's 6px and the artwork's 2px). The toggle follows edge to edge, its icon 42px in, off the panel's line.
  Why: the line is held by the mark, the one glyph on every page; an offset to bring the toggle onto it would move the
  logo.
- The panel toggle is a 28px tile with the sidebar glyph, the same neutral button open or shut (`aria-expanded` says
  which; the panel beside the model already shows it). Its tooltip, "Show panel" or "Hide panel" with ⌘\, opens to its
  right and hides while the panel peeks. Over the home it is the same tile, for the home's sidebar.
- Display and Preview are control-sized tiles (28px; 36px on a phone) 2px apart, the plain cube and the play triangle ([Icons](design-system.md#icons)):
  muted at rest, Display in the accent fill while its card is open, tooltips below (none on a phone). In Preview the
  navbar is hidden, and Preview's own bar stands in its place.
- **The app menu** is Settings, the cog in the panel's foot ([The panel's foot](#the-panels-foot)): Language, the
  host's switches (Telemetry) and Theme, then a muted footer with the version. Send feedback, GitHub and
  Discord are icons beside it, not items. In a host with no home it is the logo's, and holds those three too. Its rows
  come from the host; settings rows keep it open. A file's view settings are never here, and neither is a way to
  another page: the logo goes home, and the search is a key and a document's ⋯.
- **The ⋯ file menu**, from the document itself outwards: Copy path, Copy link; where it opens: Open in new tab (from
  an app's frame, Open in browser, left out where Open in's Browser already is it), Open in ▸ (Browser, the file
  manager, the source's apps, each export's apps, then Default app unless the host says the OS's own handler is not
  offered for the source: never for a script or a KiCad file); what is made of it: the host's items, Export ▸; last,
  after a rule, other documents and its project: Search documents with ⌘K (Ctrl+K) at the right (where the host has a
  library), then Previous in project and Next in project with `[` and `]` at the right (a folder of more than one
  document; each off at its end), or, for a document in no project, Import its folder as a project
  (the desktop's chooser opening at its folder, so the person picks the level). Each only where the host can do it. Apps
  are looked up as the menu opens; where the source was moved or deleted, what would open it is disabled and says why.
- **Moving between documents** is the navbar's and the keys', never a tab in the panel: the project's name goes to its
  page on the home, at the document's folder; `[` and `]` step through the documents of that folder, in the order its page
  lists them (passing a file no page opens), stopping at its ends; and the search (⌘K) reaches the whole project and every document the library knows
  ([Search](#search)). Why: a tab of documents pushes the model's own tree aside on every document of a project, to
  offer what a key or the search does without taking room; and the documents beside one are those of its folder, as
  a file manager's are.

#### Search

- One search of documents (`search/DocumentSearch.tsx`), over a document and over the home:
  ⌘K (Ctrl+K off a Mac) from anywhere but Preview, a text field too, or Search documents in a document's ⋯. Escape, a
  press outside or a pick closes it, and the focus goes back where it was. It never opens over another dialog.
- A card near the top of the page, about 560px wide, on the popups' surface, nothing dimmed behind it; on a phone a
  sheet the width of the view under the navbar, as the panel's is. Its input has the keyboard; under it the results; on
  a desktop a line of the keys (Move, Open, Open in new tab where the host can, Close).
- It reads the library as it opens. With nothing typed it lists the documents of the folder the document on screen is
  in (the latest documents on the home or for a standalone one); a folder's files that no page opens are its page's,
  never the search's. Typed words ask the host, once typing rests, for every file of the
  document's project, from its root, whose path holds them all, "In <project>"; then the library's other documents
  that hold them in a name or a path, "Other projects"; at most 50 rows and a line saying how many more there are.
  Why: the project on screen is searched whole, every level of it, which nothing else on screen does; other projects
  are reached through what the library knows of them, so one search never walks every project.
- A row: the document's picture (the kind's glyph until it loads, and where it has none), its name, and at its right its
  format in the project on screen ("Part" or "Assembly" for an `.xbf` file, "XBF", its format, where its parts are not
  known, as on a card), else its project's name, a dash for one in none. The document on screen's row is marked and opens
  nothing. While it reads, placeholder rows; a read that fails or finds nothing says so.
- Up and Down move, Home and End go to the ends, Enter opens the row here and ⌘Enter (Ctrl+Enter) in a new tab; typing
  always goes to the input. A click opens a row here; where the host gives a document an address the row is a real
  link (a modified click is the browser's), and the row under the pointer or the keys shows a small Open in new tab
  button at its right end.

#### Projects

- A folder becomes a project only when a person or an agent opens it as one: a folder imported on the home (the
  navbar's Import, or the "+" by Projects in the sidebar), a standalone document's Import its folder as a project, or
  `cad viewer <folder>`. Nothing else makes one: a run never does, and nothing is written to the folder. Removing one
  forgets it, and nothing on disk changes.
- **A project is its folder, linked.** Its page lists what is in the folder now, so a file another tool drops in
  appears, and one deleted in the file manager goes; nothing is recorded of a project but where its folder is. Why: the
  folder is what the person keeps their work in, and a second list of it would only fall behind.
- A document is in the nearest project above it: a file by its path as reached (a file in a linked folder inside a
  project's is that project's, as one stored there is), a model by its `.xbf`. A folder opened inside a
  project is that project (they do not nest by accident). Every other document is standalone.
- Nothing browses the disk outside a project: a document is picked up by a `cad` command or by Import.
- **A project has a page of its own on the home**, and a row in its sidebar. Why: a project is a place a person goes
  to, as a folder is; sections of one long page had to be scrolled past, and showed eight of each.
- **No document tabs in the viewer.** The browser already has tabs, so every document and every project opens in one:
  its card or row is a real link, and its ⋯ has Open in new tab ([The home](#the-home)). Why: a second strip of tabs
  inside a tab is two places to look for the same document.

#### The home

- The same navbar: the logo (which goes to Recents), the sidebar's toggle, and at the right the search and Import,
  where the host has a chooser. No ⋯, and no "Home" after the toggle: the place's title says where the person is, and
  the logo is the way home, so a name there said it twice. The search narrows the place on screen.
- **Import is the system's own chooser.** Where one chooser takes a file or a folder (a Mac's open panel), Import is
  one button that opens it, with no chevron and no menu: a folder chosen is opened as a project, a file is shown.
  Where the system has no such chooser (Windows' and Linux's take a file or a folder, never both), Import is a menu of
  File… and Folder…. The "+" by Projects is the folder chooser everywhere. Why: it is how VS Code does it, "Open…" for
  both on a Mac and "Open File…" and "Open Folder…" elsewhere; a menu in front of a chooser that takes either was a
  choice the system's own dialog already offers.
- **One place at a time** (`library/ModelLibrary.tsx`, the `.cad-library` rules): Recents (the default: every document
  opened lately, across projects), Starred, or one folder of a project. Why: each is a question a person asks ("what
  was I on?", "what is in this folder?"), and one list answers one question. A document in no project is found in
  Recents (and Starred, starred) and by the search, as in Drive's file browser, which has no place of files in no
  folder: a place of them was one more row for a question nobody asks.
- **The sidebar** lists the places (`library/LibraryPlaces.jsx`) and behaves as the viewer's panel does, because it is
  that panel over another page (`library/LibrarySidebar.jsx`, on `file-viewer/panelFrame.jsx` and `PanelSurface.jsx`):
  pinned it pushes the place, collapsed it leaves nothing, it peeks from its toggle, ⌘\ shows and hides it, its grip
  sets its width, and on a phone it is a sheet ([The panel](#the-panel)). Its rows are the panel's rows on the panel's
  16px inset, in the home's body size, not the panel's step: it is a page's navigation, as Figma's and Drive's
  sidebars are their body size. Why: one sidebar to learn, not two that look alike and differ.
  - Recents; Starred (lucide's star); "Projects", with a "+" that opens the system's folder chooser (where the host
    has a chooser; on a Mac too, where Import is one button: a "+" by Projects makes a project), over one row a
    project (its folder glyph and name, the latest activity first; one whose folder is gone muted). No
    row has a count, as Figma's and Drive's sidebars have none: a count is a number nobody acts on, and a project's
    would read every folder of it on every read of the sidebar.
  - The place on screen is marked as an open tab is (the accent fill, medium weight) and said (`aria-current`), a
    project's whichever of its folders is on screen; pressed there, it goes to the project's top. Up and Down move
    between the rows, Home and End to the first and the last.
  - Every row is always there, so the list keeps its shape: Starred with nothing starred is there too, and its page
    says how a file gets there.
  - It ends in the panel's foot, as a document's panel does: the app's links and Settings
    ([The panel's foot](#the-panels-foot)).
- **The place** fills the rest, on the page's colour, padded by the panel's inset (16px) on all four sides, at every
  width and on a phone, its blocks (the head, the folders, the cards, a line) 16px apart. Why: the
  navbar's logo, the sidebar's rows and the place then stand on one 16px line, and a box padded alike across and down
  reads as meant; the 24px gutters and 20px top it had were on no scale.
- **Its head is one row**, the control tall, as Figma's file browser heads a place:
  - **At its left**, the place's title, the page's `h1`, a step over the body at medium weight
    ([the type scale](design-system.md#the-type-scale)): "Recents", "Starred", a project's name or its path; on a
    project's page its ⋯ after it. Why: the title says where the person is, the one larger text on the page, as
    Figma's "Recents" is.
  - **At its right**, "Back to <name>" where there is one, then Sort, then grid or list, each centred vertically on
    the title (their centres within a pixel of its). Sort and the layout are there wherever the place lists anything
    (and while it is read, and over a search that finds nothing); with nothing to list (an empty folder, nothing
    starred, the welcome) they are not, as there is nothing to order or lay out. The content starts 16px under the
    row.
  - **One row at every width.** On a phone the row does not wrap: the title (or the path) is the first to give way,
    and where the controls still do not fit Sort shows its glyph alone, keeping its accessible name ("Sort by Last
    activity") and its menu.
  - **The way back is its glyph alone where its name has no room.** Where "Back to <name>" would leave the title less
    than ten heading-sized characters (measured from what is drawn, not a breakpoint: a long name goes sooner), it is the
    back arrow the navbar's Back draws, a control wide, in the same outline button, keeping its accessible name ("Back
    to <name>"), its press and Escape; on a wide screen it is its name and its Esc hint. Why: a name cut to "Bac…" reads
    as broken, a label that is whole or a glyph that says what it is does not, and Sort already gives up its name the
    same way.
  - **Sort** is one control: a ghost button, its sort glyph, the sort's name and a chevron, its menu the four orders
    with the chosen one ticked, each an order of a column the list shows: Last activity (the default: the later of
    when a page last opened the file and when it last changed, which is what a card's line says); Name; Last viewed;
    Last edited. A file with no such time comes last. No "Sort" label stands beside it: as a label flush against the
    button, the button's fill ran into it. Sort and the layout are the tab's ([Settings memory](#settings-memory)); a
    kept order that no longer exists (Kind) reads as Last activity.
- **A project's title is the folder's path**: its folder glyph, then the project's name and each folder down to the
  one on screen (`gearbox / housing / v3`), every part at the title's size, as Drive's and Dropbox's paths are: each
  part but the last a link back up to its folder, regular and muted, the slashes regular and muted, and the last the
  folder on screen, medium in the foreground; then its ⋯: Open in new tab (this folder), Copy path, Reveal (this folder), then
  Remove from CAD (the project), which says nothing on disk changed and goes to Recents. Nothing beside the name says
  where the folder is on disk: Copy path and Reveal do, as Figma's and Drive's titles say none. A path too long for
  the row gives way from its start: its earliest folders fold into one "…" crumb before the rest (`… / v3`), as few as
  make it fit, and only when even that is too long does the folder's own name truncate, so the folder on screen is the
  last to go. The "…" is a button, "Parent folders", whose menu lists the folded folders, the project first, each going
  to that folder. Why: a path cut to a bare "/" before its last folder says nothing about where it is, and a "…" that
  opens what it hides is how Drive and Finder do it; it is the way a file browser says where you are, and the one way
  back up, with no Back button of its own.
- **A document is its file, one card.** Every row is a file: a model's document is its `.xbf` (every model has one:
  `<name>.xbf` beside its script, or the path `@xbf("arm.xbf")` gives it; a shape's handed over too), and its id is
  that file's: one file, one row, one card, in Recents, Starred, a folder's page and the search, named by
  its file's name. Opening the file opens the model, live while the engine holds its build, else read from the file.
  Why: one document, one identity, one "model" type; two Assembly cards of the same thing asked the person which to
  open. An `.xbf` exported to another path, or copied, is another file, so a card of its own, and STEP, GLB and the
  other exports always are. A file that is gone is gone from every list.
- **A folder's page** (`library.folder`): its subfolders first, then every file directly in it, the documents and then
  the files the viewer does not open, nothing below them flattened in; hidden files and folders are not listed. Why: a
  folder shows its direct children, folders and files together, as Finder, Explorer, Drive and a CAD data panel do; a
  flat list of everything below lost where each file was, and a tree is a second way to see the same thing. One way to
  see a project, with no setting or switch between ways. And a project's folder holds an engineer's other files too
  (datasheets, drawings, scripts, another tool's native files): the page shows the folder as it is and hands each file
  to the app that opens it.
  - A subfolder is its glyph and its name, drawn in the family of the files beside it. Among cards it is a tile of the
    cards' own: a card's box, corners and column, a card's 12px inset round one line inside a card's border (46px tall), its name a card's
    name in size and weight, its glyph where a card's name starts; the folders are a grid of their own, 16px over the
    cards (Drive's folders over its files). In the list it is a row of the list, its glyph on the picture tile where a
    file's picture stands, its Type "Folder" and a dash for each time. It has no picture, count, star or menu: it is a way into the
    folder, a real link where the host gives places an address. Why a tile of the cards' family: a folder and a file
    on one page are read as one set, so they share a box, a column and a name's type; the sidebar's row drawn among
    cards read as a different surface, its folders a line of small labels beside large cards.
  - **A file the viewer does not open** (a PDF, a script, notes, another CAD tool's native file) comes after the
    documents. In the grid it is a compact tile of the folders' family, in a grid of its own 16px under the cards: a
    folder tile's box, column, corners, 12px inset and 46px, its kind's glyph where a folder's glyph stands, its name
    (medium, truncating), and its ⋯ at its right end, centred in a square as tall as the tile's inside, there as a
    card's actions are (under the pointer, in focus, always where nothing hovers). In the list it is a row after the
    documents' rows: the plain tile with its kind's glyph, its name, its extension as its name writes it for its Kind,
    upper case (`PDF`, `PY`, `F3D`; a dash with no extension), then when it was last viewed and last edited. A search's results are
    grouped just so: the documents' cards or rows first, then these files as the same tiles (16px under the cards) or
    rows, each group in the Sort's order; it is never a card with an empty picture. Nothing about it is dimmed:
    it is a file of the folder. Why a tile: a file the viewer cannot picture has nothing to show in a picture's space,
    so it takes a folder's compact tile and comes after the files the viewer can show. **A press opens it**, as a
    press on a document opens the document: with no page for it, in an app of the computer's, chosen from what the
    host answers for the file as it is pressed: the OS's own handler where the host offers it; else the first app the
    host lists (an editor, for code); and where it lists neither, the place's line says no app here opens it, by its
    name. An open the host refuses is said on the same line, in the host's words; while it is asked for, a spinner
    stands where its glyph is. It is a button, not a link (it has no address), worked as a document's card is: the
    same ring, Enter and Space, the same pointer. Its ⋯ is a card's menu with what applies: Open in ▸ (each app the
    host lists, then Default app where it is offered; the rows the navbar's Open in draws), Copy path and the file
    manager; with no app and no handler, those two alone. It has no star and no Open in new tab, being in no library;
    `[` and `]` and the search of documents pass it by. A host that opens no apps shows it in its file manager on a
    press, and where it can do neither the tile is no control at all.
  - **No blank cell in the list.** A cell whose value is not known reads a dash ("—", as a folder's row does for each
    time): Type, Last viewed and Last edited alike, on a document's row and on another file's.
    Why: an empty cell reads as a fault or a column still loading; a dash says there is nothing to show.
  - Sort orders the documents, and then the other files, each group in its order; the folders stand first in the
    folder's own order. Nothing narrows them by kind.
- **A project's top page leads with its recent files.** At a project's top (its own folder, not one below it), where
  files of the project below the top were opened by someone or built by a run, a block labelled "Recent" comes first,
  then the listing under "All files". It holds the library's rows of the project whose folder is below its top (the
  list Recents shows; no folder is read for it), by last activity, newest first: in the grid one row of the cards' grid,
  as many cards as fit across at the width on screen (five at 1440px beside the sidebar), the rest left out, and a
  resize changes how many; in the list at most five rows, under a header of their own, the listing's columns, drawn at the same x as All files' at every
  width (a table is never wider than the place, so a long name truncates inside its column and moves no other). A
  search replaces it with the search's results. Each label is the body's size at medium weight in the foreground, 8px over what it labels, and All files
  stands 16px under the Recent row. With no such files there is no block and no label: the page is the folder. Why: in
  a project the files worked on are rarely in its top folder, and Google Drive, Dropbox, Box, Figma, Fusion and
  Onshape put recent or suggested files at the home or the root (Drive's Suggested row on its Home, Box's Recents on
  All Files), not on every folder's page; so a project's top, its root, leads with them, and a folder below it is that
  folder alone.
  - The folder is read as it is shown and again every two seconds while it is up, so a file written meanwhile joins
    it. Where the host listed only part of a very large folder, a line under its last row says so.
- **Its documents**, all of them, with no Show more: a folder lists at most what the host answers of it, and Recents a
  couple of hundred. Cards in columns at least 200px wide, 16px apart across and down, or rows.
  - **A card** is one box on the card's colour with a card's 10px corners: the picture edge to edge with its format's
    chip 8px in from its corner, then the caption on a card's 12px inset, the name (medium, a card's title) over one
    muted line in the small step. Why 200: the panel's narrowest width, a measure the page already has, on the 8px grid; it
    puts four or five across beside the sidebar on a laptop's page, a card about 200 to 250px wide, and one on a phone.
    232 made cards near 290px wide on a laptop, larger than a file's picture needs.
  - **A document's picture is 3:2 wherever it is drawn** (a card's, a row's, the search's), on the light viewport's
    gradient in both themes, and taken at 3:2 (480 × 320), so a card shows it whole; one taken earlier at 4:3 is fitted whole in the box. Why: one picture, one shape; a card's, a row's and the search's had three.
  - **A row** is the search's: the control + 16 tall (44px; a phone's 52), its picture the control + 4 tall, then its
    name and its facts in one size, the name in the foreground and the facts muted, under a header of muted labels the
    control tall with no rule under it. Its fill hangs 8px past the place's line, so the header's labels and the pictures,
    a folder's tile among them, stand on the line; its star and ⋯ float over its right end. A narrower place drops Type
    (under 560px), then Last viewed (440). Why that tall: a row with a picture is as tall as its
    picture needs, the same in the search; a list's emphasis is colour, never a second size.
  - An `.xbf` file is badged "Part" when its document holds one part and
  "Assembly" when it holds more (the row's `parts`: its parts' occurrences, as `cad inspect` counts them and the
  Model tree shows them), and "XBF", its format, where the host does not know for the file as it now is: never a
  guess, and never a read to find out. Why: desktop CAD names its own documents that way, a part or an assembly, and
  a person reads a card the same way; an xbf is the engine's own document saved as a file, the same thing a model's
  page shows, so it is named as a model is. STEP, STL, 3MF, GLB and the rest are other formats and keep their format's
  name, whatever they hold. Only the label: an xbf is still a file (its menu, its size and path, what Star does).
  - **A card's picture is the one its row names**, the one taken when a page last showed that file as it now is; a
    file with none shows its kind's glyph on the plain tile. The home draws no picture of its own. Why: a picture drawn out of sight
    reads a file nobody opened, on a timer, and a folder of a thousand files is a thousand reads.
  - A card's line is its last activity alone ("Edited now", "Viewed 7h ago"), as Figma's cards say "Edited 2 hours
    ago". A card has no glyph, place or size. Why: the picture and its badge say what it is. The list shows what a
    card shows, as columns to read down, and nothing more: **Name** (its picture or glyph, and its name), **Type** (the
    card's badge: "Part", "Assembly", "STEP", "KiCad PCB", a file's extension; a folder's row says "Folder"), **Last
    viewed** (when a page last opened the file, the age the card's "Viewed …" says, with no verb) and **Last edited**
    (the file's modified time, the card's "Edited …"), then the star and ⋯. The same four columns in a folder's page,
    a project's top Recent, Recents, Starred and a search. A value that is not known is a dash.
  - Each has a star and a ⋯ (Open, Open in new tab, Open in ▸, Copy path, Copy link, Reveal, then Star or Unstar),
    shown on hover or focus and always on touch; a starred document keeps its star, filled in the foreground. The star
    says "Star" or "Unstar" in its hint and its name. Open in is the navbar's: the apps the host lists for the
    document's files and Default app, looked up as the menu opens, and there only where it lists one. Nothing on the
    home deletes a file or forgets one: there is no Delete and no Remove from Recents. Why: a document is its file,
    and removing a file is the person's own act, in their file manager; the list of what was opened needs no pruning
    by hand, and the item was one more line in every card's menu for a chore nobody asked for. A starred document is not
    listed first: Starred is its own place. Starred is Figma's, Drive's and Dropbox's word; the library, its rows, the
    host's actions and the place's address keep the word they shipped with, `pinned`.
- **Links.** Where the host gives a target an address (the web page), a card's or a row's main press and every row of
  the sidebar is a real link: a plain click shows it in this view, and ⌘ or Ctrl and a click, a middle click and the
  browser's own link menu open it in a new tab. Where the host can open a target beside the view, every document's ⋯
  has Open in new tab directly after Open, and a project's ⋯ has it first; in an app's frame (the CAD app) the words
  are Open in browser, on a document's ⋯ alone. A project's file no page has opened yet is a link as the rest are, and
  so is each folder of a project and each part of its path: a folder's address is the project's and its path below
  the project's root.
- **Coming from a document.** The navbar's project name, pressed over a document, shows that project's page at the
  folder the document is in, with the document remembered: its card or row ringed in the brand's colour and brought
  into view, and "Back to <name>", with an Esc hint, at the title row's right end. Escape returns to the document while no menu,
  dialog or field has the keyboard. It lasts until another document is opened or the person goes to another place.
  From the sidebar a project opens at its top. Why: the document's folder is where the documents beside it are, and
  the way back should cost nothing. "Back to <name>" is the scale's outline button, as tall as the row's other
  controls, its arrow alone where its name has no room ([the head](#the-home)): never a name cut short.
- **Search** narrows the place on screen. Recents and Starred narrow the rows in hand. A folder's page asks
  the host, once typing rests, for every file anywhere below the folder on screen whose path below it holds every
  word, and lists them flat, with no folders. Why: a search is the one place
  a person wants every level at once, and it is the one place they are flattened.
- **After a folder is imported** (Import's Folder, a folder in its one chooser, or the "+") the home goes to that
  project's page, at the folder chosen where it is inside the project, with a line saying what came of it (made,
  already a project, or inside another). A file imported is shown, as a document is opened. **After Remove from CAD**
  it goes to Recents and says so.
- **Every state stands where its content will**: placeholder cards or rows while the list is read, placeholder rows
  where the projects will be; "No projects yet." under Projects; one muted line, where the place's first row would
  stand, in a place with nothing to list (an empty folder, nothing starred, a project whose folder is gone, one no
  longer in CAD, a folder that could not be read: the path above it still leads back up), and under a folder's last
  file when the host listed only part of it. What came of a folder imported or a Remove from CAD, and an action that
  failed, are a line there too, the failure in the destructive colour: no box, no tint. With nothing at all yet,
  Recents shows the C mark (two controls tall, with no stage under it: it is a mark, not a picture), "Nothing here
  yet" in the body's size at medium weight (the title's size is the page's title's alone), one muted line, the ways
  in (Import, one button, where the system's chooser takes either; else Import file and Import folder), and the
  formats the viewer opens, muted, 16px apart in a column centred in the place.
- **On a phone and in a narrow home** nothing of the place's own changes: the same 16px inset, one card across on a
  phone, as many as fit elsewhere; Import is its icon in a navbar under 480px. The sidebar is collapsed there until the
  person opens it (the panel's rule, from 872px down), and a phone's is the sheet. The width is the home's, never the
  window's.

### The panel

One panel at the page's left, the same over a document and over the home. Over a document it holds the file's structure
and settings (`FlatPanel.jsx`); over the home, the places ([The home](#the-home)); and both end in the same foot
([The panel's foot](#the-panels-foot)). How it shares the page
is one frame for both (`file-viewer/panelFrame.jsx`, `PanelSurface.jsx`, `panelToggles.js`, `panelPeek.js`), so every
rule below holds on both pages; "the view" is the page it stands beside, "the model" the picture or the place.

- One panel, docked at the view's left at its full height, on `bg-sidebar` with a rule on its right (`FlatPanel.jsx`,
  `PanelSurface.jsx`, `sidebars.js`).
- **Pinned, it pushes.** The picture is drawn in the room it leaves, the model centred there; it never overlays the
  model, at any width. Showing or hiding it is a plain resize, so a fitted view refits.
- **Collapsed, it leaves nothing** over the model: no rail, no hot edge. A pick never opens it.
- **The peek.** A mouse or pen resting 250ms on the toggle (`PANEL_PEEK_DELAY_MS`) shows the collapsed panel as a card
  over the view, 4px in from the window's left, the navbar and the view's bottom, its contents where a pinned panel's
  stand. It slides in over 100ms and out over 80ms, pushes nothing, and works from the page's first frame. It goes
  150ms after the pointer has left both toggle and card (`PANEL_PEEK_LEAVE_MS`; not while a menu opened from it is up), on Escape, or on a
  press on the model (on the home, on the place). Only a click on the toggle or ⌘\ pins it; nothing done inside it
  does (a place chosen in the home's is shown under it), and a peek is never kept.
  There is no peek for a finger, a held button or keyboard focus. Why: a glance at the tree should not resize the
  picture or move the camera.
- **Width.** 232px at first (`DEFAULT_PANEL_WIDTH`), 200 to 480 by its grip, the same at every desktop width. Why 232:
  the least width on the 8px grid where any three tabs fit beside the search icon, so the panel takes no more of the
  model than three tabs need.
- **It opens by itself only until the person chooses.** Until they open or close it on a file, the view decides: open
  where the view is at least 872px wide (`MIN_MODEL_WIDTH`, 640, plus 232), collapsed below, following resizes. Once
  they open, close or pin it on that file, their choice holds at any width. A peek is no choice.
- Its open state, width and tab are kept per file for the session, never globally ([Settings memory](#settings-memory)).
  Why: everything else about a file is kept per file, and forgotten with the tab. The home's open state and width are
  kept the same way, the home in the file's place: with the tab's settings, where its layout and Sort are.
- **From the first frame** the toggle and the name are in the navbar and the panel is open or shut as it will be, its
  tab showing placeholder rows. Neither arrives late and pushes the model aside. The home's is there with its places
  from its first frame too.
- Every tab stays mounted, so a tree keeps its folds, and each keeps its own scroll. The first tab opens by default.
- **Rows** are the control's height on the panel's 16px inset in every tab: a tree's rows ([Trees](#trees)), and the
  settings rows (`panelRows.jsx`), each a muted label on the left line and its control ending on the right one, a
  dropdown half the row wide ([Spacing and the panel inset](design-system.md#spacing-and-the-panel-inset)).

#### The panel's foot

- **One row at the panel's bottom, the same on the home and over a document** (`file-viewer/PanelFoot.jsx`, one
  component), in the pinned panel, the peek and the phone's sheet alike. A hairline rule, the panel's full width,
  parts it from what is above; under the rule, 8px, the row of control-sized icon tiles, 8px. It is pinned: the
  panel's content scrolls above it.
- **At its left, the app's links**, each an icon with its name in a hint above it: GitHub and Discord (each only
  where the host gives that link), then Send feedback (the round chat bubble: a new issue on the host's tracker).
  A press opens the link the host's way. Muted at rest, the foreground under the pointer.
- **At its right corner, Settings**, a cog, which opens the app menu upward: Language, the host's switches
  (Telemetry), Theme, and the version. The cog is lit while its menu is open.
- **On the panel's lines**: the first icon and the cog's stand on the two insets, as the head's icons do. At the
  panel's narrowest (200px) the row fits; links that would not fit wrap upward, and the cog keeps its corner.
- **A tab's own actions row** (Params' Reset and Save) stays in the scroller, directly over the foot's rule, flush
  against it wherever the tab is scrolled ([A tab's actions](design-system.md#a-tabs-actions)).
- **Only where the host has a home.** There the logo is the way home, so the links and Settings need a place of their
  own. A host with no home keeps them in the logo's menu and its panel has no foot; a document whose view has no
  panel has none either, and the home is one press away.
- Why here, and why in a document's panel, which otherwise holds only the file: the app's own links and settings have
  one place, the bottom of the sidebar, the same on the home and over a document, so a person finds them without
  leaving the document, and a logo that opens a menu is not also the way home.

#### The head and its tabs

- One head row, on a desktop and a phone alike, the control plus 4 tall ([its measures](design-system.md#spacing-and-the-panel-inset)).
  Tabs are pills at its left, each as wide as its name, so choosing one moves nothing; ←/→ move between them.
- **Budget three tabs.** A file seldom has four at once. Tabs that do not fit go, in order and with their icons, into a
  ⋯ at the row's right end, just left of the search icon (there only where a tab can be searched); the open tab always
  shows. Fit is measured, never a breakpoint.
- **One tab is a plain title**, not a pill, with no rule under it and no gap kept for one: with one tab there is
  nothing to separate. Tabs have a full-width rule under their row, level with the strip's bottom edge. A file whose
  tabs arrive after it has loaded (a STEP's Params or Joints) gains the rule once.
- **Search replaces the head row.** Pressed (or "/"), the row becomes the search box at the same height and place: no
  tabs, title or ⋯ while it is open. It keeps the head's rule (none over a lone title), so nothing below moves. Why:
  there is no point in tabs while searching, and a second row would push the list down. What it finds: [Trees](#trees).
- A tab with something to reset (Params, Joints, Animation) carries the changed dot on its name while its Reset is
  enabled, and on the ⋯ while the tab is hidden there. Its actions stay in a sticky row at the panel's bottom, its one
  Reset (and Params' Save) at the right ([A tab's actions](design-system.md#a-tabs-actions)).

### The tool strip and the corner

**The strip** (`FloatingToolBar.js`):

- It floats at the top centre of the whole view, 8px down and at least 8px from the sides. No panel moves it; where
  they meet, it stands over the panel. Why: a strip that slid with each panel moved under the pointer.
- It holds the file's own tools in one order: Select, Draw, Measure, then Explode and Clip
  ([What each file shows](#what-each-file-shows)). One row, no rules; on a desktop it wraps before it would overflow.
- A tool the file cannot use is left out, never drawn disabled: a greyed tile says "not now" where the file will never
  offer it. Explode appears once the loaded model reports parts to separate.
- It holds tools only: Display and Preview are the navbar's, always.
- There is no strip with nothing to hold, while the file first loads, after it failed, in a compact view or in Preview.
- The row of the tool in hand hangs 8px under the strip, centred, while the tool is in hand (Draw's tools, Measure's
  measurements, Explode's or Clip's slider), one width from tool to tool so the column holds still.
- The update line stands centred under them ([Loading and status screens](#loading-and-status-screens)). A renderer's
  own panels may hang in a column below (`ToolStack.jsx`, stopping above Quick Edit); no file type uses it today.

**The corner** (`ViewCorner.jsx`, `viewportLayout.js`) holds only the camera's own navigation:

- A 3D view: the orientation cube alone, in a 6rem box 2px from the right edge, its top level with the strip's. A click
  on a face, edge or corner turns the view there; a drag across it orbits.
- A flat view (a drawing, a schematic, a board in 2D or 3D): one zoom control, "100%" and a small chevron, 28px tall,
  centred on the strip's middle line, 12px in. Its menu: Zoom in, Zoom out, Zoom to 100%, then Zoom to fit and Zoom to
  selection (off with nothing picked), each with its key. On a board in 3D it zooms the 3D camera.
- Nothing else, ever: no +/−, no Home, no Display, no tool. And nothing at all on a phone (a pinch zooms; a long press
  opens the view's menu, with its framing), in Preview, while the file loads or after it failed, or in a compact view.
- A host whose own control floats over that corner may lower it, or anchor it at the top left, where the cube or the
  zoom stand mirrored ([viewer-host.md](viewer-host.md)).

### The Display card

- **The button.** Display is one navbar button for every file type, just left of Preview: the plain cube, a toggle
  (pressed while the card is open), no chevron, tooltip "Display". Why: one place and one icon for how the picture is
  drawn, beside Preview, keeping the picture itself clear.
- **The card** (`DisplaySettings.jsx`, on `SettingsCard.jsx`) is titled "Display". It docks 4px under the navbar and
  4px from the view's right edge and slides in from the right as the peek does from the left. It is at least 288px
  wide on a desktop, so every dropdown is half its row, and 320px on a phone, and grows to fit a value rather than cut it off
  ([The settings cards](design-system.md#the-settings-cards)).
- **Rows**: no section headings, one hairline between the camera's rows and the picture's.

  | File | The camera's rows | The picture's rows |
  |---|---|---|
  | 3D: STEP, .xbf, GLB, STL, 3MF, robot | Projection | Style, Background, Show grid |
  | KiCad board | Side, Mode, Projection (in 3D) | Style, Background |
  | Drawing (DXF), schematic | none | Background, with no hairline and no Reset |

- Projection, the row changed most, leads a 3D file's card: Orthographic first (the default), then Perspective.
- A 3D file's Style: Solid (the default: shaded, with CAD edges), Shaded, Parts, X-ray, Hidden line, Wireframe, each
  where the file can draw it. A STEP assembly has all six, a STEP part all but Parts, and a file without CAD edges
  (STL, 3MF, GLB, robot) Solid, plus Parts where it has several. Render is Preview's, never a Style.
- A board's Style: Board, Copper, Assembly, Placement (KiCad's presets), and a disabled "Custom" while the Layers tab's
  eyes have left the preset; choosing a preset goes back to it. Mode is the words "2D" and "3D" alone, with no icon
  ([Icons](design-system.md#icons)). Show grid is off by default; Background is Light or Dark.
- **Reset**, at the bottom right, puts the file's settings back to what a file opened for the first time gets (3D:
  Orthographic, Solid, no grid; a board: Top, 2D, Board, Orthographic). It never touches the Background, the person's
  own and the same in every file of the tab. It is off while nothing differs.
- **No camera reset row.** The camera comes back by Zoom to fit (F, a double-click on empty space, the view's menu,
  the zoom menu) and by the cube. Why: a second reset beside Reset would read as the same thing.
- **Behaviour.** A change applies at once (a costly one is prepared behind the frame on screen, `viewUpdatePlan.js`).
  The card stays open while the person works. Its button, its X, Escape (focus back to the button), another file and
  Preview close it; on a phone, so does a press outside the card and its button. It is never kept open across a reload.

### Quick Edit

The bar where a person writes a note to their agent about what is on screen (`QuickEdit.jsx`).

- **Always there**, with no X and no setting, wherever a note can carry the view's picks or ink: STEP, .xbf, GLB, STL,
  3MF, a robot, a drawing, and a board or schematic once indexed. It is hidden (its note kept) while the file loads and
  in Preview, and absent in a compact view. Why: a bar that came and went was not there when wanted.
- **One row at rest**: the note ("Describe a change…") with its buttons at the right of its last line. A row of
  attachments appears above it only while something is attached; the bar grows upward, its bottom and note in place.
  One solid surface, the strip's, at rest and in use: no dimmed rest state.
- **Placement**: 16px off the bottom, centred on the whole view, at most 400px wide (else the view less 16px a side).
  Where a pinned panel would reach under it, it centres on the model's area; a peek moves nothing. On a phone it spans
  the view less 8px a side, above the safe area. The bottom of the view is Quick Edit's alone.
- **The note** grows upward as it is written (never on focus) to four lines, then scrolls, its scrollbar at the bar's
  inner right edge; its border turns brand blue while focused. Why four: the bar always stands over the model. A
  reference line pasted into it becomes a pill, which Backspace takes whole.
- **Buttons**: square icon buttons, only those the host can carry out: Copy Prompt (copy) always, Queue (list-plus)
  where the host has a composer, Send (an up arrow) where it can post now. The rightmost is primary; Enter presses it,
  Shift+Enter is a new line. Why icons: words took a third of the row and put the note's scrollbar mid-bar.
- Copy shows a tick for about 1.6s and keeps everything. Queue and Send clear the note, the selection and the ink once
  the note has gone. A failure keeps the note and says why under it.
- **Chips** ([Chips](design-system.md#chips)): all the geometry picked is ONE chip, a single pick by its name and
  several by their count ("5 refs"); the Annotation chip (the pen) stands apart. One row, then "+N more". A press on
  the refs chip (or a short mouse rest) opens its list: each pick's name, kind, X and key facts; a press on a name
  copies it. Why one chip: a chip per kind crowded the note and said no more than a count.
- **The keyboard**: on a desktop the note takes it after the person's own pick in the view (within 1.5s of their
  press) or their first ink stroke; never for an agent's selection, and never on a phone, where it would raise the
  keyboard. Until the person writes in the note or presses in it, `[` and `]` there are still the view's (the folder's
  previous and next document); after that, a bracket is typed. Why: a pick lends the keyboard, and the person who has
  not taken it up is still moving through the folder. Escape in a written note gives the focus back to the view; in an
  empty note it also does the viewer's.
- **What goes**: the note, the file's path, the references one a line, and a snapshot of the view and any views with
  ink, made only when Copy, Queue or Send is pressed. Params' saved values add a line ([Parameters](#parameters)).

### A phone

- **One breakpoint.** A phone is a viewer narrower than 600px (`VIEWER_MOBILE_BREAKPOINT`), measured on the viewer and
  never the window, so a narrow desktop window works as a phone. Its sizes are the phone scale
  ([Two scales](design-system.md#two-scales)); what changes in the layout is below.
- **The page is pinned** (`fixed inset-0`) and never scrolls.
- **The navbar** is 48px, with no Back or Forward (no room), and the project's name a folder tile. Display and Preview
  stay in it, without tooltips.
- **The panel is a sheet** from the left, under the navbar and over the strip, the model and Quick Edit: 85% of the
  width, at most 20rem, with no scrim. It slides in over 100ms and out over 80ms, starts closed, is never kept open,
  and has no grip and no peek. Inside are the same tabs, search and rows, with row actions always shown, and the
  panel's foot at its bottom. The home's sidebar is the same sheet, with its places; a place chosen in it closes it.
  - It closes on a tap outside it (a tap on the picture only closes it), a swipe left of at least 48px, Escape, the
    toggle or ⌘\. A tap on Display, Preview or the file's name closes it and does that control's job in the same tap.
  - A press on a row of a board's or schematic's tree closes it and frames what was chosen.
  - The focus goes into it as it opens and back to the toggle as it closes.
- **The strip** is one row of 36px tiles that never wraps. Tools that do not fit go, from the end, into More (an
  ellipsis, last, there only while a tool does not fit), where a tool is a row ticked while it is in hand. A slider row
  is 20rem, and Draw's row wraps.
- **There is no corner.** A pinch zooms, and a long press opens the view's menu, with Zoom to fit and Zoom to selection.
- **The Display card** is at least 320px wide (less on a narrower screen), and a tap outside closes it.
- **Quick Edit** spans the view less 8px a side, above the safe area, and never takes the keyboard by itself.
- **Menus** open and close at a finger's tap; a submenu opens in place ([Menus](design-system.md#menus)). No hint opens.
- **The search** is a sheet the width of the view under the navbar, with no line of keys.
- **Preview**: a tap shows its bar for 2s. What a tap, a double tap and a long press do on the picture is in
  [Selection and gestures](#selection-and-gestures).

## What each file shows

| File | Panel tabs | Strip | Display card | Corner | Preview |
|---|---|---|---|---|---|
| STEP, .xbf | Model; Params (where it declares parameters); Joints (movable joints, its motion on top) or Motion (motions without joints) | Select ⌄, Draw, Measure ⌄, Explode (an assembly), Clip | Projection │ Style (six for an assembly, five for a part), Background, Show grid | Cube | Yes |
| GLB | Model (its nodes); Animation (where it has animations) | Select, Draw, Measure, Explode (two or more rigid parts), Clip | Projection │ Style (Solid; Parts where it has several), Background, Show grid | Cube | Yes |
| STL | Model (its bodies) | Select, Draw, Clip | As a GLB | Cube | Yes |
| 3MF | Model (its objects) | Select, Draw, Measure, Clip | As a GLB | Cube | Yes |
| URDF, SRDF | Links; Joints (drivable joints) | Select ⌄ (while it can be posed), Draw, Measure, Clip | As a GLB | Cube | Yes |
| KiCad board | Parts, Nets, Layers | Select ⌄, Draw, Measure | Side, Mode, Projection in 3D │ Style, Background | Zoom, in 2D and 3D | Yes |
| KiCad schematic | Parts, Nets; Hierarchy (more than one sheet) | Select ⌄, Draw, Measure | Background | Zoom | No |
| DXF | Layers | Select, Draw, Measure | Background | Zoom | No |

- ⌄ marks a tool with a menu ([Select's menu](#selects-menu)); │ is the card's hairline. A STEP opens as an engine
  document, the same view as an .xbf ([cad-renderer.md](cad-renderer.md#engine-document-renderer)).
- An STL has no Measure: it carries no unit to measure in. Its bodies are its runs of triangles that share corners,
  largest first, found after the model is on screen (a file of more than 2,000 is not split).
- A tree always shows, even with one row (a STEP part, a 3MF of one object); a GLB with no node shows one row named
  after the file.

### A board in 3D

- **It is the same view.** Display's Mode (or the key 3) draws the board in 3D, as KiCad's Alt+3 opens its 3D viewer.
  The strip, the panel, Quick Edit, the selection, ink, measurements and the corner's zoom all stay, and the zoom then
  zooms the 3D camera (`Board3dView.jsx`; 2D loads no 3D code). There is no cube and no Home: Projection is the
  Display card's row (Orthographic by default), and Zoom to fit is the way back.
- **What it draws**: a slab cut to the board's outline, with the 2D pictures as its faces. KiCad's stack-up colours
  show only in the Board style; Copper, Assembly, Placement and a focused layer keep the layer colours, as 2D always
  does. Parts are the footprints' STEP models in their own colours; a missing model is a see-through 1mm block.
- **Working in it**: a pick lands on the face the ray meets, under the same filter; a drag orbits (box select is
  2D's); Measure works on the board's plane; ink sits on the face and is shared by both modes. The hover tip, the menu
  and the double-click are the same.
- **Side** (or ⇧F) turns the camera over the board's left-right axis, eased, never through the board.
- **Entering** starts head-on at the 2D window, the 2D picture held until 3D has drawn the same picture, then eases to
  the opening tilt (or the last 3D camera) on the same side. **Leaving** restores 2D's own window. Each mode keeps its
  own last view; only the side carries over. The home's picture of a board is the flat board. Its Preview:
  [Camera, animation and Preview](#camera-animation-and-preview).
- **A shared board is 2D alone**: the card has no Mode, 3 does nothing, and there is no Preview and no 3D models row;
  a view left in 3D opens in 2D. Why: a share shows a board in 2D, and its 3D is a GLB of its own, shared as a file of
  its own.

## The panel's tabs

The structure tabs come first, then what the file declares (Params, Joints, Animation), each where the file has it,
under every tool. Rows, settings rows and sliders are the design system's ([Rows](design-system.md#rows),
[The slider control](design-system.md#the-slider-control)); a tab's groups are parted by one hairline, never a box.

### Trees

Model, Links, Parts, Nets, a board's Layers, Hierarchy and a drawing's Layers are trees: dense rows, a long list
mounting its rows as they scroll into view (`VirtualRows`).

- **A row press** selects as a click on the picture does (taking Select up first), without moving the view. Shift,
  Ctrl or Cmd adds. A double-click on an assembly's row isolates it; on a board's or schematic's row it frames it.
- **Row actions** float at the row's right end on hover or focus (always on touch): Isolate, then the eye, on an
  assembly's rows (in a part file, the eye alone); the eye on part, net, layer and link rows. An isolated row keeps an
  X, "Exit isolate". A row's menu (a right click, a long press) is the picture's menu for that item.
- **A link's eye** hides the link's own visuals, never its child links. A partly hidden link counts as shown, so its
  eye hides the rest; a row that draws nothing has no eye.
- **A pick in the picture shows its row** once, opening what it must. The selected row is lit, and a row that holds
  the pick is tinted. On a board at most one block is opened by the latest pick, shut again when the next pick goes
  elsewhere; blocks the person opened or shut stay theirs. Why: the list stays the shape the person left it.
- While parts are hidden, a line over the Model rows says "3 hidden · Show all". Select's filter shapes the tree: Parts
  alone opens assemblies and shuts parts, Faces or Edges open assemblies, Parts with either keeps the person's folds.
- **A board's Parts** are grouped by the schematic block each footprint records (else by kind: ICs, Resistors…), and
  end with a shut "No 3D model" group that says why for each part. Its **Nets** are flat, with pad and pin counts, and
  unconnected pins in a shut group of their own, as Altium's PCB panel lists them. A block's name opens or shuts it and
  selects nothing; its menu has "Select all N parts" and "Zoom to" it.
- **A schematic's Hierarchy** (KiCad's Hierarchy Navigator) lists the root and its sheets in page order. The sheet on
  screen is lit, and a press shows that sheet.

**Search** covers the trees only, never Params, Joints or Animation.

- An empty box changes only the head. A query shows results only. A file with one tree shows that tree's hits,
  whatever tab was open; a file with several (a board, a schematic) shows one list, a group per tab with hits, in tab
  order, each under its tab's name and count.
- Hits act as their tab's rows; the arrow keys walk across the groups, and Enter picks. Most tabs list hits flat. A
  drawing's Layers keep them under their layer, and folds made while searching go when the search closes. A board's
  Parts search finds pads and pins too (`#U3.9` finds a pad).
- Escape or the X brings back the tab as it was, with its scroll and folds. Search never changes the open tab.

### Parameters

The engine document's Params tab (`XbfParametersSection.jsx`), after Model and before Joints, on a phone too, wherever
the document declares parameters. It is the one control in the viewer that changes a design, and only through the
engine; everything else in the viewer only looks.

- **Edits are drafts until Save.** While a draft differs, the view shows the model built at the drafts; nothing is
  written until Save.
- **Rows**: a parameter with a range is the slider control, filled from the left end; any other is its name and a
  number field ([Number fields](design-system.md#number-fields)). Values carry their unit. Integers step by one, floats
  by their declared step, else by a power of ten giving 100 to 1,000 steps. Parameters from other files follow the
  model's own, each file under a muted heading.
- **The foot** is the tab's actions row: a status right-aligned above Reset (it drops the drafts) and Save (filled only
  while it can save; it sends the changed values in one request). Both are off while nothing differs.
- **The status** says why the buttons are off, or "Saved" once a save is answered, else nothing; never a count of
  unsaved values. Why: why the buttons are off is read where they are.
  - "Edit these in the script." (an .xbf opened as a file, and any document shown from a view bundle, which has no
    engine to build it: [viewer-host.md](viewer-host.md#a-view-bundles-host)), "Run the script again to edit." (the script's process has
    gone), "Script changed. Run it again." (the file was edited by hand since it ran).
  - Any other reason Save is off is its hint: one short line, never the engine's message, which can run to many lines.
  - A parameter that cannot be written is off and says why ("Set in lib/spec.py.", "Calculated in the code.").
- **The preview** follows the slider on a fast model (one that answers within 250ms). A slower one is built only at the
  value the slider comes to: released, stepped by a key, typed, or still for 300ms. Each answer draws in place, the
  camera kept and the update line silent; controls never lock or snap back. Why: a build cannot be stopped, so none is
  spent on a value already passed.
- **Saving** turns the controls off and Save says "Saving…". The rebuilt model arrives as a new version.
- **The agent learns of a save**: the next Quick Edit message says once what was saved, so the agent keeps the values.
  Unsaved drafts add a line to every message saying they are shown, not saved. How the tab works:
  [cad-renderer.md](cad-renderer.md#engine-document-panels).

### Joints

A STEP with movable joints, and a robot with joints it can drive, have a Joints tab, under every tool.

- **A mechanism's one tab.** Where the model also has motions, the Joints tab holds both: the motion's rows on top
  (the [Animation](#animation) tab's rows), one hairline (no heading), then the joints. There is no Motion tab beside
  it. Why: the motions drive the joints the sliders set, so two tabs split one subject in two.
- **The Position row** leads the joints: "Position", a dropdown of Default, the named poses, and "Custom" while the
  joints are set by hand.
- **Each joint is the slider control**: its name and value ("90.0°", or mm for a slide). The fill runs from the rest
  position to the value, with a tick at rest. Why: a joint's zero is mostly mid-range, so a fill from the left end
  would mean nothing.
- **One Reset**, at the bottom right, puts the motion back at its start and the joints at their default. It is on
  while either is off.
- The knobs in the picture belong to Select while its filter ticks Position. None show while the model is exploded or
  a routine plays, and using a joint turns Explode off.
- The pose holds across tools, and across model updates with the same joints. Default restores the authored values
  (an SRDF's home among them) and stops the motion.

### Animation

A GLB with animations, or an engine document's motions without joints (the tab is then "Motion"), has this tab, last.

- Its rows: the routine (a dropdown, "Animation", or "Sequence" for a motion), where a choice plays from its start;
  the transport, a Play/Pause tile and a scrubber filling the row, with no time readout; Speed ("1×"); and Loop, a
  switch.
- **Reset**, at the bottom right, puts the routine back at its start and the model at rest. The transport has no Reset
  of its own. Why: one Reset per tab, always in the same place.
- A routine opens at rest, and nothing plays it but the person. Leaving the tab or closing the panel leaves it playing.
- In the tools view routines play only from here; Preview has its own playbar.
- Speed and Loop are kept with the file and never light the tab's dot.

### Layers

**A board's Layers** (`board/LayersSection.jsx`):

- Grouped Front, Inner, Back and Other, under muted headings. Each row has a colour swatch, the name, a count and the
  eye. A press makes a layer active: a 6px dot after its name, the layer drawn on top.
- Last in Other, "3D models" (a count of the parts that have one, and its eye) shows or hides the parts in 3D.
- **Layer display**, under one hairline and its heading: Others (Shown, Dimmed or Hidden; ⌘H cycles it), Pours (a
  switch, only while copper is drawn), and the Zones (60%) and Tracks (100%) opacities. Why: they are changed now and
  then, so they are the panel's, as in KiCad's Appearance panel; how the board is drawn as a whole (Side, Mode,
  Style) is Display's.

**A drawing's Layers** (`dxf/LayersSection.jsx`) are in the drawing's order, each row with its pen colour, name, entity
count and eye (a hidden layer is not drawn, picked or snapped to). Block references open under their layer, named by
their handle ("#9C").

## Loading and status screens

**Opening a file** shows one indicator, `LoadingStep`, the same in every phase and every view:

- A step line ("Reading model", its count at the right) over a thin bar (its share, or a sliding segment where the
  share is unknown), 240px wide and centred in the view's area. No mark, no spinner, no headline. The steps are a
  closed vocabulary ("Finding file", "Reading model"…), never the engine's own words.
- It stands on the viewer's Background, in that scheme's ink; Preview's cover stands on Preview's backdrop. Why: a
  page never flashes from one background to the other.
- The navbar, the toggle and the name are there from the first frame, and the panel stands open or shut as it will
  be. A tree with no rows yet shows six placeholder rows on the rows' own lines, fading downward and pulsing gently.
  Why: the navbar names the file and the panel shows it is loading, so the indicator needs no more, and nothing moves
  at the hand-over. The strip, the corner, Quick Edit and the Display button arrive with the model.
- A lost connection adds "Waiting for a response. Retrying…", and a step's detail shows after 10s, both hanging under
  the bar so the step line never moves.

**Updating a file on screen** never brings back the loading screen. The rebuilt model loads behind the picture, and
the old one stays until it is ready; the camera stays put. One update line says so, centred under the strip (at the
top centre where there is none): after 150ms, a small spinner and words on a pill in the picture's scheme ("Updating
model…"), or "Couldn't update view" with Retry. It never blocks anything. On a phone it is an icon with a popover.

**The alert card** says what went wrong, over the view: Retry (which reloads the file), Report Issue where the host has
a tracker, and Details with a copy button. A card the model survives (a failed update, a warning) has an X; it then
stays away while that alert stands, and its icon, first of the navbar's right-hand controls, brings it back.

**Status screens** (`EmptyState.jsx`) cover every state with nothing to show: a file that is not there, one that will
not open, CAD not running, a replaced link, a server that does not answer.

- One quiet column, 22rem wide, centred and left-aligned: the title, the explanation 4px under it in muted text, then
  one small outline button 12px under that (`StatusAction`). No icon, no tinted tile, no colour for the tone, in the
  app's theme. Why: the words say how serious it is, and a page state has no picture to take a Background from.
- A file that will not open shows under the navbar ("File does not exist" with its path, "Could not open that file"
  with the reason), with Go home where the host has a home. "CAD is not running" covers the whole page, and the page
  under it is inert, so no tools or panel show.

## Selection and gestures

- **A click selects; Shift adds** (in a tree, Shift, Ctrl or Cmd). A click on empty space clears. On a STEP the picks
  reach faces and edges as well as parts, as the filter allows ([Select's menu](#selects-menu)).
- From front to back, a press takes a measurement, then ink, then the model. The selection stays lit, and in Quick
  Edit's chip, under every tool. The hover tip names what a press would pick
  ([Tooltips and feedback](#tooltips-and-feedback)).
- **A double-click never takes the selection away**, on a flat view as on a 3D one. A click that would let something
  go (the selected thing pressed again, or taken out with Shift or a finger) waits the double-click window: 220ms for a
  mouse (`DOUBLE_CLICK_WAIT_MS`), 300ms for a finger. A double-click drops it; a click on something else lets it act
  first. A press on empty space clears at once, since what a double-click there does needs no selection. The same in
  every view, 2D and 3D, a board in 3D included.
- **A double-click** under Select (under Draw or Measure it is the tool's):
  - On a STEP or .xbf: on a part of an assembly it isolates the part and shows its row, keeping the selection; on a
    face, an edge or ink it turns the view square to it, keeping what the first click picked; on empty space it leaves
    isolation, else fits. Isolation also ends with the row's X, "Exit all isolates" or Escape, and the tree then
    shuts again what isolating opened.
  - On a GLB, STL, 3MF or robot: on empty space it fits; on a part it does nothing more.
  - On a flat view it fits; on a schematic's sheet symbol it opens that sheet.
- **Box select.** On a STEP or .xbf, Select's menu chooses Select (a drag orbits) or Box select (a drag from empty
  space draws a box; one from the model, ink or a measurement still orbits). On a flat view a plain drag under Select
  draws a box anywhere. The box takes what it touches, even in part, and in 3D only what is visible. Shift adds;
  otherwise the box replaces the selection. Escape or a second finger drops it.
- **The view's menu** (a right click; a long press on touch) is one list in every view: Copy Reference; Select,
  Isolate, Exit all isolates (on a 3D view, Select tangent faces or edges where they apply); Hide others, Show all,
  Hide; the view's own items; and last, Zoom to fit and Zoom to selection.
- **Touch.** One finger orbits a 3D view, two fingers pan and zoom, and a tap picks. A tap adds to the selection (a
  finger has no Shift), a tap on a selected item takes it out (after the double-tap window), and a tap on empty space
  clears at once, in every view (a board in 3D too). A tap takes a measurement or ink the same way. A double tap is a
  double-click, and a long press
  is a right click: the menu opens at the finger, and what the press started is cancelled
  ([Touch](design-system.md#touch)).

### Select's menu

Select carries a menu where the file has something to filter: a STEP or .xbf, a robot while it can be posed, a board,
a schematic. On a STEP or .xbf, Measure carries one too.

- The tool and its chevron are one control under one fill. Changing the filter takes the tool up.
- **The menu**: on a STEP or .xbf a "Selection tool" section comes first (Select or Box select; choosing closes the
  menu), then a rule, then ONE "Filter" row. The row names what is ticked: All, the one kind, None, or "3 of 9".
- **The Filter submenu** (in place under its row on a phone): All (a tick, or a dash when some are ticked), a rule, the
  kinds as names alone in one column, a rule, then the extras that All leaves alone (a board's Locked items, a posable
  model's Position). Ticking keeps it open. It is KiCad's Selection Filter.
- **The kinds**:
  - STEP, .xbf: Parts (assemblies only), Faces, Edges, Annotations, Measurements, and Position where the model can be
    posed. Its Measure: Vertices, Edges, Faces.
  - Robot: Links, and Position. There is no menu where nothing can be driven.
  - Board: Footprints, Text, Tracks, Vias, Pads, Graphics, Zones, Rule areas, Dimensions, then Locked items, off at
    open. A click takes the most specific item; a whole net comes from the Nets tab.
  - Schematic: Symbols, Pins, Wires, Labels, Sheets, Other items.
- Every box is ticked when a file opens (but a board's Locked items), and kept across updates of that file. With
  nothing ticked nothing lights, a click clears and a box takes nothing.
- **The badge.** The tool's tile shows its filter: no badge when everything is ticked, the one kind's glyph when one
  is, Position's knobs when only Position is, else a funnel. Why: what a click will take shows on the strip, not only
  in a closed menu.
- Select tangent faces and Select tangent edges are actions of the view's menu, never a setting of the filter.

## Tools

- **One tool in hand,** and only it lit (the pressed fill, its glyph in brand blue, no tooltip). Pressing it again
  does nothing. A tool goes down when another is taken up, or with Escape, which goes back to Select.
- **Select** is every file's default, and every open starts in it: the tool in hand is never kept. A pick in a panel
  tree takes Select up before it acts. Select has no row under the strip.
- **Measure** is the ruler.
  - On a STEP or .xbf it takes whole things, as its filter allows: a vertex within 10px of an edge's end, else the
    edge, else the face; with nothing ticked, or Shift held, a free point. A hover lights what a press would take. A
    pair reads as a CAD measure does: a distance (with ΔX ΔY ΔZ), ⟂, C-C from a hole, or ∠.
  - On a mesh (GLB, 3MF, robot) it takes two surface points, approximately, with no menu. On a flat view it snaps to
    the drawing and reads in its unit.
  - Its row is the measurements as chips, each with an X to delete it, then a rule and Clear; no row while nothing is
    measured. Measurements stay drawn under every tool, and never reach the agent or Quick Edit.
- **Explode** and **Clip** change the model and stay changed.
  - In hand, each hangs its row under the strip. Explode: its name, a slider, a whole percentage, Reset. Clip: an axis
    button (X, Y or Z, then Part colours and Reverse), a slider of the share cut away, a percentage, Reset. Values can
    be typed. There is no on/off switch: at 0 the effect is gone.
  - In hand, either stands over Select: a press picks as Select does, and the camera works as always. Put down, the
    effect stays, and the tile shows the changed dot while it is set. Reset sets the amount to 0 and keeps Clip's axis
    and settings.
  - Explode is offered only where parts can separate: a STEP assembly, or a GLB with two or more rigid parts.
- **One motion at a time.** Explode, the pose and a routine (and on a GLB or a robot, Clip) replace each other:
  setting one puts the others back at rest. None disables another's controls.
- **Undo** (⌘Z, ⇧⌘Z) walks the view's one history: ink and measurements. The camera, the selection, Display,
  Explode, Clip, hiding and the pose are not steps; each has its own way back. Draw's row has Undo and Redo buttons
  too; no other tool has them.

### Draw

Draw is the one drawing tool: ink on the model, for a note to the agent ([its mechanism](cad-renderer.md#draw)).

- **One plain button** with no chevron. It shows what it draws with (the last one used), and its tooltip names that
  and its key ("Rectangle R"). A press takes up the last tool chosen.
- **Its row** ("Annotation controls") is two rows, left-aligned, with no rule. The first is the seven drawing tools:
  Pen, Highlighter, Line, Arrow, Rectangle, Ellipse, Text. The second is seven controls: Eraser, Colour, Stroke width,
  Placement (3D only), Undo, Redo, and Clear (a bin, off with no ink). Undo and Redo are off where the history has no
  step that way, and their tooltips give their keys (⌘Z, ⇧⌘Z; Ctrl+Z, Ctrl+Y). It is the same at every width and wraps
  on a phone. Why: the order a person reaches for them, as in design tools.
- **Style** is kept per kind (the Pen, the Highlighter, the shapes); every stroke starts at 2px. The Pen and the
  shapes start red (#ff2d55), the Highlighter yellow (#ffe600), which draws five times wider at 35% opacity.
- **Colour** is a grid of seven bright colours and one neutral that reads on the picture (white on a dark Background,
  near-black on a light one), then the system's colour wheel. Stroke width (1, 2, 4, 6px) shows the lines themselves.
  Every stroke is solid. Placement is On surface (the default) or On plane; a flat view has none.
- Controls that do not apply grey out and stay where they are: the Eraser greys the three style controls. Why: the
  row never jumps.
- Draw has no Select or Pan of its own: a right or middle drag is the view's, and holding Space hands the pointer to
  the view. The cube stays live.
- **Ink stays where it was drawn**, on the model's surface or a plane, from every angle, and across a new version of
  the file: its marks are in the scene's coordinates, so a rebuild never throws away what a person drew. **Picked ink** (under Select)
  gets a small bar just above it: Colour, Stroke width, a rule, Delete. Ink has
  no panel: it is Quick Edit's Annotation chip, whose X clears it. Under Draw, ⌘C copies the view with its ink.

## Camera, animation and Preview

**The camera** (how it is framed: [cad-renderer.md](cad-renderer.md#preview-and-the-camera)):

- A drag orbits as a turntable that goes over the top: sideways about the world's vertical, up and down about the
  view's level right, never rolled. The arrow keys and a drag across the cube orbit the same way. A click on the cube
  turns the view and keeps its target and distance, landing upright.
- **Zoom to fit** (F, ⇧1, a double-click on empty space under Select, every view's menu, the zoom menu) frames what is
  shown now (exploded or posed as it stands, hidden parts left out) at the current angle, in the room under the strip.
  **Zoom to selection** (⇧2) frames what is picked, and is off with nothing picked.
- **100%** is the model as authored, framed whole: a fixed ruler that Explode, a pose, a routine, Clip, hiding and
  isolating never move. A rebuild that changes the model's box redefines it.
- **The camera is the person's once they touch it.** Until they orbit, pan, zoom, use the cube or look at a face, a
  rebuild that changes the model's box fits again (eased, as F is). Once touched, a rebuild keeps the camera exactly,
  and a fit hands it back. Why: as in desktop CAD, the view never jumps away from where the person put it.
- Projection is Orthographic unless the person picks Perspective. A Display change never refits and never touches the
  pose, the selection or what is hidden.

**Preview** presents the model as it will be seen: the picture alone, rendered at its best.

- **Where**: the navbar's last view button, right of Display (the play triangle). It is not a tool: pressing it
  leaves the tool in hand. Every 3D file offers it, and so does a KiCad board; a drawing and a schematic do not.
- **Entering** covers the view at once with "Preparing preview…" (the one loading indicator, on Preview's backdrop),
  which lifts once the picture has settled: after at least 700ms, and by 6s at the latest.
- **It hides** the navbar, the strip and its row, the corner, Quick Edit, the update line, the Display card and the
  panel (kept as it was, out of sight). Leaving brings them back as they were. **Its bar** stands in the navbar's place
  at its height, on no surface: the file's name at the left; Display (Display's cube and name, where the navbar's Display stood: the same settings for the Preview environment)
  and Exit preview (X) at the right; tooltips below.
- **The bar comes and goes** with the playbar: up on entry, hidden after 2s without pointer movement over the view
  (`PREVIEW_IDLE_MS`) or at once when the pointer leaves, back on a move, a tap or keyboard focus. It stays while
  hovered or focused, or while one of its menus or the Settings card is open. On a phone a tap shows it for 2s.
- **Its colours** are the backdrop's: the bar, the playbar and the cover take the light or dark of Preview's backdrop,
  never the app's theme. The Settings card keeps the app's theme, as the Display card does.
- **Its own view**: the model as authored (the opening pose; nothing hidden, isolated, picked, measured, exploded or
  clipped), fitted at the default angle and still, through its own perspective camera. Leaving (Exit preview, Escape,
  or another file) discards it, and the working view is as it was. The tools' and the board's keys do nothing in it.
- **The Settings card** is the Display card's component, titled "Settings", docked under Preview's bar at the right
  and closed on every entry. Its sections, parted by hairlines: Orbit (a switch on its heading, off on every entry,
  with Speed while on); Part colours (Source, then a colour or the palette; none on a board); Lighting (Quality,
  Exposure, Rotation, Softbox, Fill); Background (Colour, Opacity); Floor (a switch on its heading, on by default at
  the model's lowest point, with Colour, Opacity, Placement, Finish). Its Reset takes back only Preview's own changes.
- **The playbar**, for a file with routines, is one row under the model: the routines (where there are two or more),
  Play/Pause, the scrubber and a Playback settings menu (Speed, Loop). It plays Preview's own routine; in the tools
  view a routine plays only from its tab ([Animation](#animation)), one motion at a time ([Tools](#tools)).
- **A board's Preview** draws the whole board in 3D with the default Display, whatever the Layers tab shows: its parts
  (but missing models), with no highlight, isolation, ink or measurements.

## Settings memory

Everything the viewer keeps is kept for one browser tab (the web page: sessionStorage; the CAD app: its tab's own
store) and forgotten with it. Nothing is in localStorage, and nothing is shared between tabs. Why: a file is looked at
in a session, and settings that outlived it would surprise the next one.

- **Tab-wide**: the appearance (System, Light or Dark; a new tab follows the system), the viewport's Background (Light
  unless picked), the home's layout and its Sort, the home's sidebar (the person's choice of open or closed, and the
  width they dragged it to; nothing until they choose), and the tool stack's layout. The home's place is the host's:
  the page's address in the web page, a step of the view's history in the CAD app.
- **Per file**, by its path and its view: the panel's open state, width and tab; the Display card's values; the
  camera; Explode and Clip; the pose; hidden and isolated parts and the tree's folds; a board's layers, side, mode and
  3D projection; Preview's settings; Speed and Loop.
- A reload brings back the file on screen. The page keeps the views of up to 32 files it has left, in memory, and
  gives one back when its file is shown again. A file not yet shown opens fitted, at the defaults.
- **Never kept**: the tool in hand (every open starts in Select), the selection, measurements, ink, an open card, menu
  or peek, the phone's sheet, Orbit, where a routine was, and the home's search and its kind's chip.
- **The person's own settings** (the language, the telemetry switch, the What's new already seen) are the host's,
  kept in `settings.json` in the state folder and the same everywhere. The app menu (Settings, in the panel's foot)
  changes them; a file's view settings are never there.

## Keyboard

Keys belong to one viewer: the one with the focus, or the one last pressed in; a field being typed in keeps its own.
A file shown in a page of its own takes the keyboard where nothing else has it, so its keys work without a click.

- **Single keys** need no ⌘, Ctrl or Alt, do not repeat, and never fire in a text field or in Preview: V Select,
  M Measure, F Zoom to fit, and Draw's tools, each taking Draw up with that tool: P Pen, ⇧P Highlighter, E Eraser,
  L Line, ⇧L Arrow, R Rectangle, O Ellipse, T Text; and `[` and `]`, the previous and next file of the folder the
  document is in, in its page's order (nothing at its ends), through the same keys of the view
  (`file-viewer/projectKeys.js`).
- **⌘K** (Ctrl+K) opens the search from anywhere but Preview, a field included, and closes it again; it waits while
  another dialog is up. Inside it, its own keys ([Search](#search)).
- **Zoom**: + (or =) in and − out, by half again (also with ⌘ or Ctrl, which then zoom the view, not the page); ⇧1
  fit, ⇧2 the selection, ⇧0 100%. These repeat.
- **The arrow keys** orbit the viewer that has the focus or the pointer; never in Preview, a text field or a tree row,
  or with ⌘, Ctrl or Alt held.
- **The panel**: ⌘\ (Ctrl+\) shows or hides it, and pins a peek, over a document and over the home (there, from
  anywhere but a field being typed in). "/" opens a document's on its search (a peek searches where it is). On a phone
  ⌘\ opens and shuts the sheet, and "/" does nothing. Neither works in Preview. Tabs, tree rows and the grip keep the
  keys in [Keyboard focus](design-system.md#keyboard-focus).
- **⌘C** (Ctrl+C) copies the view with its ink as a picture under Draw, else the selection's references; never while
  text is selected or a field has the focus. **⌘Z, ⇧⌘Z** (Ctrl+Z, Ctrl+Y) undo and redo ink and measurements.
  **Delete** or Backspace deletes picked ink and measurements.
- **A board**, while it has the keyboard: ⌘H (Ctrl+H) cycles Others, 3 switches 2D and 3D, ⇧F flips the board.
- **The home**: Up and Down move between the sidebar's places, Home and End to its ends, and Enter goes to one. Escape
  goes back to the document just left, where there is one ([The home](#the-home)), after any open menu or dialog has
  spent it, and never from the search field.
- **Escape** undoes the innermost thing first: the search, an open menu or dropdown, the Display card, the panel's
  search or its peek; then Preview; then the view's own steps, one a press and in the same order in every view: picked
  ink, a box being drawn or a measurement under way, the tool in hand going back to Select (its effect kept), the
  measurements picked, then the selection, then (in a view that isolates) the isolation. Why: Escape leaves the tool first, as in design tools, and the
  selection, which feeds Quick Edit's chips, survives it. The pinned panel never closes on Escape. Quick Edit's note has its own Enter and Escape ([Quick Edit](#quick-edit)).

## Tooltips and feedback

- Every hint is the one `TooltipHint` ([Tooltips](design-system.md#tooltips)); below is which controls have one.
- **Which side**: above the strip's tools and Quick Edit's buttons; below Draw's row, the effects' Resets, the zoom,
  the navbar's Display and Preview, the logo ("Home") and Preview's bar; to the right of the panel toggle; above the
  icons of the panel's foot.
- **No hint** where the control says what it is: the logo where it opens the app menu, Back, Forward, the project's name, the name, the ⋯, the X
  on a chip or a card, Play/Pause, the scrubber, the Playback menu, Clip's axis, Colour, Clear, and buttons with words.
  Exit preview is the one X with a hint; the project's folder tile names its project in one, and a search row's Open
  in new tab says so in one. A finger never raises a hint, and the navbar's Display and Preview have none on a phone.
- **The hover tip** names what a press would pick. Every picking view's frame owns one (`HoverTip.jsx`): under Select,
  after a 450ms rest, a small tip near where the pointer stopped gives the thing's name and a short kind. It goes on
  leaving, on a press or when Select is put down, and takes no pointer. The panel never shows a pick's details.
- **Feedback is quiet.** Copy and the other clipboard actions work silently, their button showing a tick for a moment.
- **One toast**: Export. "Preparing part.step…" with a spinner while it runs, at the top right under the navbar, gone
  when the browser's download starts; or the error and its one-line reason, kept until dismissed.
- **What's new** is the one dialog the viewer opens by itself: once after a release with notes, never on a first run,
  a loading page or under a host's notice. It has one button, Got it
  ([Dialogs and sheets](design-system.md#dialogs-and-sheets)).

## Naming the page

- What a person reads says "browser" for the browser (Open in ▸ Browser, the CAD app's Open in browser) and "the
  viewer" or "this page" for the page, in every locale. The page has no other name.
- Developer docs and the skills call it the viewer too, and its command is `cad viewer`. Where a reader has no context
  (a file read on its own, a package's description), it is "the text-to-cad viewer".
- The skills say what a person can do in the viewer, never where its controls are or how they look: that is this
  document's alone.

## Not done this way

- **A cluster of view controls in the corner.** The corner navigates the camera; how the picture is drawn is the
  Display card's, the same for every file.
- **A board's Side and Mode in the Layers tab, or as navbar switches.** They are how the board is drawn, so they are
  Display's, and the navbar is the same for every file.
- **Tools other than zoom in the "100%" menu.** A zoom menu that does other things is a surprise.
- **+/− buttons and a Home button in the corner.** The zoom menu, its keys and Zoom to fit already do their work.
- **A camera "Reset view" row in the Display card.** It reads as the card's Reset; F, a double-click and the menus fit.
- **Search as a row above the tabs.** Tabs mean nothing while searching, and a second row pushes the list down.
- **A Project tab leading the panel.** It hid the model's own tree on every document of a project; the project's name,
  `[` and `]` and the search move between documents without taking the panel.
- **Document tabs in the page.** The browser already has tabs: every document and project offers a new one instead.
- **A loading animation.** The animated 3D mark looked dated, cost time, and said nothing the step line does not.
- **Icons on status screens.** The words carry the state; an icon on an empty page is noise.
- **A dimmed Quick Edit at rest.** A bar that fades at rest reads as off.
- **Autoplay for routines.** Settings last a session, so a switch to play on open saved nothing.
- **A scrim behind the phone's panel sheet.** The view stays readable beside the sheet, and a tap on it closes it.
- **A Motion tab beside Joints, and a Reset on the transport.** One subject is one tab, with one Reset.
- **Pencil and Shapes as two tools.** Draw is the one drawing tool, and its row holds them all.
- **The home as one long page of sections, a project each.** A project deep in the page was a scroll away, and each
  showed eight documents until asked. A place at a time, from a sidebar, puts each one click away, whole.
- **Document tabs inside the viewer.** The browser has tabs; every document and project opens in one.
- **A sidebar of the home's own, and a menu of places on a narrow home's heading.** Two sidebars that looked alike and
  behaved differently; the home's is the viewer's panel, collapsed, peeking and a sheet as that one is.
- **The app menu on the logo, where there is a home.** It put the way home behind a second press. The logo goes
  home; the links and Settings are the foot of the sidebar, on the home and over a document.
- **Settings as a row of words, with the links inside its menu.** Three links one press deep in a menu named for
  something else; they are icons in the foot, and the cog's menu holds settings alone.
- **A project as one flat grid of everything below it, a tree, or a setting or switch between ways.** A flat grid
  lost where each file was; a tree is a second way to see one folder; a switch asks the person to choose how to look
  before they look. A project's page is one folder of it, and the search is where levels are flattened.
- **Pictures drawn out of sight for cards.** The home read and drew files nobody had opened, on a timer. A card shows
  the picture a page took of its file, or its format's tile.
- **Delete on a card, and Remove from Recents.** A viewer that reads files never deletes one, and the list of what was
  opened needs no pruning by hand: the item was one more line in every card's menu.
- **A place of the documents in no project (Standalone).** Drive has no place of files in no folder: such a document is
  in Recents, Starred when starred, and the search.
- **Counts in the sidebar.** Figma's and Drive's have none: a count is a number nobody acts on.
- **Where a card is, before its activity, and a project's folder from `~` beside its name.** A card's line is its
  activity, as Figma's is; where a file is, is Copy path's.
- **Kind tabs (All, 3D models, Drawings, Boards, Robots) over a place.** The owner asked "what is the utility of the
  doc type filters? It feels unnecessary": a place is short enough to scan, the search narrows it, and a second row of
  filters pushed the content down. The head is one row, with Sort and the layout at its right.
- **Where, Size, Created and Updated columns in the list, and Sort by size, created or kind.** The owner asked "what
  is the purpose of 'Where'? I would strip this down to its minimum in terms of what is actually useful, same info as
  what is in the card": the list shows a card's own facts (name, type, last viewed, last edited), and Sort orders only
  what the list shows. Where a file is is Copy path's; its size and the day the library first knew it are nobody's
  question on a home.
- **"Home" in the navbar over the home, and the place's name at the navbar's size.** The logo is the way home and the
  place's title says where the person is: a name after the toggle said it twice, and a title the body's size read as
  no title. Figma's file browser titles a place one step over its body.
- **A "Sort" label beside a dropdown.** The dropdown's fill ran into the label; Sort is one control, its glyph saying
  what it is, as Figma's is.
- **A second small size for a card's line, the formats or the sidebar.** Figma's file browser is one body size told
  apart by weight and colour; the sidebar is a page's navigation, at the page's body size.
- **Recent files on every folder's page.** A folder's page is the folder; recent files lead at a project's root, as
  Drive's and Box's lead at theirs.
- **A card for a file the viewer does not open.** Its picture's space held only a glyph on an empty gradient, a
  picture's room with no picture in it; it is a folder's compact tile, after the cards.
- **A File… and Folder… menu in front of a chooser that takes either.** A Mac's open panel takes a file or a folder,
  so the menu asked what the system's own dialog asks; Import there is one button, as VS Code's "Open…" is.
