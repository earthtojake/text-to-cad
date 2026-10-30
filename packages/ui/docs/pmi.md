# PMI

An engine document's PMI — its product and manufacturing information: dimensions with their
tolerances or limits, datum features, geometric tolerances (GD&T) and numbered notes, with each
part's named views and what its coverage check found — in the CAD viewer: read from the document,
drawn on the model, picked, hidden, walked view by view, and asked for. It is the document's own,
not the person's: ink (Pencil and Shapes, [annotation](annotation.md)) is a note on a view and goes
with a prompt; PMI is what the part is made to, and goes with the part.

The document is made from code. A model declares its PMI with `cadgen.ap242`'s calls, each that
writes an AP242 entity named after it (`annotate(body, datum("A", ...), dimensional_location(...),
flatness_tolerance(...), ...)`; `note` and `view`, the xbf's alone, write none), the engine writes
its requirements into the document's XCAF GD&T attributes, which its AP242 export reads, and the
served structure carries it (`structure.pmi`, absent where there is none; beside it
`pmi_views`, the xbf's alone, and `pmi_coverage`, served for a STEP's PMI too).
So the viewer writes
nothing: a change asked for in the viewer is the call the model's code should make, which Quick
Edit hands the agent, and the change reaches the view as the engine's next version.

## What is said, and where it comes from

`@text-to-cad/core/lib/xbf/xbfPmi.js` reads the structure (`readXbfPmi`), each field read as it is
or as nothing, never guessed, into `{ entries, notes, views, coverage }`: every annotation
and note (`entries`); the ones said as each part's numbered notes, in their numbers (`notes`: its
general profile Note 1, then its notes); each part's named views in the code's order, keyed by
part and name (`views`); and, of each part carrying PMI, the faces no requirement is on and the
requirements that cannot both hold (`coverage`). An entry is one of:

