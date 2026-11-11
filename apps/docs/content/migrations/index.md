---
title: Migrations
description: The hand-migration guides between text-to-cad releases, for a project or a computer set up on an earlier one.
---

Most updates need nothing from you: a release that breaks nothing installs itself. For any other, run the install command again, or click the update button in the CAD Viewer or the CAD app, and your computer moves to the new release ([Updates](/docs/install#updates)).

A release that breaks something comes with a migration guide. Each guide says what changed and what to change in a project written for the earlier release. Below 1.0, a breaking change bumps the minor version, so the guides are named for the minor versions they move between.

| From | To | Guide |
| --- | --- | --- |
| 0.10 | the next release | [Migrating from 0.10 (draft)](/docs/migrations/0.10-to-next) |
| 0.8 | 0.10 | [Migrating from 0.8 to 0.10](/docs/migrations/0.8-to-0.10) |
| 0.7 | 0.8 | [Migrating from 0.7 to 0.8](/docs/migrations/0.7-to-0.8) |
| 0.4 | 0.5 | [Migrating from 0.4 to 0.5](/docs/migrations/0.4-to-0.5) |

One guide follows a dependency instead of a release: [moving to OpenCASCADE 8](/docs/migrations/opencascade-8), for model code that uses build123d methods 0.12 removed or calls the kernel directly.

The guides are files in the repository, under [`docs/migrations`](repo:docs/migrations), and are shown here as they are written there.
