# Model catalog

Run `planetary_gear_assembly.py` to build the assembly and all nine children.
Each model can also be run independently. Outputs go to `../STEP/`.

| Source | Geometry |
| --- | --- |
| `planetary_gear_assembly.py` | Nine-part assembly; carrier placement |
| `carrier_plate.py` | Carrier plate; independently editable diameter |
| `ring_gear.py` | 60-tooth internal ring |
| `sun_gear.py` | 24-tooth sun |
| `planet_gear_1.py`, `planet_gear_2.py`, `planet_gear_3.py` | Three individually placed and colored 18-tooth planets |
| `planet_pin_1.py`, `planet_pin_2.py`, `planet_pin_3.py` | Three individually placed pins |

`lib/` holds plain factories and shared constants, with no decorated models.
