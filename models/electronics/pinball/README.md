# SHORT CIRCUIT: a miniature pinball machine whose playfield is its circuit board

**Build the board first.** The playfield board's KiCad files are generated from the design model, not committed:
`cad run build.py` in `board/` makes them in about eight minutes (KiCad 10.99 comes with the `cad` command; KiCad's
stock libraries from macOS's KiCad.app or `KICAD_STOCK`). Opening the board or its schematic in the CAD Viewer or in
KiCad, and `board/check_fit.py`, need that build first; the design model (`src/`) does not.

An 8 mm chrome steel ball on a 112 x 236 mm four-layer board: the playfield IS the PCB, its gold art the machine's
switches ("the ball is the switch": a comb of two nets the ball shorts), its flippers driven by two 16 ohm coils from
USB-C PD at 9 V. The board is routed, ERC clean and DRC clean (0 errors, 14 warnings, listed in its README). Two parts
of the project live here:

| Folder | What |
| --- | --- |
| `src/` | the design model: `layout.py` (every place and size), `playfield.py` (the art, as 2D geometry the board scripts read too), `dotfont.py` (the one typeface), `parts.py`, `looks.py` (the finishes), `machine.py` (the assembly), `physics.py`, `check_fit.py` |
| `board/` | the scripts that write the playfield's KiCad project (a root sheet and 6 sub-sheets, its libraries and the board), its build (`build.py`) and its checks: [`board/README.md`](board/README.md) |

## Build

From this folder, with the `cad` command:

```bash
cad run src/machine.py        # short_circuit (off), short_circuit_lit (on, a flipper up), both without the glass, two close-ups
cad run src/check_fit.py      # does it fit and does it play (exits 1 on any failure)
python3 src/physics.py        # the ball, the pitch, the flippers, the plunger and the power budget, in numbers
```

`check_fit.py` measures the overlap of every pair of parts whose boxes meet (any overlap fails unless the pair is
meant to be pressed together), and slices every part on the playfield at the ball's heights to find where the ball can
roll: one connected region must take it from the plunger round the arch, through each lane, to the flippers.

## The playfield board

Everything about the board (what is on it, how it is laid out, how to rebuild, check and view it, and what is real and
what is simplified) is in [`board/README.md`](board/README.md).

Not here yet: the backglass board, the FR-4 flipper/sling/target cards as a panel, the firmware (the pin map is
`board/scripts/geometry.py: gpio_map`), fabrication outputs (Gerbers, BOM and placement, once the remembered LCSC
numbers are checked) and the mechanics' DFM, with the printed parts cut for the pockets `board/check_fit.py` lists.
