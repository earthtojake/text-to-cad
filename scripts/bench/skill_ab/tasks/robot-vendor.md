skill: robot-simulation
fixtures: vendor_arm.py => vendor/RA2.step

## Request

vendor/RA2.step is the STEP a vendor sent us for their RA2 two-joint arm: a base, a lower link standing on it and an upper link standing on that, with no joints in the file. I need a URDF of it for ROS. From the datasheet: the first joint turns the lower link about a horizontal axis (the model's Y) through the centre of the base's top face, plus or minus 90 degrees; the second turns the upper link about a parallel axis through the centre of the lower link's top face, plus or minus 120 degrees. Every part is 6061 aluminium. Validate it and tell me what you checked and what I should check on the real arm.

## Expect

A model script that reads the STEP and declares the mechanism (not a URDF written by hand), exported with `cad model export`. Three links, two revolute joints, each axis along Y; the first joint's origin 20 mm above the base's origin and the second 120 mm above the first (0.02 and 0.12 in the URDF); limits of 1.5708 and 2.0944 rad. Masses from the material: 0.1527, 0.1296 and 0.0691 kg, total 0.3514 kg. `cad urdf validate` OK. The reply says which way positive rotation goes or that the sign is unverified.
