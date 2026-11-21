# Environments

Read this file when a script needs packages of its own, a run stops on an import, or a
check builds again a model another script built.

`cad run` takes `uv run`'s options (`--with`, `-m`, `--python`, `--index-url`, ...) and its
script header, and needs nothing set up. cad itself is pinned to this computer's release,
and its integrations are worked out from the script's imports (`import build123d` is the
build123d integration), so a script names only its own packages, at the top of the script:

```python
# /// script
# dependencies = ["pandas>=2"]
# ///
```

- `cad run` makes that environment once and keeps it for the runs after. What cannot be
  installed beside cad is refused in one line with uv's reason: change the requirement it
  names, or, where the network is needed once, run it outside a sandbox or with its
  permission.
- A header may name `cad[...]` to choose cad's integrations itself (`"cad[build123d]"`),
  never a version of cad: a script that pins cad to another release is refused.
- For a one-off, `cad run --with pandas src/plate.py`. A local folder or wheel works too,
  its path relative to the working directory (in a header, to the script's folder), and
  the next run installs it again after an edit.
- A script with no header inside a Python project (a `pyproject.toml`) runs with the
  project's dependencies, its `uv.lock` exactly where it has one, and the project's uv
  settings (a private index), as `uv run` does.

Two things follow from that, for a project of several scripts:

- **The imports are read without running anything**: the script's own and those of the local modules
  it imports, found in its folder, its package or its project. A module reached only through a path
  added at run time (`sys.path.insert(0, ...)` in a check under `checks/` that imports the model from
  the folder above) is not read, so the check stops on `No module named 'build123d'`: import
  `build123d` in the check itself, or name `"cad[build123d]"` in its header, as the line under the
  error says.
- **One header for the scripts that call one model.** Each distinct set of packages is an environment,
  and each environment has a worker of its own in the server that holds the whole model and shares
  nothing it kept with another's. The first of them to run after an edit builds the model in full,
  where a script in the model's own environment replays what the edit did not reach, and several
  such workers of a large model pass the server's memory limit, which retires one. Give the checks
  of a project the same header (the union of what they need).
