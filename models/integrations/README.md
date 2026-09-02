# Integration fixtures

These fixtures keep multiple source formats together when the behavior under
test is a handoff between tools rather than one isolated model format.

- [kicad-burr/](kicad-burr/README.md) validates a KiCad populated-board export,
  an enclosure repair in mechanical source, and Burr assembly interference.

Keep each integration self-contained and reproducible. Retain durable exchange
artifacts in Git LFS when they are part of the regression contract. Put review
screenshots, videos, and one-run reports under `/tmp` or on the pull request,
not in `models/`.
