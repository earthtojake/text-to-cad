# Minimum measurement requirements

Checkpoint 1 is a review envelope, not a fitment model. Before the master
topper envelope becomes dimensionally trustworthy, capture:

1. A common-coordinate scan of the bed rails, rear cab surface and roof trailing
   region, including at least five transverse sections and three longitudinal
   sections.
2. Bed-rail mounting-plane height, outer and inner widths, usable length,
   section geometry, corner radii, and local surface normals.
3. Cab rear roof height and width, rear-wall angle/curvature, and the minimum
   non-contacting motion/deflection keep-out behind the cab.
4. Tailgate width, height, thickness, hinge axis, open/closed swept envelope,
   latches, and the upper opening available above the closed pickup tailgate.
5. XYZ and interface geometry for every factory bed anchor, including fastener
   access and verified load documentation.
6. XYZ, service direction, and actuation envelope for the gear-tunnel, tonneau,
   and tailgate controls.
7. XYZ, local mounting plane, fastener/interface geometry, and permissible load
   documentation for the factory cab and bed crossbar mounts.
8. Rear-light and camera fields of view, wiring routes, connectors, and legal
   clearance requirements.

Use stable scan datums tied to the coordinate convention in `cad/parameters.py`.
Replace parameters one group at a time, regenerate, and rerun all reference
views after each update.
