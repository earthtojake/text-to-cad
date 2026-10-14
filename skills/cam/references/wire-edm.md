# Wire EDM: profiles cut with a wire, with skims, a hold and a taper (lite)

One operation, `wire_edm`, cuts a flat part's profiles with a wire on a 2-axis wire EDM: a `.dxf`, or
a `.step` plate whose outline is the same through its thickness. It cuts the openings of a die, the
outline of a punch, or both; roughs each one, skims it back and forth, leaves a short hold so the
slug (or the part) cannot drop onto the wire, stops so the operator can secure it, then cuts the
hold. A constant taper leans the wire for a die's relief or a punch's draft.

It is **lite**: say its limits when you report it (they ride in its result):

- Two-axis contours with one constant taper (U/V): no variable taper, no different top and bottom
  profiles.
- In a taper cut each segment leans by its own normal; how a sharp corner is tapered is left to the
  controller.
- The hold is cut once at the finish offset after a stop; it is not skimmed.
- Start holes are placed, not made: drill or EDM-drill them before the cut.
- Speeds are a generic removal rate per material for a 0.25 mm brass wire; the machine's own
  technology tables set the real ones.

## A minimal job

A 20 mm tool-steel die: cut its openings with a rough cut and two skims, 1° of relief, a 3 mm hold:

```json
{
  "machine": {"kind": "wire_edm", "post": "wire_edm"},
  "material": "tool-steel",
  "stock": {"kind": "sheet", "thickness_mm": 20, "margin_mm": 10},
  "tools": [{"id": "T1", "type": "wire", "diameter_mm": 0.25}],
  "setups": [
    {"id": "die", "orientation": "+Z", "origin": "stock-top-corner", "operations": [
      {"op": "wire_edm", "tool": "T1", "profiles": "holes", "skims": 2, "hold_mm": 3, "taper_deg": 1}
    ]}
  ]
}
```

```bash
cadgen cam plan die.dxf --job die.cam.json
```

## The operation's keys

Beside `tool` (a `wire`, `diameter_mm`), `feed` (the rough cut's mm/min; skims scale from it) and
`name`, a `wire_edm` takes:

| key | default | meaning |
| --- | --- | --- |
| `profiles` | `all` | `holes` (a die: the plate stays, the openings are cut), `outside` (a punch) or `all` |
| `spark_gap_mm` | 0.03 | the gap the spark burns beyond the wire; the finish offset is the wire's radius plus this |
| `skims` | 1 | skim passes after the rough cut, 0 to 3 |
| `skim_stock_mm` | 0.04; 0.06, 0.02; 0.08, 0.03, 0.01 | what each skim takes, one number per skim; the rough cut runs that much further out |
| `hold_mm` | 2 with skims, else 0 | the length left uncut before the start by every pass, cut last after a stop |
| `taper_deg` | 0 | constant taper, -30 to 30: positive leans the wire into the part toward the bottom (the profile is exact at the top: a die's opening grows downward, a punch shrinks) |
| `start_point` | auto | `[x, y]` in the setup's WCS: the start hole for the opening it lies in, or for the outside profile when it lies outside the part |
| `lead_in_mm` | 3 | for an outside profile with no `start_point`: how far off the profile, in the waste, its start is |

An opening starts from the point farthest from its walls unless `start_point` lies in it; the cut
runs straight from there to an entry on a straight run away from corners (or to the nearest point
of the profile when the straight way would cross the part).

## What it does

Per profile, openings first, then nearest-neighbour: rapid to the start hole (a comment says to
thread the wire there), approach, rough cut round the profile up to the hold, each skim back over
the same stretch in the other direction at a smaller offset and a higher feed, a stop
("Secure the slug"), the hold cut at the finish offset, then the wire is cut. All on the waste
side. With skims and no hold, an outside profile's part drops when the rough cut closes, so its
skims would cut air: a warning says so.

The `wire_edm` post writes the taper as `G51`/`G52 A` from each pass's direction, or as `U V` words
with `machine.uv_words` ([posts.md](posts.md)). The toolpath also carries the wire's lean on every
move (top relative to bottom, mm) for the Viewer and other posts.

## Reading the result

The row reads like `Wire cut 5 profiles with T1 0.25 mm wire, rough + 2 skims, taper 1°`. Its
`facts.passes` is the number of passes and `facts.cut` carries:

| fact | meaning |
| --- | --- |
| `wire_mm`, `spark_gap_mm`, `offsets_mm` | the offset of each pass, rough first, finish last |
| `feeds_mm_min` | each pass's feed (rough first) |
| `thickness_mm`, `taper_deg`, `uv_mm` | the work's height and how far the wire leans over it |
| `profiles`, `start_holes`, `hold_mm`, `holds` | what it cut, where each start hole goes ([x, y] WCS), the holds left |
| `parts`, `parts_free`, `parts_not_free`, `slugs_drop` | what the cut frees: parts (or, cutting only outsides, their outlines) and the slugs out of the openings |

The simulated stock is the plate with every pass's cut taken out. `material_left` (a warning)
names what is still joined to a part: openings not cut (expected with `profiles` `outside`),
corners tighter than the wire's offset, a part not cut free. Every number is a starting point:
check the start holes, the hold and the machine's technology before cutting.
