# Migrating from 0.11 to the next release

Draft: this guide is renamed for its release when it ships. It covers one change: cad no longer reads
SDFormat, Gazebo's robot and world description (`.sdf` files). URDF and SRDF are read as before.

Each change names its tier of the compatibility law ([law 15](../../packages/cad/README.md#the-design-laws),
"Compatibility, by who pays for a break"), which says what a change of its kind keeps working.

## What is gone

The `sdf` document type, everywhere cad had it. cad itself never wrote an SDF, but the `robot-simulation`
skill of 0.11.0 to 0.11.7 taught an agent to: it wrote Gazebo models and worlds as `.sdf` files (an SDF
derived from a robot's URDF among them, a design ledger in a comment at the top of each), checked every
one it created or changed with `cad sdf validate` and drew them with `cad sdf snapshot`. 0.11.8's skill
stopped. So a project may hold `.sdf` files an agent wrote.

Those files are untouched and still SDFormat, which Gazebo reads as before. What changes is that cad no
longer opens, draws or checks them.

### The `cad sdf` commands (tier 1)

A hard cutover: each answers as a command that never existed does, exit 2:

```text
cad: unknown command 'sdf' (did you mean 'srdf'?); 'cad --help' lists the commands
```

| 0.11 | Now |
| --- | --- |
| `cad sdf validate world.sdf` (and `--gz-check`, `--gz-remote`) | Gazebo's own check: `gz sdf --check world.sdf` |
| `cad sdf snapshot world.sdf out.png` | gone: a robot cad draws is a URDF, `cad urdf snapshot robot.urdf out.png` |
| `python -m cad_server.cli.sdf ...` | gone, as `cad sdf` |

### The library's `cad.sdf` (tier 2)

A script that imports it breaks, with what Python says of a name that is not there: there is nothing to
alias it to.

| 0.11 | Now |
| --- | --- |
| `from cad import sdf` / `sdf.validate(path, gz_check=..., gz_remote=...)` | `ImportError`; check the file with `gz sdf --check FILE` |
| `cad.sdf.GZ_CHECK_MODES` | `AttributeError` (`module 'cad' has no attribute 'sdf'`) |
| `cad.sdf_source`, `cad.sdf_validation`, `cad.sdf_external` (0.10's spellings, aliases until now) | `ModuleNotFoundError` |
| `"sdf"` among `cad.registry.DOCUMENT_TYPES` | not there: `cad.registry` lists the types cad has |

### `.sdf` files in the viewer and the CAD app (tier 1, tier 3)

The viewer and the CAD app open no `.sdf`: one named by its path gets the answer any file of a type cad
does not show gets (`cad viewer world.sdf`: `no CAD file at ...`), the explorer lists none, and the CAD
tools (`cad_show`, `cad_open`) do not name the format.

An `.sdf` a page opened before stays in the state folder's records, and is read without a fault: it is no
longer listed in Recents, as a file of no type cad reads never was. Nothing needs doing; `cad delete
world.sdf` forgets its record (the file stays where it is).

## What to do instead

- **To check an SDF**, an agent's or anyone's, run Gazebo's own check, which `cad sdf validate` ran too
  where Gazebo was installed: `gz sdf --check world.sdf`. Gazebo keeps loading the file as before.
- **To look at a robot, pose it or check it in cad**, describe it as a URDF: `cad urdf validate
  robot.urdf`, `cad urdf snapshot robot.urdf out.png`, `cad viewer robot.urdf`, and in Python
  `cad.urdf.validate`. Gazebo loads a URDF too, so one description serves both. A robot built as a model
  writes its URDF from the model (`cad model export <id> robot.urdf`, its meshes beside it).
