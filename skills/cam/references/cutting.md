# Cutting: parts cut out of sheet on a laser, plasma, waterjet or router

One operation, `cut`, cuts every profile of a flat part out of a sheet: a `.dxf` (its closed
profiles) or a `.step` plate (its outline, which must be the same through the whole thickness: a
plate with a pocket, a step or a chamfer is refused; mill it instead). Holes are cut before the
outline that holds them, the cut is offset to the waste side so the part comes out at its drawn
size, and each profile starts on a straight run away from corners.

Read the profiles first: for a `.dxf` `cadgen cam features` lists each closed profile with its size
and holes. A drawing's blocks are expanded with their placement; its text, dimensions and hatches
are skipped and counted in a `warning:` line; any other entity (a point, a 3D face, an image) is
refused naming its handle, so delete it or redraw it as curves. A `.dxf` is cut from a `sheet`
stock that names its `thickness_mm` (a drawing has none of its own).

A flat part the user sends to a cutting service rather than cuts themselves needs no toolpaths: it
is a DXF, which the `$dxf` skill draws and `$sendcutsend` checks before upload.

```bash
cadgen cam features bracket.dxf
```

## A minimal job

A 3 mm mild steel bracket on a 1.5 kW fibre laser, cut from a sheet with a 5 mm border, two
microjoints on each part so they stay in the sheet:

```json
{
  "machine": {"kind": "laser", "post": "grbl", "power_w": 1500, "laser_source": "fiber"},
  "material": "steel-1018",
  "stock": {"kind": "sheet", "thickness_mm": 3, "margin_mm": 5},
  "tools": [{"id": "T1", "type": "beam", "kerf_mm": 0.2}],
  "setups": [
    {"id": "sheet", "orientation": "+Z", "origin": "stock-top-corner", "operations": [
      {"op": "cut", "tool": "T1", "tabs": {"count": 2, "width_mm": 0.5}}
    ]}
  ]
}
```

```bash
cadgen cam plan bracket.dxf --job bracket.cam.json
```

