"""Generate ENGINE_INSTANCES.md — the linked Merlin 1D instance map.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("falcon_heavy.step", HERE / "falcon_heavy.step.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
shape = m.gen_step()

rows = []
def walk(c):
    for ch in getattr(c, "children", []) or []:
        if str(ch.label or "").startswith("merlin1d_instance"):
            p = ch.location.position
            rows.append((ch.label, p.X, p.Y, p.Z))
        elif str(ch.label or "").startswith("mvac_engine"):
            p = ch.location.position
            rows.append((ch.label, p.X, p.Y, p.Z))
        walk(ch)
walk(shape)

out = [
    "# Falcon Heavy — Engine Instance Map",
    "",
    "> **Educational, non-functional public-source reconstruction. Not suitable "
    "for manufacture, propulsion, testing, or operational engineering.**",
    "",
    "Linked source model: `models/renders/merlin1d/` (vendored parametric library "
    "`merlin_common.py`, reduced decorative detail for instancing; cluster-fit "
    "exit 960 mm — see DIMENSIONS.md). Octaweb pattern: 8 outer engines on a "
    "1290 mm circle + 1 center per core, outer turbopumps oriented "
    "tangentially. Generated from the live assembly.",
    "",
    "| # | Instance | X (mm) | Y (mm) | Z exit (mm) |",
    "|---|---|---|---|---|",
]
for i, (label, x, y, z) in enumerate(sorted(rows), 1):
    out.append(f"| {i} | `{label}` | {x:.0f} | {y:.0f} | {z:.0f} |")
out.append("")
out.append(f"Total: {len([r for r in rows if 'merlin1d' in r[0]])} Merlin 1D instances + "
           f"{len([r for r in rows if 'mvac' in r[0]])} MVac derivative.")
(HERE / "ENGINE_INSTANCES.md").write_text("\n".join(out), encoding="utf-8")
print(f"wrote ENGINE_INSTANCES.md ({len(rows)} engines)")
