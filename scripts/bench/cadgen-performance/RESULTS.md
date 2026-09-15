# Recorded performance results

These measurements were taken on September 12, 2026, against main at
`3e4dfdeef2cbd5804c369592b59620132188a150` and the performance branch starting
at `10b90215febea61b01c258cf04f33dbb39fe7dc5`, including the fixes recorded in
that review. They are historical measurements, not a fresh benchmark of every
subsequent commit. The original review and raw run records remain in
[commit 4edbd7356](https://github.com/earthtojake/text-to-cad/tree/4edbd7356a7b6a6a346117e81cf1d13f11d3babc/scripts/bench/cadgen-performance).
Raw logs, profiles and intermediate reports are intentionally absent from the
current tree.

The host was an M1 Max with 64 GiB RAM, macOS 26.5.1, Python 3.13.13,
build123d 0.11.1, cadquery-ocp 7.9.3.1.1 and Chromium 151. Generation comparisons
used identical source and dependency versions, separate stores and interleaved
before/after order: one cold sample and the median of three warm samples.
All 80 generation commands succeeded; 40 matched pairs produced byte-identical
STEP files. A cold sample used an empty application store and a new model worker;
filesystem-cache and supervisor restarts were not established.

## Generation and edits

Seconds from CLI process start to completed STEP save, shown as **before → after**.

| Model | Cold generation | Warm unchanged | Geometry edit | Placement edit |
| --- | ---: | ---: | ---: | ---: |
| Plate, 1 part | 6.278 → 3.375 | 2.705 → 0.118 | 2.690 → 0.191 | 2.679 → 0.190 |
| Plates, 24 parts | 5.139 → 2.637 | 2.609 → 0.112 | 2.696 → 0.257 | 2.687 → 0.259 |
| Procedural planetary, 9 parts | 6.217 → 3.768 | 2.670 → 0.132 | 3.138 → 1.077 | 3.135 → 1.049 |
| Imported planetary STEP, 9 parts | 6.328 → 5.862 | 2.576 → 0.121 | 3.087 → 0.693 | 3.202 → 0.676 |

Warm unchanged calls improved 20–23× and geometry edits 2.9–14.1× in this set.
Much of the gain comes from avoiding startup and reconstruction; it does not
mean OCCT boolean operations themselves became that much faster. The retained
`warm_build.py` command isolates in-process execution and has a narrower timing
boundary than the CLI comparison above.

## CAD snapshots

Seconds for 1200 × 900 snapshots without `--render`. First snapshots follow a
fresh generation; warm snapshots are medians.

| Model | First snapshot | Warm snapshot | Generation + first snapshot |
| --- | ---: | ---: | ---: |
| Plate | 1.672 → 3.470 | 1.659 → 1.106 | 7.126 → 6.756 |
| Plates, 24 parts | 1.642 → 3.452 | 1.680 → 1.119 | 6.667 → 6.076 |
| Planetary, 9 parts | 1.674 → 4.440 | 1.685 → 1.155 | 7.864 → 8.100 |

Warm snapshots improved about 1.5×. Deferring surface generation moves work into
the first display request: combined generation plus first snapshot was 5–9%
faster for the plates and 3% slower for the planetary assembly. Those combined
measurements used their own generation samples, so they do not sum with the
separate generation table.

## Browser display

First visible geometry in seconds at 1280 × 900, DPR 1, using each version's
production default Inspect settings. These are product-default comparisons,
not matched mesh-quality measurements. Visibility records the first actual
draw to the default framebuffer, not GPU completion or compositor presentation.

| Model | Cold first visible | Warm first visible, median |
| --- | ---: | ---: |
| Plate | 3.798 → 3.001 | 0.205 → 0.199 |
| Plates, 24 parts | 2.289 → 6.267 | 0.223 → 0.222 |
| Planetary, 9 parts | 7.733 → 8.206 | 0.268 → 0.227 |
| Iris, 118 occurrences / 91 components | 12.208 → 8.004 | 0.587 → 0.237 |

The iris appeared sooner, but complete standard detail took **12.254 → 16.571 s
cold (35% slower)** and **0.623 → 0.673 s warm (8% slower)**. Orbit frame intervals
were about 8.3 ms in both versions; no meaningful frame-rate gain was established.
These results do not establish uniformly faster cold display.

No new giant-assembly or FreeCAD benchmark was run for this comparison. Earlier
FreeCAD retained-document operation timings exclude costs included in cadgen's
CLI timings. This evidence does not establish FreeCAD parity or a general 100×
speedup. Use the [benchmark commands](README.md) for focused follow-up measurements.
