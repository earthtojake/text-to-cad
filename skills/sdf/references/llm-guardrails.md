# LLM guardrails for SDF authoring

This skill assumes agents are useful at structuring SDFormat documents and weak at silently deriving precise spatial, physical, and simulator-specific values. The workflow should route those weaknesses into explicit ledgers, constants, helpers, validators, and smoke tests.

## What agents can usually do well

- organize an SDF model or world into links, joints, frames, visuals, collisions, sensors, plugins, and includes;
- translate user intent into a plausible document structure;
- maintain naming consistency when names are explicit;
- write small throwaway Python scripts for derived numbers and transformations;
- explain assumptions and create checklists;
- preserve existing patterns when examples are nearby.

## What agents should not be trusted to infer silently

- exact link poses, frame transforms, or joint origins;
- positive joint-axis directions from visual theme;
- mesh units, mesh scale, or coordinate-system conventions;
- center of mass or inertia tensors from rendered shape alone;
- plugin filenames, parameters, topics, namespaces, or sensor schemas;
- whether a plugin is a simulator runtime plugin or a CAD Viewer visualization-only extension;
- target simulator support for a given SDFormat version or extension;
- whether collision geometry is stable for physics;
- whether external URIs resolve in the deployment environment.

## Required mitigation pattern

For every spatial, physical, or simulator-specific value, use one of these sources:

1. user-provided requirement;
2. upstream geometry, robot-description, planning-metadata, mesh manifest, or model package source;
3. target simulator documentation;
4. measured or calculated value with method stated;
5. explicit assumption recorded in the ledger comment block and the final report.

Do not hide guessed values in raw XML: every non-obvious number carries a comment or a ledger line naming its source.

## Placeholder policy

Placeholders are allowed only when the user asks for a scaffold, draft, or minimal example. Mark them as placeholders and keep them easy to replace.

Examples of acceptable placeholders:

```xml
<!-- placeholder_inertial: primitive approximation pending measured mass properties -->
<inertial>
  <mass>0.5</mass>
  ...
</inertial>
```

Examples of unacceptable placeholders:

- invented plugin filenames;
- adding CAD Viewer-only motion plugins to SDF files;
- arbitrary inertia values on a dynamic robot without a warning;
- guessed mesh scale that makes the visual look plausible;
- silently flipping a joint axis to match an expected screenshot.

## Spatial reasoning checklist

Before generating or modifying SDF, answer these questions in the ledger or final report:

| Question | Required evidence |
|---|---|
| What frame is each pose expressed in? | `relative_to`, source file, or documented default |
| What frame is each joint axis expressed in? | `expressed_in` or documented default |
| What is positive motion for each non-fixed joint? | command/test expectation or upstream source |
| Are mesh units and scales known? | manifest, CAD export config, or explicit assumption |
| Are visual and collision poses intentionally different? | simulation reason or source geometry |
| Are inertials measured, calculated, approximated, or omitted? | method and confidence |
| Are plugin and sensor parameters copied from target docs? | target simulator/version and source |

## Authoring style

Prefer this pattern:

```xml
<!-- Source: project CAD frame export 2026-05-12. RPY radians. -->
<pose relative_to="base_link">0.18 0 0.12 0 -0.2 0</pose>
```

Avoid this pattern:

```xml
<pose>0.18 0 .12 0 -11.5 0</pose>
```

The second version omits the frame, uses degrees without saying so, and makes the source of the transform impossible to audit.

## Validation expectations

The validator should catch cheap deterministic mistakes, but it cannot prove the design is physically or simulator-correct. After bundled validation, use optional external checks and simulator smoke tests when the task depends on simulator behavior.

Report skipped checks explicitly. A skipped check is not automatically a failure, but it is relevant risk information.

## Response behavior for agents

When finishing an SDF task, state:

- the `.sdf` path(s) created or modified;
- checks run and their result;
- checks skipped and why;
- assumptions and placeholders;
- risks that need simulator verification.

Do not simply say that the file is valid. Say which validator or smoke test passed.