- A **dimension** (`distance` between two parallel flat faces, `diameter` of a round one): its
  nominal is the engine's, measured on the geometry (`source: "geometry"`), or as another system's
  file gives it (`source: "file"`, said so in its values); its tolerance is what
  the code supplied (`plus_minus_tolerance(upper, lower)`, or its **limits**, `limits(lower, upper)`:
  its least size and its greatest, which need no nominal, a file's having none), and none where it
  supplied none. The viewer never fills a tolerance in, not even a default. A **basic** dimension
  (`dimensional_location(..., basic=True)`,
  `dimension.basic`: theoretically exact, as a position tolerance's true position is located) is a
  distance between flat faces and holes, a hole by its axis; it holds no tolerance at all, and its
  number is drawn boxed, as a drawing draws it.
- A **datum**: its letter.
- A **geometric tolerance** (`flatness`, `position`, `surface_profile` on one face or several):
  its value, a diameter zone, the datums it refers to. A part's **general profile**
  (`general_profile`, `general: true`: every face nothing else controls, within its value of
  true, to its datums) is its Note 1; its refs are the faces it covers this build.
- A **note** (`note`): its number, its words, and a **flag note**'s faces and the annotations it
  names (a general note names neither).
- Anything else the document holds (a STEP's cylindricity, an angle) is an entry the viewer
  does not draw: listed, saying why (`unsupported`: the engine's `reason` where it gives one, else
  the viewer's own, with its XCAF type), never dropped. Whether it is drawn is the viewer's to say;
  `cadgen snapshot` reads it by the same rule.

An id is the author's and unique on its part (a datum's is its letter), so an annotation is known
by its part (`part`, the structure's prototype) and its id together (`key`, `pmiKey`: `0:thickness`),
and two parts may each have a datum A.

`pmiCallout` says each as a drawing writes it: the nominal at its tolerance's places or at what it
needs (up to four), whichever is more (`pmiDimensionPlaces`: `⌀6.35 ±0.1`, `25.40 ±0.05`,
`3.175 basic`), `±0.2` where it is the same both ways and the two deviations stacked where it is not, true minus
signs; limits in place of the nominal, `9.8–10.2` (an en dash), drawn stacked, the upper over the
lower; a datum's letter in its box; a frame's cells — its characteristic (**Surface profile** ⌓
among them), `⌀` and its value, each datum; a flag note its flag and its number; the general
profile as a drawing's notes say it, "Unless otherwise noted, all surfaces profile 0.5 to A",
drawn as no callout. The characteristic, `⌀` and flag glyphs are drawn (`xbf/pmi/pmiGlyphs.jsx`), not typed: most UI
fonts lack them. A kind's glyph is neutral, never a status's colour.

## References and their state

Each reference is the engine's ref grammar (`cadgen.engine.refs`): `refs[].ref` canonical where it
resolved, `refs[].written` as the code wrote it, and a status — `ok`, `missing` (it names nothing
in this build), `ambiguous` (it names several, its `candidates` listed) or `invalid` (it names a
face the annotation cannot stand on: a diameter on a flat face, say). A dimension whose reference
broke has no nominal, there being nothing to measure: it says `?`. The engine resolves
them on every build; the page finds the same element (`xbf/pmi/pmiRefs.js`) by spelling each
candidate's canonical ref as the tree does and keeping exact matches, and finds none for a ref
that is not `ok`. An annotation whose reference broke is drawn where its code placed it, its
leader ending in an open ring where the code anchored it (there is no face to point at), its box
and leader dashed in the status colour (missing and invalid red, ambiguous amber), and its row and
values say why — the engine's own words where it gives them. It is still its part's (`part`),
linked to no geometry, so it keeps its key, its pick and its eye across the rebuild that broke it.
A reference that resolved is named as a pick's chip names it ("plate · face 7"), its canonical ref
its copy.

## Drawing it

`@text-to-cad/core/lib/xbf/xbfPmiLayout.js` makes each annotation's construction in the scene's
coordinates from the elements its references name (`elementGeometry`): the point on its feature
a leader starts from (a flat face's own node nearest its middle, so never in a hole; a hole's rim),
where its label stands, and a distance's dimension and extension lines: along what it measures (the
first flat face's normal; between two holes, square to both), each extension line from its end's
plane, or from a hole's centre line.
`presentation` (`place(anchor, offset)`: the anchor on the feature and the label's offset from
it, in millimetres in its part's frame, `part` the structure's prototype; drawn where the part
stands, `pmiPresentationToScene`, and written back in its frame) is where the code
placed it; one the code never placed stands out from its feature, each of a
feature's turned from the last. A placement says where a callout is drawn and nothing else.
`pmiConstructions` is that loop over a document, the one the viewer draws and cadgen's stills are
held to (`__fixtures__/pmi_plate/constructions.json`). A flag note is drawn as a frame is, out from
its first face. What is said in the notes alone is drawn on no face (`pmiDrawnOnPart`): a general
note, the general profile, and a flag note naming annotations and no face — drawn on its
annotations' faces it would say it is about those faces, which its code never said, and the viewer
cannot stand a flag beside another callout's label, so it is listed, and its pick lights what its
annotations are on.

A repeated part's occurrences carry the same faces (`xbf/pmi/pmiRefs.js`): an annotation of the
part is about those faces on every occurrence, so a pick of any of them finds it, and it is drawn
once, at the first occurrence that is shown — not hidden, and in the isolation where one is set
(`pmiDrawnAt`). Where no occurrence of its part is shown it is not drawn, and stays listed; one
whose reference broke is drawn where its code placed it, in its part's frame. One of no part
(another system's, linked to nothing) is in the scene's frame.

`xbf/pmi/PmiOverlay.jsx` draws them over the viewport, as the joint handles are drawn: the labels
are DOM at the UI's size whatever the zoom, laid out again on every frame the camera or the view's
size moved, and the leaders (an arrow at the feature, a datum's filled triangle) and dimension
lines (arrows inside, or outside where the line is short) on a canvas under them. A distance's
words stand beside its line, out from the part. Labels the code did not place are set apart on
screen where two would cover one another (`separateLabels.js`). A leader or extension line whose
start the model hides from the camera (a datum on the bottom, seen from above) is drawn faint,
its marker hollow (`pmiHidden.js`: a ray through the point, its first surface nearer by more than
a thousandth of the model); the labels themselves are always on top, to be read. They are drawn on the model as
built: while Explode or a pose moves the parts they are not drawn, and the section says so.

## The MBD panel

The PMI section (`xbf/pmi/PmiSection.jsx`) is read as a machinist reads a drawing: under its head
(New, the eye of them all), four groups, each under a static heading with a rule above all but the
first, none folding ([settings UI](settings-ui.md)), each there only where it has something (a
document with no annotation, note or view at all says "No PMI yet" instead):

- **Views**: a row per view, its glyph, its name and what it shows ("4 annotations", or "All" for
  one that names none), each part's said where several parts have views (two may share a name).
  A pick applies it and a second leaves it; another view's pick applies that
  one instead. Applied (`xbf/pmi/usePmiView.js`, `pmiViews.js`): the camera is set down its
  direction (from the part toward the eye, as the stills' presets) with its up, fitted to its
  part's box where the part stands, through the viewport's own camera (`setPerspective`), the
  projection staying the person's; its section is the Clip's settings (`{ enabled, axis, at,
  invert }`), placed from the part's frame to the scene's; only what it shows is drawn, its own
  placements first (`pmiConstructions`' `placements`). Each is seen from the first occurrence of
  its part that is shown, as its PMI is drawn there. Where that occurrence's placement turns the
  section's axis off a world axis (a part placed at an angle), it is not cut along another: the row
  says "Its section is not on this placement's axes" and the view applies its camera alone. Left,
  the camera and the Clip are as they were before the first view was picked; a view with no
  section leaves the Clip as the person had it. In a view a label stands where the view places it,
  so it is neither moved nor pinned there. A view is never an annotation: a view "A" and a datum A
  are picked apart.
- **Notes**: a row per note, "1. Unless otherwise noted, …", in their numbers (the general profile
  Note 1 with its profile glyph, a flag note with its flag, a general note bare), each part's said
  where several parts have notes. A pick opens its words whole under its row; a flag note's lights
  its faces, and its eye hides its flag.
- **Coverage**: of each part, "N faces have no requirement" or "Every face has a requirement",
  then each conflict the engine found, in the warning colour, by its ids and the engine's words: a
  datum no tolerance's frame names, a flag note linked to nothing, and each requirement that cannot
  hold with another. **Show faces with no requirement**, the checkbox at the heading's right end,
  lights those faces as a pick is lit; the group's lines stay either way. It warns, as the engine
  does: nothing here fails.
- **Annotations**: every other entry, as below.

## Picking, hiding, and asking

Under Select a label is a control. A click picks its annotation, and its features are lit as a
pick of them is (the renderer's element highlight); its row in the section opens its values. A
double-click looks at its feature (`lookAt`). Escape lets it go, and a press on the model does.
Under any other tool the labels take no pointer.

The section's eyes hide one annotation, or all of them; what is hidden is the file's view
(`xbfViewSlices.js`'s `pmi` slice, by each annotation's key, kept across a rebuild of the same
parts), never the document. Turned off, PMI is off in a prompt's views too (`display.pmi` false).

Where the document is made from code (a model's, by its id, or an `.xbf`), what the person
changes is asked for, never written (`xbf/pmi/useXbfPmi.jsx`), each a chip in Quick Edit (its `requests`) that carries one
paragraph of what to do to its part's `annotate(...)` call, the annotation by its author's id,
the part by its name and the names it and the call take from `cadgen.ap242` (`from cadgen.ap242
import annotate, ...`), and the call itself (`pmiChangeRequest`), what it does not change as the
document says it (a label, a position's zone, round or not):

- **Move**: a drag of the picked label, on the plane facing the view through where it stood. It
  stands where it was let go, ringed, until the change goes; the request sets only `presentation`.
  **Pin placement** writes an annotation the code never placed where it is drawn now.
- **Edit**: a dimension's tolerance (`±0.1`, `+0.1/-0.05`, its limits `9.8–10.2`, or nothing
  for none), a geometric tolerance's value and a position's datums, committed as the section's
  fields are. Limits are two unsigned sizes, the least first, between an en dash (the field's own
  text for them, so a limits dimension's field reads back as its limits), a hyphen or "to"
  (`10.00-10.05`, `10.00 to 10.05`: `limits(10, 10.05)`); a signed or slashed pair stays
  deviations (`+0.1/-0.05`, `0.1 -0.05`). The label keeps saying what the document says until the
  code does.
- **New**: from a face's menu ("Add datum", "Add flatness"... whatever it and the faces picked with
  it can carry, which picks them and opens the PMI section on the form), or the section's New, of
  the faces Select has picked: one of the supported subset — a datum on one flat or round face, a
  flatness on one flat face, a distance between two parallel ones, a basic dimension between two
  of flat faces and holes, all parallel, a diameter or a position on a round one, a **surface
  profile** on one face or several of one part, of any kind (`surface_profile_tolerance`, its datums its
  part's, none to three) —
  with an id and a letter its part has none of, its references the faces' canonical refs, its
  datums its part's, and its values given (a geometric tolerance's value required; a dimension's
  tolerance only if given). A kind the pick cannot make is off in the menu, saying what it needs.
  Until it is built it is called by its id ("Add flatness"), a datum by its letter ("Add datum B").
  After a rule, what is of the faces' part, or, with nothing picked, of the document's one part:
  - **Note**: a flag note on the faces picked, a general note where none are (`note`). Its
    words are typed; nothing starts them, cadgen ships none. A face's menu offers it as
    "Add note", a flag note.
  - **General profile**: no face to pick (`general_profile`, its faces each build's), its value
    and its datums given; offered while its part has none, built or asked for ("Its part has one").
  - **View from here**: the view the viewport shows now, as a named view of the part
    (`view`), seen from the first occurrence of the part that is shown and taken back through
    its placement into the part's frame, as `pmiViews.js` places a view (`pmiViewFromHere`): the
    camera as `camera(direction, up)`, `direction` from the target toward the eye (as the
    stills' presets), `up` the screen's; the Clip, while it is on, as `section(axis, at,
    invert=True)` where it keeps the upper side; `shows` the part's annotations drawn now, by id.
    Its name is fresh among its part's views ("view", "view-2"...) and the person's to change. Where
    the placement turns the Clip's axis off the part's axes it is refused, saying "Its section is
    not on this placement's axes" (it is no section of the part, nor made one along another axis);
    it is not offered while the parts are moved. Called by its name ("Add view").

The call names its references as this build resolves them (canonical refs, which name the same
elements however the code wrote them) and asks the agent to keep the code's own. A STEP is not made
from code here: its PMI, where the engine serves any, is read alone.

## Reviewing requirements and the export

The PMI section follows the selected annotation's faces, or the selected geometry when
no annotation is picked. It lists every attached requirement, including hidden callouts.
**Show all PMI** restores the whole list; **For selection** returns to the filter. A selection
with no attached PMI says so without implying that it needs no requirements. A dimension
with explicit tolerances also shows **Current limits** (nominal plus each signed deviation, or the
limits it was given, at the places its nominal is written at), from the saved document, never a
guessed tolerance or an unapplied Quick Edit.

A position tolerance lists its datum references in primary, secondary and tertiary order.
These buttons highlight the datum's geometry without changing its assignment or adding a
Quick Edit. Selecting a datum lists the tolerances that use it under **Used by**. Both
directions resolve within the annotation's part.

**Export** in the top-right toolbar lists the formats the file's kind writes, STEP among them,
written from the built document with its GD&T; a Quick Edit request not yet built is not in it.
Its notes and named views are the document's: a STEP carries neither, and is
not refused for them. Where the document carries PMI, the menu's muted lines under the formats
say so, and where it holds notes or views, which of them stay in the XBF ("Notes and named views
stay in the XBF: a STEP carries the GD&T."), from what the view already holds (`ExportView.pmi`, `export/context.ts`: `gdt` and `kept`),
nothing inspected first. The export service pins the
revision on screen, holds the job and its file, and never runs the model's code. A file that
would not carry the PMI the code made whole is refused by its job, and its toast says why: a STEP
that would drop an annotation linked to no geometry, and an XBF of a model held by its id, which
the engine writes as the document made again, carrying none of its PMI yet. There is no STEP of a
pose or of one part to refuse: those are models of their own.

Once the STEP is written, before it is handed over, the worker reads that same file back on its
own and compares its supported annotations with the document's, one to one, each part against its
own product's records: values, units, datum order, tolerance-zone form and the faces each is on,
by name and geometry -- as `cadgen export` does. The result and the file's SHA-256 go with the
export job, and stay with it when another model opens. An export has no success toast of its own
(the browser's downloads say the file came); a STEP's check is its toast once the file is handed
over, the check's headline as its title (every annotation verified, which goes on its own): the
check is part of the export, with no endpoint or export of its own. The browser's save writes that
file; a save that fails never says Saved.

Missing or extra annotations, no PMI, a parser problem or a schema other than AP242 fail the
check. Both signed deviations' units are checked. Face names are looked for across each part's
geometry, faces with no annotation included. An ambiguous name within a part, two source refs that
collide, a datum letter a part's records repeat, two products of one name or an unsupported
modifier fail it too. For a document the code made, a check that fails refuses the file: the job
fails with the engine's reason, its error toast, and no file is handed over. Only a STEP of a
document another system wrote, whose faces carry no names, is handed over with a check that found
problems: its toast says the check is incomplete, a warning kept until dismissed.

The check does not establish a complete manufacturing definition, nor that a factory's importer
reads the file: the result says that is untested. Graphical callouts and the author's annotation
ids are not exported; basic dimensions are, marked theoretical, and are checked as any other
dimension is. What interoperability is tested with is the exported STEP itself.

## Known limits

- No leader routing: labels the code placed can cover each other, and a leader can cross the
  model.
- Not drawn under Explode or a pose, or in Preview. `cadgen snapshot` draws it as this does, on the
  parts as made (the engine README's snapshot section); a label moved here and not yet in the code
  is drawn where the document places it.
- Only the supported subset is drawn: distance (basic or not, its tolerance or its limits),
  diameter, datum, flatness, position, surface profile, the general profile (said, not drawn) and
  notes; New makes distances, diameters, datums, flatness, positions, surface profiles, notes, a
  general profile and views from here (the rest are the code's to write: a note on annotations, a
  view's own placements or label, a preset's name for its camera).
- A view's projection is the person's (the Projection menu), not the view's; its section is cut
  only along a world axis.
- A moved label returns to the document's placement if its change is dropped or sent before the
  code has it.
- The section's strings are English, as the engine document's other sections are.
