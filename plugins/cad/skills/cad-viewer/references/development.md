# CAD Viewer Development

Use this reference only when the user asks to modify, debug, or iterate on CAD
Viewer source.

CAD Viewer source development happens in the root
source workspace, not inside this generated skill runtime.

If you are not currently working directly in the editable source workspace, ask
the user for the correct checkout and run the agent from that repository.

Once inside the repository, read root `AGENTS.md` for guidance on modifying and running the Viewer.

## External Tool Integration

The Text-to-CAD system uses standard robotics and CAD interchange formats:

- **URDF** (Unified Robot Description Format) for robot kinematics
- **SRDF** (Semantic Robot Description Format) for planning semantics
- **SDF** (Simulation Description Format) for simulation models

These formats are compatible with many open-source tools:

- **FreeCAD**: Can import/export URDF and STEP files. OpenCASCADE backend enables parametric modeling.
- **Gmsh**: Can mesh STEP/STL geometry for finite element analysis.
- **OpenCASCADE**: Underlying geometry kernel for many CAD tools; STEP format provides interoperability.

For finite element pre/post-processing workflows:
1. Generate CAD geometry via Text-to-CAD (STEP/GLB output)
2. Import into FreeCAD for parametric edits if needed
3. Export to STEP/STL for Gmsh meshing
4. Use mesh for FEA simulation

Deep integration (direct OpenCASCADE library calls, Gmsh scripting) would require additional plugin development. The current architecture supports file-based interchange via standard formats.