# The job file

One JSON object, passed as `--job part.cam.json` or as inline JSON. Every key set is closed: an
unknown key or value is refused, naming the keys or values allowed, and nothing is written. All
lengths are mm, feeds mm/min, speeds rev/min.

| Key | Value (default) |
| --- | --- |
| `machine` | Required. [Machine](#machine) |
| `material` | Required. [Material](#material) |
| `stock` | Required. [Stock](#stock) |
| `tools` | Required. A list of at least one [tool](#tools) |
| `setups` | Required. A list of at least one [setup](#setups) |
| `name` | The job's name, heading each posted program (the job file's name, else `job`) |
| `tolerance_mm` | How closely FreeCAD follows curves, 0.01 to 1 (0.01) |
| `coolant` | `off`, `flood` or `mist`, for every operation that does not say (`off`) |

## Machine

| Key | Value (default) |
| --- | --- |
| `post` | Required, no default. `grbl`, `linuxcnc`, `mach3` (Mach3 and Mach4), `fanuc`, `centroid`, `uccnc` or `smoothie`. Ask the user which controller runs the machine |
| `name` | The machine's name, for the result |
| `travel_mm` | `[x, y, z]`: a setup whose moves span more is a `travel` error (not checked) |
| `max_rpm` | Required. The spindle's top speed: a faster table speed is held to it, a `clamped` warning |
| `min_rpm` | The spindle's slowest: a slower table speed is raised to it, a `clamped` warning (not checked) |
| `max_feed_mm_min` | The fastest feed: a faster one is held to it, a `clamped` warning (not checked) |
| `rapid_mm_min` | The rapid rate, for the cycle time only (3000, listed as assumed) |
| `work_offset` | `G54` to `G59` (`G54`) |

## Material

A name from the feeds table, as text (`"material": "aluminum-6061"`) or as `{"name": ...}`:

`aluminum-6061`, `aluminum-7075`, `steel-1018` (or `mild-steel`), `stainless-304`, `brass`,
`delrin` (or `acetal`), `acrylic`, `hdpe`, `mdf`, `hardwood`, `plywood`.

The table's numbers are conservative starting points for carbide tools, not tuned for any machine:
say so. Override any of them in the object, or give a material that is not in the table with at
least `surface_m_min` and `chipload_mm` from the tool maker's chart:

| Key | Value |
| --- | --- |
| `name` | A table name, or the material's own name |
| `surface_m_min` | Cutting speed, m/min: rpm = 1000 × it / (π × diameter); a drill turns at 0.6 of that |
| `chipload_mm` | Chip load per tooth for a 6 mm tool; cadgen scales it with the tool's diameter |
| `drill_mm_per_rev` | Drill feed per revolution per mm of drill diameter (0.02 in aluminium: a 5 mm drill feeds 0.1 mm/rev). A material that is not in the table needs it for a job that drills: without it a `drill` is refused |
| `stepdown_fraction` | The default `stepdown_mm` as a fraction of the tool's diameter (0.5 in aluminium, 0.25 in steel) |

The milling feed is rpm × flutes × chip load (more at a light stepover to make up for chip
thinning), the plunge 0.3 of it. An operation's `feed`, `speed` and
`plunge_mm_min` win over all of this.

## Stock

| Key | Value (default) |
| --- | --- |
| `margin_mm` | A number, or `[x, y, z]`: the part's bounding box grown by x and y on each side and by z over the top (0). The stock's bottom is the part's bottom |

There is no other stock shape. The blank the user clamps must be the size this makes.

## Tools

| Key | Value (default) |
| --- | --- |
| `id` | Required. The name operations use, like `T1`: letters, digits, `-` and `_`, since it names a posted file when a post takes one tool a program |
| `type` | Required. `flat` (end mill), `ball`, `bull` (bull nose) or `drill` |
| `diameter_mm` | Required |
| `number` | Required. The T number posted, 0 to 9999, as the machine's tool table has it; one per tool |
| `name` | The tool's name, for the result |
| `flutes` | `flat`, `ball` and `bull` only, and required: 1 to 100, the feed is worked out from it. A `drill` is fed per revolution and takes none |
| `flute_length_mm` | Required. The cutting length, which every cut's depth is held to |
| `stickout_mm` | Required. The length out of the holder, flutes included, at least the flute length (FreeCAD models the tool from it) |
| `shank_diameter_mm` | `flat`, `ball` and `bull` only, and required (FreeCAD models the tool from it; its drill has no shank of its own) |
| `corner_radius_mm` | `bull` only, and required: more than 0, at most the radius |
| `point_angle` | `drill` only, and required: 60 to 180 degrees, its point's included angle, which sets how far past a through hole's bottom it drills |

Nothing about a tool has a default: a tool missing one of these is refused, naming it. Ask the user for it.

## Setups

One setup per way the part is held. Its posted file is named for its `id`.

| Key | Value (default) |
| --- | --- |
| `id` | Letters, digits, `-` and `_` (`setup1`, `setup2` ...) |
| `orientation` | `+Z`: the tool comes down on the part's top; `-Z`: the part turned over about X, the tool on its bottom (`+Z`) |
| `origin` | The work zero: `stock-top-center`, `stock-top-corner`, `stock-bottom-center` or `stock-bottom-corner`, in the setup's turned stock (`stock-top-center`). A corner is the low-X, low-Y one |
| `operations` | Required. A list of at least one [operation](#operations), run in order |
| `clearance_mm` | The height above the stock the tool moves between operations (5) |
| `retract_mm` | The height above the stock the tool retracts to between cuts; at most `clearance_mm` (2) |

## Operations

Every operation takes these keys; [SKILL.md](../SKILL.md#the-operations) lists what each `op`
cuts and its own keys.

| Key | Value (default) |
| --- | --- |
| `op` | Required. `face`, `profile`, `pocket`, `adaptive` or `drill` |
| `tool` | Required. A tool's `id`: a `drill` for `drill`, a `flat`, `ball` or `bull` for the rest |
| `faces` | Face refs as `cadgen cam features` lists them. Required for `pocket`, `adaptive` and `drill` |
| `feed` | Feed, mm/min (the table's); the plunge scales with it |
| `speed` | Spindle, rpm (the table's) |
| `plunge_mm_min` | Plunge feed (0.3 of the table's feed) |
| `coolant` | `off`, `flood` or `mist` (the job's `coolant`) |
| `name` | The operation's name, for the result |

And each operation's own:

| Key | Operations | Value (default) |
| --- | --- | --- |
| `stepdown_mm` | `face`, `profile`, `pocket`, `adaptive` | Depth per pass, at most the flute length (the material's `stepdown_fraction` of the diameter) |
| `stepover` | `face`, `pocket`, `adaptive` | Width per pass as a fraction of the diameter, up to 1 (0.4; `adaptive` 0.15) |
| `side` | `profile` | `outside` or `inside` the outline (`outside`). `inside` with a through bore's or a slot's walls in `faces` cuts the bore or slot out, with a tool narrower than it; `inside` takes walls, or a pocket's floor for that pocket's walls (walled all round, nothing opening in it: the plan names the walls it cut), never another flat face |
| `through_mm` | `profile`, `drill` | How far past the part's bottom (a through hole's exit for `drill`, plus the drill's point) to cut, up to twice the tool's diameter (`profile` 0, `drill` 1). A `profile` of a blind feature stops at its floor |
| `leave_mm` | `profile`, `pocket`, `adaptive` | Stock to leave on the walls for a finish pass after, up to the tool's diameter (0) |
| `peck_mm` | `drill` | Peck depth (none: one plunge) |
