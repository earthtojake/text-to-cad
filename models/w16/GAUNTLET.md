
## Whole-engine gauntlet, round 1 (2026-09-02 15:35)

Blind A/B packets (`src/lib/critic_pack.py`, both sides re-encoded as 1600 px PNG so
neither suffix nor size reveals the render), one fresh-context critic per view,
references from `tmp/refs/INDEX.md`. Renders: `render/gauntlet_job.json`
(presentation theme, solid, presentation-large, zoom 1.8–1.9).

| View | Reference | Verdict | Largest gap named for ours |
|---|---|---|---|
| Front three-quarter | A_04 (Bugatti W16, Vogt) | **LOST** (high) | "floating slab plenum and free-floating tube arcs" → a packaged induction: shaped plenum onto real runners, charge pipes anchored at both ends with flanges and clamps |
| Sectioned side | B_01 (Napier Lion cutaway, Beaulieu) | **LOST** (high) | "no piston or rod is visible … the intake pipe arcs across and hides the internals" → open the crankcase on the section to show piston–rod–crank in profile; route the intake pipe off that face |
| Top-down | A_03 (Chiron W16, Reutersberg) | **LOST** (high) | "two flat slab plenums with embossed rectangles and dot fasteners; pipes end in nothing" → true cast manifolds: ribbed, draft-tapered, radiused, runner throats meeting the head, real bolt bosses |
| Low sump | C_02 (Countach V12, dave_7) | **WON** (high) | — (critic: "sump, accessory drive, twin turbos and downpipes read as one designed assembly") |

Actions: induction re-sculpt + bank-1 front charge pipe rerouted aft of the section
plane (builder agent, `induction.py`); `SECTION_Z_MIN` −10 → −95 (the block's +y
crankcase half is now open to the pan rail for x > 121, exposing the crank throw
and rod big ends of cylinders 1–2). Round 2 re-runs all four views.

## Whole-engine gauntlet, round 2 (2026-09-02 17:35)

Same protocol, fresh packets and fresh references, after: induction re-sculpt
(cast plenum + 16 runner throats + flanged/clamped charge-pipe ends), section
deepened to the pan rail, bank-1 front turbo lifted off, oil filter and pump
moved aft/clear.

| View | Reference | Verdict | Note |
|---|---|---|---|
| Sectioned side (the money shot) | B_03 (Porsche 912 cutaway, Porsche Museum) | **WON** (medium) | "the near bank is cut open in profile so the twin overhead cams, valve buckets, followers, cylinder bores and the crank/rod line read in one continuous sweep" |
| Low sump | C_04 (McLaren F1 engine bay) | **WON** (medium) | "a coherent object … consistent material vocabulary … fasteners repeat at sane pitch, pipe bends have real radii and clamped joints" |
| Front three-quarter | A_05 (Bugatti W16, GIMS 2019) | LOST (high) | gap: "detail density collapses at the middle scale — no ribbing, bosses, brackets, clamps or auxiliary hardware between the large shapes and the fasteners" |
| Top-down | A_04 (Bugatti W16, Vogt) | LOST (high) | gap: "plenum covers are featureless mirrored rectangles … no runners, throttle body or intake ducting resolving into them" |

Round-1 → round-2 movement: section LOST → **WON**, low WON → **WON**, front34
and top still lost but on a different, narrower complaint (mid-scale detail and
plenum-lid articulation rather than "floating slab and tubes that end in
nothing"). The two remaining gaps are in TODO.md.

## Whole-engine gauntlet, round 3 (2026-09-02 18:55) — the two views that were still losing

After the two-hour finishing pass: cam covers gained 22 cast blade ribs and 22
drafted bolt bosses per bank, oil-filler towers, three sensor bosses per bank, a
PCV circuit and P-clip stanchions gathering the coil leads; the accessory
brackets gained load-path ribs, bosses and a repeated hose-clip family; the
intercooler lids gained a cross-rib grid, proud bolt bosses with spotfaces, a
relieved split-line step, differing casting numbers, a cross-flow coolant circuit
(cold in low at the rear, hot out high at the front), a degas tower with pressure
cap on one bank only, a temperature sender on the other, and a three-outline
throttle joint with gussets and a bolted duct stay.

| View | Reference | Verdict | Gap now named |
|---|---|---|---|
| Front three-quarter | A_04 (Bugatti W16, Vogt) | LOST (medium, was high) | "pipes, hoses and manifolds are routed for looks instead of purpose — they bend through open space and terminate vaguely instead of tying identifiable ports to identifiable components" |
| Top-down | A_04 (Bugatti W16, Vogt) | LOST (high) | "plenum/cover surfaces are undifferentiated flat slabs … no cast structure, bosses, or hardware transitions" |

Read across the three rounds, the front three-quarter complaint has moved from
"floating slab plenum and free-floating tubes" (round 1) to "detail collapses at
the middle scale" (round 2) to "the routing does not tie identifiable ports to
identifiable components" (round 3), and the confidence dropped from high to
medium. The top-down complaint has NOT moved: a crowned, ribbed lid still reads
flat from directly overhead, because in a plan view nothing of the crown shows in
silhouette. Fixing that view means changing what is on top, not how it is
detailed — exposed runner trumpets or an open lid, which the module's own
geometry currently forbids (BUGS #14).

Standing score: sectioned side WON, low sump WON, front three-quarter LOST,
top-down LOST. The brief's bar — all four views win — is NOT met.
