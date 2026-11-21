skill: fea
fixtures: bracket.py => bracket.step

## Request

bracket.step is an L-bracket machined from 6061-T6 aluminium (E 68.9 GPa, Poisson's ratio 0.33, yield 276 MPa). It is bolted down flat, so treat the whole underside of its base as fixed. A cable pulls on the very top of the upright, horizontally, in the +X direction of the file (toward the side the base sticks out on), with 400 N: apply it on the upright's top end face. Will it hold, and how far does the top move?

## Expect

Peak von Mises 113.3 MPa, safety factor 2.44, largest displacement 0.59 mm (fixed: the base's underside; 400 N in +X on the upright's top face). The reply says it is a first-pass check and gives a hand estimate (about 100 MPa, 0.58 mm).
