# falcon_heavy models

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

`models/falcon_heavy` on cadgen 0.8: the SpaceX Falcon Heavy as a
museum-style full-vehicle reconstruction from public sources. One script,
`falcon_heavy.py`, holds the three models that were three scripts:

| Model | | What it is |
| --- | --- | --- |
| `falcon_heavy` | `@model` | Full stack: three cores, 27 linked Merlin 1D engines, nosecones, grid fins, stowed legs, raceways, attach hardware, MVac second stage, 5.2 m fairing (85 parts, 2,142 placements) |
| `falcon_heavy_cutaway` | `@model` | Center core + S2 + fairing sectioned 270° (opening +Y): schematic LOX/RP-1 volumes, transfer tube, domes, COPV-like placeholders, octaweb frames, avionics/separation placeholders, payload adapter + payload |
| `falcon_heavy_exploded` | `@model` | Boosters outboard, stage/fairing lifted, translucent guide rods |

Build from this folder: `python falcon_heavy.py` builds all three, each printing its id
and page; a run writes nothing.

```
python falcon_heavy.py
cadgen snapshot "$STACK_ID" falcon_heavy.png        # the id: lines the run printed
cadgen snapshot "$CUTAWAY_ID" cutaway.png --camera back
```

The sources, confidence and estimates behind every number
([`RESEARCH.md`](../RESEARCH.md), [`PROVENANCE.md`](../PROVENANCE.md),
[`DIMENSIONS.md`](../DIMENSIONS.md)) and the point-in-time hierarchy and engine map
([`HIERARCHY.md`](../HIERARCHY.md), [`ENGINE_INSTANCES.md`](../ENGINE_INSTANCES.md)) were the
original project's, and are kept beside this folder.

## How it is built

`lib/falcon_common.py` (the vehicle) and `lib/merlin_common.py` (the vendored
Merlin 1D library) are the original's but for `import build123d as bd` and three
changes the engine asks for:

- **Placements.** The engines were placed with the old `compound_from_instances`,
  because a build123d move copied the ~70-solid engine. Under cadgen's engine a
  move places the same geometry, so a cluster is nine `moved` placements of one
  prototype.
- **No module state.** `engine_prototype()` cached its result in a module global and
  set `merlin_common.DETAIL_BOLTS = False` before every build; a function may not
  leave state for another, so the cache is a `@memo` stage (below) and
  `DETAIL_BOLTS` is the constant `False` the vehicle always built with.
- Three scripts became one, so the three models share one worker and its memo.

Two `@memo` stages, measured (cold, the three models): 7.1 s with none, 5.7 s with
the first, 5.0 s with both.

- `engine_prototype()` (~400 kernel calls): every cluster calls it. Without the marker
  each of its calls is built again (its features are named apart, so its kernel calls
  miss): three Merlins per vehicle, nine per build. With it, one per build: every
  other call is a new placement of its result.
- `build_vehicle(cutaway)` (~1,300 kernel calls beside the engine's): the full stack
  and the exploded view both call `build_vehicle()`, so the exploded model's vehicle
  is a placement of the stack's (13 kernel calls of its own: the guide rods).

An edit to one group (the nose attach block's height) misses 6 calls per vehicle and
replays the engine (1.8 s); reverted, the files are the cold build's bytes.

## Not ported

Nothing: the three models are the three scripts. The STEP each wrote is an export
on request now (`cadgen export "$STACK_ID" STEP/falcon_heavy.step`).
