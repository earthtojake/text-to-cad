# electronics models

A circuit board, the case it lives in and a cable it drives, as one cad-project. Every script
directly under `src/` is runnable; its outputs land in format folders at the project root
(`PCB/`, `STEP/`, `HARNESS/`). The `src/` tree is committed; build the outputs you need.

```bash
python models/electronics/src/servo_power.py    # the board: KiCad project, fab files, 3D
python models/electronics/src/servo_case.py     # the case, with the board in it
python models/electronics/src/servo_cable.py    # the cable, from the board's netlist
```

The board needs KiCad 10 and Freerouting (`$pcb`); the cable's drawing needs WireViz and
Graphviz (`$harness`).

| Script | Artifact | Description |
|--------|----------|-------------|
| `servo_power.py` | `PCB/servo_power.kicad_{pro,sch,pcb,dru}`, `PCB/servo_power.{gerbers.zip,bom.csv,pos.csv}`, `STEP/servo_power.step` | USB-C servo power board: 5 V through a polyfuse to three servo headers, an AMS1117 for 3.3 V logic, autorouted over two ground pours, JLCPCB rules |
| `servo_case.py` | `STEP/servo_case.step` | Open-top printed case: the board on four standoffs, its USB-C port through the left wall |
| `servo_cable.py` | `HARNESS/servo_cable.harness.yml` | Servo extension from the board's J2 header to a servo's three-wire lead |
