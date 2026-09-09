# Source review checkpoint

This branch preserves the hand work in progress and its runtime changes. It is
not a release or a finished model. Start with [README.md](README.md), then
[RESUME_STATUS.md](RESUME_STATUS.md) and [GAUNTLET.md](GAUNTLET.md).

The current R13 native certificate covers 3259 occurrences, 48 tendons and
actuators, and 225 specified static poses. It does not accept the independent
visual gates or unauthored choreography and explode transitions. The live
Viewer crashed the user's browser; BUG036 remains unresolved. Do not open the
full hand in a browser until bounded loading has been implemented and checked
outside the user's browser.

The PR includes:

- Model sources, authored presentation modules, design notes and validation
  runners, including earlier experiments needed to understand the revisions.
- Concise Markdown validation tables and acceptance ledgers.
- BUGS.md, including the unresolved native Boolean diagnostic and live Viewer
  memory failure.

Generated STEP/BREP files, sidecar JSON, numeric validation dumps, static route
packets, caches, progress files, logs, environments and review images stay local
and gitignored. This PR uploads none of those files and adds no LFS payloads.

The ledgers describe local audit results and reference local generated reports.
The R13 reconstruction and its validators depend on those intermediate native
exports and metadata; they are not a one-command fresh-clone build. A portable
regeneration workflow remains unfinished. Missing outputs or review images do
not supply an acceptance verdict.
