# moonwatch models

Every model of `models/moonwatch`, on cadgen 0.8 (each a `@model`; a run writes nothing):

| Script               | What it is                                | Description                                                     |
|----------------------|-------------------------------------------|-----------------------------------------------------------------|
| case.py              | model                                     | Case cluster: middle, bezel stack, crystal, caseback, crown, pushers, lugs |
| dial.py              | model                                     | Three-register step dial, applied indices, printed tracks, full hand stack at 10:09:38 |
| bracelet.py          | model                                     | Flat three-link bracelet, end links, fold-over clasp            |
| finishing_sampler.py | model                                     | Standing coupon exercising the shared finishing vocabulary      |
| movement.py          | model                                     | Complete movement = movement_base + keyless_works + chrono_works (sub-assemblies) |
| movement_base.py     | `@memo` layer of the movement             | Main plate, barrel, going train, bridges, escapement, balance  |
| keyless_works.py     | `@memo` layer of the movement             | Stem, winding/sliding pinions, setting lever, yoke, motion works |
| chrono_works.py      | `@memo` layer of the movement             | Column wheel, levers, lateral clutch, runners, hammers          |
| moonwatch.py         | model                                     | The full watch: case + dial/hands + movement + bracelet, its mechanism, and its four clips |

Build from this folder: `python case.py`, `python dial.py`, `python bracelet.py`,
`python finishing_sampler.py`, `python movement.py`, `python moonwatch.py`. A build
writes nothing; `cadgen export <id> GLB/moonwatch.glb` writes the watch's GLB, its four
clips baked, on request.

The case, dial and bracelet are plain functions in `lib/watch.py` (each with its
finishes set), which their models return and the full watch composes; `moonwatch.py`
composes the movement from the same three `@memo` layers `movement.py` does. No model
calls another.

Only the three layers are `@memo`: each holds seconds of kernel work (movement_base
alone is ~130 s cold), so an edit to one layer runs it and replays the other two, and
a leaf edit costs about 4.5 s. The groups of parts inside a layer (`lib/mvt_*.py`,
`_plate_parts` ... `_chrono_bridge_parts`) are plain functions: marking each of the
19 added nothing beyond the layers (see "When to use `@memo`" in
`models/README.md`). The case stays one body: `lib/case.py`'s band builder leaves
`_BAND_CHAMFER_APPLIED` in its module for the polish builder to read, state a replay
would not set, so no builder of the case is a `@memo`.

## Materials

The original's `materials=` finishes (`lib/materials.py`) are `FinishedMaterial`
values set on the parts before they are composed, by the same leaf-label
assignments (`apply_materials`). Each finish is the catalogue's entry for the
metal, glass or rubber in the finish's look (explicit scalar `PbrProperties`), or the project's own
where the catalogue has none, with the old finish name as the description. A
finish keeps the original's metallic, roughness and clearcoat (`coat`,
`coat_roughness`), and takes the look fields its name implies:

| Old finish | Material | Look beyond the original's metallic, roughness and coat |
| --- | --- | --- |
| brushed_steel | Stainless 316 | anisotropy 0.5 (brushed) |
| case_mirror_polish | Stainless 316 | no grain |
| polished_steel | Stainless 304 | no grain |
| satin_steel | Stainless 304 | anisotropy 0.4 (satin) |
| blued_screw | Steel 1018 | |
| grained_lever | Steel 1018 | anisotropy 0.5 (straight grain) |
| brass_part, copper_plate, gilt_wheel | Brass C360 | |
| anglage_mirror | Brass C360 | roughness 0.1 (mirror; 0.14 before) |
| bezel_anodized | Aluminum 6061-T6 | no grain |
| glass | Glass, soda-lime | transmissive, ior 1.52 |
| glass_back | `Sapphire` (corundum, 3980 kg/m^3) | transmissive, ior 1.77 |
| ruby_jewel | `Ruby` (corundum, 3980 kg/m^3) | transmission 0.8, ior 1.77 |
| rubber | NBR 70A | |
| matte_print | `Matte Print`, no density | |

