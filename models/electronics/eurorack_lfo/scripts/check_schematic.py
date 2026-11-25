"""Holds the schematic KiCad reads to the connections the generator meant (scripts/schematic_intent.json):
every (part, pin) on the net it was drawn to, in both LFO instances. Run: cad run scripts/check_schematic.py"""

import json
from collections import defaultdict
from pathlib import Path

from cad import kicad_sch

ROOT = Path(__file__).resolve().parent.parent
sch = kicad_sch.read(ROOT / "twin_orbit.kicad_sch")
have = {(p.ref, p.number): p.net for p in sch.pins if not p.ref.startswith("#")}
intent = json.loads((Path(__file__).parent / "schematic_intent.json").read_text())
GLOBAL = {"+12V", "-12V", "GND"}


def kicad_name(net, sheet, ref):
    if net == "NC":
        return None
    if net in GLOBAL:
        return net
    if net.startswith("^"):
        # a hierarchical label: the net takes the root's label name
        suffix = sheet[-1]
        return f"/{net[1:]}_{suffix}"
    return f"/{sheet}/{net}" if sheet else f"/{net}"


bad = 0
expected = defaultdict(set)
for sheet_key, rows in intent.items():
    for ref, pin, net in rows:
        if ref.startswith("#"):
            continue
        instances = [(ref, "LFO A"), (ref[0:len(ref) - 3] + "2" + ref[-2:], "LFO B")] if sheet_key == "lfo" else [(ref, "Power" if sheet_key == "power" else "")]
        for r, sheet in instances:
            want = kicad_name(net, sheet, r)
            got = have.get((r, pin))
            expected[want].add(f"{r}.{pin}")
            if want is None:
                if got and not got.startswith("unconnected"):
                    print("NC pin on a net:", r, pin, got)
                    bad += 1
                continue
            if got != want:
                print(f"{r}.{pin}: drawn to {want}, KiCad reads {got}")
                bad += 1
# every pin of every part is accounted for
drawn = {(r, p) for rows in intent.values() for r, p, _ in rows}
nets = defaultdict(list)
for (r, p), n in have.items():
    nets[n].append(f"{r}.{p}")
print(f"{len(have)} pins, {len([n for n in nets if n and not n.startswith('unconnected')])} nets; {bad} mismatch(es)")
for n in sorted(nets, key=str):
    if n and not n.startswith("unconnected") and len(nets[n]) == 1:
        print("single-pin net:", n, nets[n])
unconn = [k for k, v in nets.items() if not k or k.startswith("unconnected")]
print("unconnected pins:", sum(len(nets[k]) for k in unconn))
