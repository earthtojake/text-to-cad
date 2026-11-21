skill: cad
fixtures: plate.py -> src/plate.py
id: src/plate.py::plate

## Request

My plate is src/plate.py (already built; its page is open). In the viewer I clicked one of the holes and it copied this reference:

{ID}#plate/face 10

Make that hole 8 mm in diameter and leave the other three as they are. And tell me where that hole's centre is.

## Expect

The hole at (30, 20) has radius 4.0 and the other three 2.5 (`cad model inspect <id> 'plate/face N'` for faces 7 to 10). The reply gives the centre, (30, 20).