The setup looks down on the sheet (`orientation` `+Z`, or `-Z` to cut it flipped); WCS zero is
usually the sheet's corner (`stock-top-corner`). Laser, plasma and waterjet cut with a `beam` tool
(`kerf_mm`, the cut's width); a router cuts with a `flat` end mill.

## The machine

`machine.kind` is `laser`, `plasma`, `waterjet` or `router`. The cutting speed comes from a table of
starting points for a reference machine, scaled by these keys (each refused on another kind):

| key | kind | meaning |
| --- | --- | --- |
| `power_w` | laser | the source's power. Default: 1500 W for fibre, 100 W for CO2 or a diode. Speed scales about linearly with power |
| `laser_source` | laser | `fiber` (metals), `co2` (wood, acrylic, plastics; metal only from 500 W), `diode` (wood and dark plastics, never metal). Default: fibre for a metal, CO2 for anything else |
| `amps` | plasma | the cutting current. Default 45 A; another current cuts thickness t about as fast as 45 A cuts t x 45 / amps |
| `abrasive` | waterjet | `true` (default: abrasive, cuts metal and stone) or `false` (pure water: foam, rubber, soft plastics only) |

A material the table has no row for (a plasma on acrylic, a fibre laser on plywood) is refused in
one sentence; give the operation a `feed` (mm/min) to cut it anyway. A thickness past the table's
thickest row is extrapolated and said so as a warning.

## The operation's keys

Beside the keys every operation takes (`tool`, `feed` to override the speed, `name`), a `cut`
takes:

| key | machines | default | meaning |
| --- | --- | --- | --- |
| `direction` | all | `climb` | `climb` keeps the part on the right of travel (outsides clockwise, holes counter-clockwise: the good side of a plasma arc, climb milling on a router); `conventional` reverses it |
| `tabs` | all | none (router: on) | microjoints on outside profiles: `{"count": 4, "width_mm": 0.5}` (a beam's width defaults to two kerfs, at least 0.3 mm); a router's also take `height_mm`. Count 0 for none |
| `lead_type` | beams | `arc` | `arc`, `line` or `none`: the lead-in and lead-out on the waste side |
| `lead_in_mm` | beams | laser 1, plasma 4, waterjet 2 | the lead-in's radius (arc) or length (line); it shrinks to a half and a quarter, then becomes a line, then is dropped (pierced on the profile, said as a warning) to stay clear of the part |
| `lead_out_mm` | beams | laser 0.5, plasma 2, waterjet 1 | the lead-out, the same way |
| `pierce_s` | beams | from the thickness | the dwell with the beam on before moving (a waterjet's grows with how slowly it cuts) |
| `pierce_height_mm` | beams | laser 2, plasma 3.8, waterjet 2 | the head's height over the sheet while piercing |
| `cut_height_mm` | beams | laser 1, plasma 1.5, waterjet 2 | its height while cutting |
| `corner_slowdown` | beams | `true` | slow to cos²(turn/2) of the speed (at least 0.3) within 1 mm or two kerfs of each sharp corner |
| `power` | laser | 1 | beam power, 0 to 1 |
| `small_holes` | plasma | `slow` | holes under 1.5 x the thickness: `slow` cuts them at 0.6 x speed, `warn` at full speed; both warn that they come out tapered |
| `quality` | waterjet | 3 | edge quality 1 (separation, fastest) to 5 (finest): 2.0, 1.4, 1.0, 0.75, 0.6 x the table's speed |
| `ramp_angle_deg` | router | 3 | each depth is ramped into along the profile itself at this angle (no leads) |
| `breakthrough_mm` | router | 0.3 | how far below the sheet the last depth goes, into the spoilboard |

A router's step down is `stepdown_mm` (default from the material and the bit); its tabs default to
2 to 8 per outside profile (one per 150 mm of outline, plus 2), the bit's width or 4 mm wide (whichever is wider) and a
third of the sheet (1 to 3 mm) high. A tab that does not fit a small part is left off and said so.

## What it does

1. **Kerf compensation.** Each outside profile is offset outward and each hole inward by half the
   kerf (a router: the bit's radius). A hole as narrow as the cut is cut along its middle; one
   narrower is not cut, and a warning says where.
2. **Order.** Every profile lying inside another is cut first (a part's holes, then any part
   nested in a hole, before the outline around them), then nearest-neighbour from the head.
3. **Pierce.** On a straight run at least 1 mm, two kerfs and the lead-in from any corner, nearest
   the head; on an all-curved profile, nearest the head.
4. **Beam processes.** Rapid at the clearance height to the lead's start, down to the pierce
   height, beam on with the pierce dwell, down to the cut height, lead-in, the profile (slowed at
   corners, the beam off over each microjoint and re-pierced after it), lead-out, beam off.
5. **Router.** Down to the retract plane, then for each depth a ramp along the profile (never across
   it: round a short profile in laps, forward and back over a long one's first stretch before its
   first tab; a round profile by helical arcs) and the full profile, lifting over the tabs on the
   depths below the tab's top. A hole exactly the bit's size is plunged (a warning says the bit must
   cut at its centre).

## Reading the result

The operation's row reads like `Cut out 8 profiles with T1 0.2 mm kerf beam at 3000 mm/min`; a
beam has no spindle (`rpm` is null). Its `facts.cut` carries the numbers:

| fact | meaning |
| --- | --- |
| `kerf_mm`, `thickness_mm`, `speed_mm_min`, `speed_from`, `source`, `pierce_s` | what it cut with, and the table row the speed came from |
| `profiles`, `outsides`, `holes`, `pierces` | what it cut (each microjoint adds a pierce) |
| `leads_in`, `leads_out`, `leads_shortened`, `lead_type` | the leads fitted; shortened ones had no room at full size |
| `corners_slowed`, `tabs`, `small_holes` | corners with a slowdown, microjoints left, small plasma holes |
| `parts`, `parts_free`, `parts_held`, `parts_not_free`, `slugs_drop` | which parts fall out of the sheet, which stay held by microjoints until broken out, which are not cut free (a profile that does not close, parts closer than a kerf), and how many scraps drop out of holes (a slug crossed by its lead-in and lead-out counts as its pieces) |
| router: `depths`, `stepdown_mm`, `breakthrough_mm`, `tab_height_mm`, `tab_width_mm` | the depths and the tabs |

Findings to expect: `corner_radius` (a warning) names inside corners the kerf or the bit cannot
reach (a plasma's 1.5 mm kerf leaves a 0.75 mm radius in a square hole's corners; a router bit its
radius); `material_left` (a warning) is what the simulated sheet still joins to a part: those
corners, a hole that was not cut, a sliver between two cuts, or a part not cut free. Warnings also
say when a lead was dropped, holes were too small, or parts sit closer than the kerf. A router's
cut is also judged for gouges and reach (flute length against the sheet plus the breakthrough).

The simulated stock in the GLB is the sheet with every kerf taken out. Speeds, pierce times and
heights are starting points: cut a test coupon and measure the kerf before cutting parts.

## Limits

- Only through-cuts of a flat part along the setup's Z: no bevel cutting, no marking or etching
  passes, no common-line cutting or nesting (place the parts in the DXF where they should be cut).
- Microjoints go on outside profiles only.
- The torch height control, the controller's own corner handling and the machine's cut charts are
  the posts' and the operator's: see [posts.md](posts.md) for each post's machine keys.
