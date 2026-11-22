skill: cad

## Request

Design a motor mount plate to be CNC machined from 6061 aluminium on a 3-axis mill (the shop has 3, 6 and 10 mm end mills). It is an 80 x 60 x 10 mm plate. A 22 mm through bore at the centre. Four M4 clearance holes (4.5 mm) on a 31 mm square pattern around the bore. A rectangular pocket 40 x 30 mm and 5 mm deep in the top face, centred on the bore (a cable relief). Four 5.5 mm mounting holes, each 6 mm in from the plate's edges at the corners. Make sure it can actually be machined, and tell me about anything I should know. I want a STEP at the end.

## Expect

`cad model dfm <id> --process cnc --material aluminum --tools 3,6,10` exits 0 on the result. The pocket's corners carry a radius the 3 mm tool can cut, and the reply says so as a departure from the request. The material and its process are recorded on the part and the check's flags in the module docstring. The reply says that the M4 holes straddle the pocket's wall, which the check reports as four `cnc.partial_hole` warnings (each reaching 1.75 mm past the wall) unless the design was changed to clear them, and what to do about it. A STEP.
