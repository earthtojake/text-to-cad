# Falcon Heavy — Engine Instance Map

> **Educational, non-functional public-source reconstruction. Not suitable for manufacture, propulsion, testing, or operational engineering.**

Linked source model: `models/renders/merlin1d/` (vendored parametric library `merlin_common.py`, reduced decorative detail for instancing; cluster-fit exit 960 mm — see DIMENSIONS.md). Octaweb pattern: 8 outer engines on a 1290 mm circle + 1 center per core, outer turbopumps oriented tangentially. Generated from the live assembly.

| # | Instance | X (mm) | Y (mm) | Z exit (mm) |
|---|---|---|---|---|
| 1 | `merlin1d_instance_core_center__linked` | 0 | 0 | 0 |
| 2 | `merlin1d_instance_core_outer_1__linked` | 1290 | 0 | 0 |
| 3 | `merlin1d_instance_core_outer_2__linked` | 912 | 912 | 0 |
| 4 | `merlin1d_instance_core_outer_3__linked` | 0 | 1290 | 0 |
| 5 | `merlin1d_instance_core_outer_4__linked` | -912 | 912 | 0 |
| 6 | `merlin1d_instance_core_outer_5__linked` | -1290 | 0 | 0 |
| 7 | `merlin1d_instance_core_outer_6__linked` | -912 | -912 | 0 |
| 8 | `merlin1d_instance_core_outer_7__linked` | -0 | -1290 | 0 |
| 9 | `merlin1d_instance_core_outer_8__linked` | 912 | -912 | 0 |
| 10 | `merlin1d_instance_port_center__linked` | -3660 | 0 | 0 |
| 11 | `merlin1d_instance_port_outer_1__linked` | -2370 | 0 | 0 |
| 12 | `merlin1d_instance_port_outer_2__linked` | -2748 | 912 | 0 |
| 13 | `merlin1d_instance_port_outer_3__linked` | -3660 | 1290 | 0 |
| 14 | `merlin1d_instance_port_outer_4__linked` | -4572 | 912 | 0 |
| 15 | `merlin1d_instance_port_outer_5__linked` | -4950 | 0 | 0 |
| 16 | `merlin1d_instance_port_outer_6__linked` | -4572 | -912 | 0 |
| 17 | `merlin1d_instance_port_outer_7__linked` | -3660 | -1290 | 0 |
| 18 | `merlin1d_instance_port_outer_8__linked` | -2748 | -912 | 0 |
| 19 | `merlin1d_instance_stbd_center__linked` | 3660 | 0 | 0 |
| 20 | `merlin1d_instance_stbd_outer_1__linked` | 4950 | 0 | 0 |
| 21 | `merlin1d_instance_stbd_outer_2__linked` | 4572 | 912 | 0 |
| 22 | `merlin1d_instance_stbd_outer_3__linked` | 3660 | 1290 | 0 |
| 23 | `merlin1d_instance_stbd_outer_4__linked` | 2748 | 912 | 0 |
| 24 | `merlin1d_instance_stbd_outer_5__linked` | 2370 | 0 | 0 |
| 25 | `merlin1d_instance_stbd_outer_6__linked` | 2748 | -912 | 0 |
| 26 | `merlin1d_instance_stbd_outer_7__linked` | 3660 | -1290 | 0 |
| 27 | `merlin1d_instance_stbd_outer_8__linked` | 4572 | -912 | 0 |
| 28 | `mvac_engine__linked_derivative_schematic` | 0 | 0 | 43200 |

Total: 27 Merlin 1D instances + 1 MVac derivative.