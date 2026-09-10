# Model inventory — 2026-09-09

Counts cover the source, validation, website, and authored STEP render modules
now consolidated under `models/tendon_hand`. Historical candidates and
validation revisions are included. Repository-wide CAD engine code, Markdown
documentation, JSON data, caches, and binary artifacts are excluded from the
code count. Lines are physical lines, including blank lines and comments.

| Code area | Files | Lines |
|---|---:|---:|
| Modeling Python | 206 | 37,241 |
| Validation and diagnostic scripts | 302 | 14,455 |
| Preview and behavior checks | 2 | 1,137 |
| Authored export helpers | 12 | 46 |
| **Total** | **522** | **52,879** |

There are 50,895 nonblank lines.

The following is the generated-output inventory measured before the source-only
consolidation. None of these STEP files is committed in this project:

| STEP inventory | Files | Exact bytes | Decimal size |
|---|---:|---:|---:|
| Generated exports, excluding the imported/ archive | 154 | 4,150,143,977 | 4.15 GB |
| All STEP files, including stored import copies | 189 | 4,963,629,536 | 4.96 GB |
| Latest complete mechanical candidate, hand_mechanical_candidate_r13.step | 1 | 279,285,151 | 279.3 MB |

The export total includes historical full assemblies, component exports, and diagnostic candidates; it is not a count of unique parts. All 189 files contain real file data, with no Git LFS pointer placeholders.
