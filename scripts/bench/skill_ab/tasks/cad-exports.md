skill: cad
fixtures: plate.py -> src/plate.py, bracket.py -> src/bracket.py

## Request

src/plate.py and src/bracket.py are the two parts of a mount I am working on. My machinist works from a STEP of each and I print test pieces from an STL of each, and I keep sending files that are a version behind. Set it up so that after any change I can get all four files made again in one go (STEP/plate.step, STEP/bracket.step, STL/plate.stl, STL/bracket.stl), and tell me what to run. Then make the plate 8 mm thick instead of 6 and give me the updated files.

## Expect

The four files exist. `cad step inspect STEP/plate.step` gives bounds 80 x 60 x 8 mm and volume 37,772 mm^3, and STL/plate.stl spans 8 mm in Z (`stl.read(path).bounding_box()`); the bracket's are as they were, 60 x 40 x 66 mm and 28,937 mm^3. The reply names one command that makes all four again, and it does: with `T` in src/plate.py set to another value and only that command run, the plate's STEP and STL both measure the new thickness. Which way the files are exported (from the `.xbf`, a handle, the model function or an id) is noted, not graded.
