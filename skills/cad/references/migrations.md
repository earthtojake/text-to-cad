# Migrations

Read this file when source, command syntax or sidecars target a different
cadgen version. First run `cadgen doctor <skill-dir>` to check the installed
version against the skill's pin. Follow the specific error and current command
help; a modeling failure alone does not establish version skew.

cadgen uses hard interface cutovers. A retired interface may fail with a
teaching error naming its replacement; it is not a compatibility alias.
The retired inspect CLI is replaced by Python checks using `read_scene` and
native geometry; see [inspection](inspection-and-validation.md).

## When to suspect skew

- **A model script runs, exits 0, and writes nothing.** An older source carries
  no decorated function and no entry point of its own, so Python defines a
  function and exits. Nothing looks for an entry point by name.
- **A command or flag you are sure of comes back unknown**, and the help lists
  an unfamiliar set. Building a model is running its script; there is no
  generation verb. Consult current help and any replacement named by the error.
- **A sidecar is refused for its schema version.** Sidecars are never upgraded
  in place and never partially read, because a wrong-shaped one would cost a
  model its kinematics silently.
- **A model that used to articulate renders inert**, presenting as a plain
  document with no pose and no animation. Nothing is discovered by convention:
  kinematics and animation are `kinematics=` and `animation=` on the model's
  decorator, and the build puts both in the document's sidecar. A companion
  JavaScript file beside the document is no longer read. A generated model's
  build warns about the leftover file and names the replacement decorator;
  the warning does not stop the build.
- **Meshes come out visibly coarser or finer, with no error.** Mesh tolerance
  kept its name and changed meaning — chord tolerance is a fraction of the
  component's bounding diagonal, not an absolute length — so a value carried
  across from an older project is wrong in proportion to the part's own size.

A migrated source may still have incompatible saved outputs. Rebuild or
re-annotate the affected document as the error directs; preserve imported
sources and do not delete unrelated artifacts to diagnose a version mismatch.

## Migration guides

- **cadgen 0.4 → 0.5** — generator functions became decorated model scripts, the
  generation CLI was removed, sidecars and provenance moved, snapshot job JSON
  was re-keyed, and mesh tolerance became relative.
  https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-0.4-to-0.5.md
