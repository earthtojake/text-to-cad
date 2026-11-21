skill: pcb
fixtures: models/electronics/blinky/blinky.kicad_pcb -> blinky.kicad_pcb, models/electronics/blinky/blinky.kicad_pro -> blinky.kicad_pro, models/electronics/blinky/fp-lib-table -> fp-lib-table

## Request

blinky.kicad_pcb is my small LED board (KiCad project beside it). I want every track on the LED and VBUS nets widened to 0.5 mm. Then check the board, show me what the copper looks like now, and write the Gerbers and drill files for JLCPCB into a fab/ folder. I use the stable KiCad 9 app on this computer: is there anything I should know before you save the board? And last time DRC printed three warnings about footprint libraries: should I worry about those?

## Expect

Every LED and VBUS track 0.5 mm and GND untouched (`kicad_pcb.read`), DRC clean, Gerbers and a drill file in `fab/`, a copper snapshot. The reply warns that the save is in the nightly's format, and explains `lib_footprint_issues` as stock libraries that resolve only with a KiCad installed.
