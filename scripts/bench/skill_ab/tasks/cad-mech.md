skill: cad

## Request

Model a small hinged box. The base is a tray 80 x 50 x 30 mm outside (80 along X, 50 along Y, 30 tall) with 2 mm walls and floor, open on top. The lid is a flat plate 80 x 50 x 3 mm that sits on top of the base. The lid hinges about an axis along X that runs along the top outer edge of the base's back wall (the wall at +Y). Add the hinge as a joint so the lid swings open, with named states for closed and for open at 90 degrees. Check that nothing collides closed and open. Then find how far the lid can really swing before it hits the base, and set the joint's limits from that.

## Expect

One revolute joint, states `closed` and `open`. `cad model interference` run at both. `cad model ranges` run (it reports 174 degrees: the lid's end face lands on the back wall at 180, and the stop is where the surfaces all but touch); the limits written are 174, or up to 180 where the reply shows by exact interference that the lid is clear to there, and it says which and why.
