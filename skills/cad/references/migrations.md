# Migrations

Read this file when the tooling behaves as though it disagrees with a model you
believe is correct. That is the signature of version skew: a project authored
against an older cadgen, running under a newer one.

cadgen carries no compatibility layer — no shims, no aliases, no deprecated
keyword arguments, no codemod. Every entry point teaches one contract, the
current one, so skew surfaces as ordinary wrongness rather than as a message
about versions. Recognizing it is the reader's job.

## When to suspect skew

- **A model script runs, exits 0, and writes nothing.** An older source carries
  no decorated function and no entry point of its own, so Python defines a
  function and exits. Nothing looks for an entry point by name.
- **A command or flag you are sure of comes back unknown**, and the help lists
  an unfamiliar set. Building a model is running its script; there is no
  generation verb, and retired spellings are simply unrecognized arguments.
- **A sidecar is refused for its schema version.** Sidecars are never upgraded
  in place and never partially read, because a wrong-shaped one would cost a
  model its kinematics silently.
- **A model that used to articulate renders inert**, presenting as a plain
  document with no pose and no animation. Nothing is discovered by convention: a
  companion `.js` file is read only when a decorator names it.
- **Meshes come out visibly coarser or finer, with no error.** Mesh tolerance
  kept its name and changed meaning — chord tolerance is a fraction of the
  component's bounding diagonal, not an absolute length — so a value carried
  across from an older project is wrong in proportion to the part's own size.

A half-migrated project fails in the wrong place: a correctly converted script
with a stale sidecar beside it fails at the sidecar. Symptoms are only worth
reading once the old artifacts are gone.

## Migration guides

- **cadgen 0.4 → 0.5** — generator functions became decorated model scripts, the
  generation CLI was removed, sidecars and provenance moved, snapshot job JSON
  was re-keyed, and mesh tolerance became relative.
  https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-0.4-to-0.5.md
