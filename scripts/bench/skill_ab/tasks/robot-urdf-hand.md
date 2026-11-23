skill: robot-simulation

## Request

There is no CAD for this yet. Write me a URDF by hand for a pan-tilt camera head so I can start on the controller. A base: a box 80 x 80 x 40 mm. A pan stage: a cylinder of radius 30 mm and height 20 mm that sits on top of the base and turns about the vertical axis through its centre. A camera body: a box 60 x 40 x 40 mm, 60 along its viewing direction, carried on the pan stage and tilting about a horizontal axis through the camera's centre, which is 30 mm above the top of the pan stage. At zero the camera looks along +X. Positive pan turns the camera to its left, and positive tilt raises its view. Pan is limited to plus or minus 170 degrees, tilt from 30 degrees down to 60 degrees up. Rough masses: base 300 g, pan stage 100 g, camera 150 g. Validate it and tell me what you checked.

## Expect

Three links and two revolute joints. The pan axis is +Z. The tilt axis is -Y in the pan link's frame (`0 -1 0`, or the same through the joint origin's `rpy`): `0 1 0` is the wrong sign, because a positive turn about +Y lowers a view along +X. Limits in radians: pan -2.967 to 2.967, tilt -0.5236 to 1.0472. Origins in metres: the pan joint 0.04 above the base link's frame if that frame is on the base's underside (0.02 if at its centre), the tilt joint 0.05 above the pan joint. Inertials on all three links with masses 0.3, 0.1 and 0.15 kg and inertia from the box and cylinder formulas (the base about its centre: ixx = iyy = 0.0002, izz = 0.00032), each at its solid's centre. `cad urdf validate` OK, and the reply shows the tilt sign was checked (a posed snapshot or a stated sweep), not assumed.
