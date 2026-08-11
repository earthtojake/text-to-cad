# CLI output: one contract, and a budget

## 0. Execution status

| Phase | Status |
|---|---|
| P0 parts inventory diet + compact stdout | **DONE** `1dd97067` |
| P1 stdout is the result, pinned by a test | **DONE** `1d51f036` |
| P2 progress parity | **DONE** `7185b6f9`, `bb08b841`, `+` |
| P3 standardize `--verbose` / `--debug` | **DONE** for `--verbose`; `--debug` stays STEP-snapshot-only, see §4 |
| P4 compact errors everywhere | **DONE** `bb08b841` |
| P5 docs + regression tests | **DONE** (this file; two test modules) |

## 1. The contract

**stdout is the result. stderr is everything else.** An agent reads the two apart:
`2>/dev/null` must leave something parseable, `>/dev/null` must leave something readable.
Narration, progress and failures are stderr; the answer is stdout, one line per target,
upgraded to compact JSON by `--json`.

**Payload size is a feature.** stdout is an agent's context window. Almost every output
here is O(1) — `gen` prints the same ~100 bytes for a 600-part assembly as for one part —
so the rare O(n) payload is where the whole cost lives, and redundancy there is measured in
tens of thousands of tokens.

**Never silent.** A long operation reports what it is doing, or it is indistinguishable
from a hang.

## 2. What was measured

The parts inventory (`snapshot --mode list`) on a 600-part rover, the only output whose
size grows with the model:

| | |
|---|---|
| before | 293,681 B / 12,619 lines (~73k tokens) |
| after | 93,989 B / 1 line |
| | **3.1x, ~50k tokens** |

Of the original: `id`, `occurrenceId` and `ref` were the same string three times over
(identical in **600/600** parts), `label` duplicated `name` (**600/600**), coordinates
carried 16 significant figures for millimetres (`-2449.9999046325684` for 2450 mm), and the
whole payload was pretty-printed (38% of the bytes).

A part now carries `ref`, `name`, `triangleCount`, `vertexCount`, `bounds`. `ref` is the
survivor because it pastes straight into `--focus` / `--hide` / `inspect`.

## 3. Progress, before and after

| CLI | Terminal progress | Sidecar record |
|---|---|---|
| `cad gen` | phase bar (was, still) | ✓ |
| `cad artifact` | none → **shared phase bar** | ✓ |
| `dxf artifact` | none → **shared phase bar** | ✓ |
| `snapshot` (all 6 skills) | none → **phase lines** | ✗ (nothing to record) |
| `dxf gen` | none → **shared phase bar** | ✓ |
| `implicit gen` | sink plumbed | ✓ |

Snapshot was the sharpest: silent for its *entire* run, which on a cold assembly is a
package build, a browser launch and a render. It now reports resolution BEFORE it starts,
because that is where the build happens and on a cold model it outlasts the render.

One shape everywhere: stderr only, self-erasing on a tty, one durable line per phase change
on a non-tty (an agent's captured log wants lines, not a bar smeared over hundreds of
writes).

## 4. Flags

Two axes, deliberately. `--verbose` is stage narration and timings on **stderr**;
`--debug` is provenance in the **JSON payload** (how an artifact resolved, cache hit or
rebuild, timings). No `--quiet` (an exit code plus `2>/dev/null` covers it) and no
per-stage flags. `--format` stays on `inspect`, the one place a text rendering earns its
keep.

`--verbose` now reaches every CLI that has one to give. Two corrections the work made to
the survey that produced this list: `dxf/dxf` and `urdf/urdf` are not CLIs at all --
`urdf/urdf` is the CLI *package* (no `__main__`, running it errors) whose entry is
`validate`, and `dxf/scripts/dxf` was an empty directory holding nothing but stale
bytecode, now deleted.

`--debug` deliberately stays on `cad snapshot` alone. It reports how a render artifact
RESOLVED -- generated vs imported, cache hit vs rebuild, selector re-extraction, resolution
time -- and no other CLI has an equivalent question to answer: `gen` and `artifact` already
report their outcome and package path on stdout, and a validator has nothing to resolve.
Adding the flag elsewhere would mean inventing content for it.

## 5. What holds the line

- `tests/python/global/test_cli_payload_budget.py` — names the allowed fields, names each
  deleted duplicate WITH the measurement that condemned it, and enumerates every
  stdout-JSON source. Its first version listed only two sources and missed that `cad
  artifact` and `dxf artifact` were still pretty-printing; widening it is what caught them.
- `tests/python/global/test_cli_stream_contract.py` — drives the real CLIs in subprocesses.
  Source inspection cannot catch a stream that drifts through a library three layers down.

## 6. Deliberately unchanged

Inputs and arguments, except the sanctioned `--verbose`/`--debug` additions. Descriptors
written to FILES stay indented and key-sorted — they are content-addressed artifacts, not
output, and only stdout is budgeted.
