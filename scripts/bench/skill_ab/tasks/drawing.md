skill: engineering-drawing
fixtures: plate.py -> src/plate.py

## Request

Make me a shop drawing (a PDF) of the plate in src/plate.py: A3 sheet, the three standard views plus an isometric, overall dimensions, the spacing of the hole pattern in both directions, and a callout for the four 5 mm through holes. Title MOUNT PLATE, part number MP-001, material 6061-T6, general tolerance ISO 2768-m.

## Expect

A PDF on A3 with four views, overall dimensions, the 60 and 40 mm hole spacings and a `4x` 5 mm THRU callout; the run prints no "measures blank paper" or "annotation overlaps"; the script imports the plate's facts from the model.
