"""Direct clamp-to-servo support for the isolated lower-link concept.

Reuse the pinned 10 mm M2 male/female posts: male studs face into the servo,
female ends land on the clamp, with M2x6 screws installed from underneath.
"""
from lib import base_stacked_layout as g

POST_HEIGHT_MM = 10.0
SERVO_PAD_Z = g.T + POST_HEIGHT_MM
ARM_Z_SHIFT = SERVO_PAD_Z - g.servo_mount_z('pi_hat')


