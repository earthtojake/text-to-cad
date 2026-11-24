# Profiling

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

Request function timings with `arm.build(profile=True)`. The script remains plain Python,
run as `python model.py`; it takes no engine flags, and no command profiles a build.

Profiling measures **actual execution**, preserving normal memo, body and XBF hits.
It does not force a rebuild: a replayed body has no function timings for its earlier
execution, and a kernel memo hit measures lookup/replay, not the skipped operation.
Read the existing `cache`, `memo` and `bodies` fields alongside the timings. `verify=True`
retains its usual verification behavior when combined with profiling; it is not a cold run.

The `profile` field in each top-level `Report.models` entry covers
one entire build request, including script loading, all requested and child models,
document processing and declared exports. For multiple targets those entries carry
the **same request-wide profile**, not separate per-model measurements to add together.
It runs in the worker (or the caller with `daemon=False`), excludes client/daemon startup
and queuing, and includes waits during that worker call. Work in other processes is
not function-profiled.

The JSON profile identifies `scope: "build_request"`, `mode: "actual_execution"`, the
process id, elapsed `seconds`, total `self_seconds`, and `function_count`. Its two
lists hold at most 20 rows each: `project_cumulative` (functions under the script's
folder, excluding installed dependencies) and
`top_self` (all functions by self time). A row names `file`, `line`, `function`, total
`calls`, `primitive_calls` (non-recursive calls), `self_seconds` and
`cumulative_seconds`. `profiling.describe` prints those tables; Python callers receive
these fields without printing or writing a profile file. No profile is saved or
reused by a later build. Failed model reports include the work observed before failure.

`cProfile` slows call-heavy Python code, so compare shares with care. It runs with
`builtins=False`: native OCCT time belongs to the Python function that called it,
which also avoids pybind11's unmatched profile events on Python 3.12 and later.
