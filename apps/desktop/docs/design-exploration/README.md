# Hardcore design-system exploration

These mockups keep the product structure and content constant so the visual system can be compared honestly:

- project folders and task-like chat rows on the left
- one active chat and composer in the middle
- the selected CAD artifact, viewer, feature tree, and parameters on the right

Open `index.html` and use the theme switcher, or review the rendered screenshots in `screenshots/`.

## Directions

### 01 · SMUI Refined

An evolution of the current Jake/SMUI bridge: Nord surfaces, sharp edges, dense controls, and monospace-forward typography. It has the lowest migration cost and strongest continuity with the standalone viewer, but the all-monospace treatment can make conversation and project content feel more like a terminal than a modern desktop tool.

### 02 · Precision Studio

A neutral professional-tool system with proportional typography, modest radii, warm surfaces, and blue focus. It gives the clearest hierarchy and most comfortable reading experience, but needs a stronger Hardcore identity.

### 03 · Hardcore Drafting

A custom CAD-native visual layer based on Amy's recurring drawing-paper and title-block language: warm paper, near-black ink, blueprint focus, restrained technical typography, and orange markup reserved for selected geometry. It is the most ownable direction, but requires more accessibility and token QA than adapting the existing SMUI theme.

## Recommended synthesis

Use **Precision Studio's typography, spacing, and panel hierarchy** with **Hardcore Drafting's blueprint/markup language**. Preserve Jake's viewer behavior and map both the Electron shell and the viewer onto neutral Hardcore semantic tokens rather than coupling feature code to SMUI-specific variables.

The repo already has the necessary design-system spine in `@emdash/theme`, `@emdash/ui`, and the desktop viewer bridge. The next step is a theme and primitive consolidation, not building a component system from zero.