Every finish uses explicit scalar PBR values; assignments restore authored colours, and a
transmissive part's colour is its tint. One face finish is painted: the bezel
ring is polished steel and its snailed top annulus satin (`paint(ring, faces,
FINISHES["satin_steel"])` in `lib/watch.py`). The chronograph works, which had no
assignments in the original, take the base's finishes by the same rules
(`MODEL_MATERIAL_ASSIGNMENTS["chrono_works"]`), so every part of every
document has a material.

## The full watch

`moonwatch.py` is one model composing the four in its body, the movement cased by the
flip about X and the MOVT_Z_OFFSET lift. The old `KINEMATICS` and `ANIMATION` are
build123d joints, placed where the parts stand and paired by label:

- **Mates.** The six hands turn on the dial (revolute; lume, hubs and the chrono cap
  fastened to theirs), the going train and the pallet fork in the movement (revolute),
  the balance (revolute; pinions, pallet stones, arbor, staff, impulse jewel and the 16
  timing screws fastened), the chronograph runner and coupling wheel in the chronograph works
  (revolute), the crown on the case middle (cylindrical: winding turn and setting
  travel) and the two pushers (prismatic, inward along their axes). The stem is not
  fastened to the crown: it stays with the movement, which the clips lift out of the
  case.
- **Couplings and poses.** The gear trains are two couplings, `running` (seconds of
  time) and `chrono` (seconds of chronograph running), each a constraint: its wheels
  and hands move only through it, and its range is what their limits allow (an hour of
  `running`, half an hour of `chrono`, either way). The old poses are configurations
  (`one_minute`, `half_hour`, `chrono_at_10min`, `start_pressed`, `reset_pressed`,
  `winding`, `setting`; `rest` is the watch as built).
- **Clips.** `running` is a motion, a function of time over the escapement and the two
  couplings. `reveal`, `showcase` and `grand_tour` are GLB animations (`cadgen.gltf`):
  the escapement and the trains posed at every key, each part or group the old clips
  translated moved along its own vector, the movement's tiers fanned (translations inside
  the movement, so its flip carries them, as the old clip composed them), and the
  movement rising out of the case and turning 180 degrees about X through its centre.
  Nothing but the mechanism is a joint. A GLB of the watch carries all four as clips.
  Neither a motion nor an animation has a loop: a player repeats it, and every part ends
  a clip where it started but the going train and the chronograph's recorders, which
  keep the watch's time. The animations play the old clips' tables: the reveal's lifts,
  the showcase's sideways clearing of the dial, bezel stack and crystal, its crown, crown
  tube and o-ring and the two pushers' parts drawn out along their axes, the caseback
  stack and bracelet spread, and the tour's headroom lift.
- **The escapement** (every clip runs it): the balance swings, the pallet fork snaps
  between its banks each beat, and each beat the escape wheel takes one half-tooth step
  (12 deg). The old clip then crept the fourth and third wheels 144 deg a loop and the
  small seconds with them, faster than their ratios; the train moves only through
  `running` now, so it steps with the escape wheel at its own ratios: 0.2 s of the
  watch's time a beat, 1.6 s a 6 s clip (the small seconds 9.6 deg, the minute hand
  0.16 deg). The chronograph runs through `chrono`, 60 s a clip: its runner and seconds
  hand one turn, as before, and now its minute (12 deg) and hour recorders with them.
- **The tier fan** (`showcase`, `grand_tour`) runs as the old clips had it: each tier's
  offset in the cased watch frame, negative toward the caseback (the bridge side), which
  the movement's flip turns upward, so open, the going train and pallet fork, the barrel,
  the pallet, train and barrel bridges, the winding, the balance with its cock and the
  chronograph works stand above the plate in that order, and the keyless works below it.

New finishes for the dial, hands and bracelet follow the same rules as the case's:
`black_lacquer` and `lume_plot` are own materials (coatings, no density),
`painted_hand` is Steel 1018, `dial_polished_furniture` and `polished_link` Stainless
316. The finishing sampler, which had no assignments, takes each coupon's movement
counterpart's finish; the movement ring the full watch adds is satin steel.
