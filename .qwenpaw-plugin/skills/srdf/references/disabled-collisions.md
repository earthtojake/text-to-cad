# SRDF disabled collisions

Disabled collisions are planning-safety data. Treat them as derived evidence, not as decorative XML.

## Valid sources

Use one of these sources:

- adjacent-link policy from the URDF kinematic graph;
- MoveIt Setup Assistant self-collision matrix generation;
- sampled collision analysis from a known MoveIt configuration;
- explicit user-provided collision matrix;
- a manually reviewed pair with a specific rationale.

Do not infer disabled collision pairs from visual theme or vague prose.

## XML shape

```xml
<disable_collisions link1="base_link" link2="shoulder_link" reason="Adjacent"/>
```

The current runtime requires:

- `link1` and `link2`;
- both links to exist in the URDF;
- distinct link names;
- a non-empty `reason`;
- no duplicate or reversed duplicate pairs.

## Reason and provenance

Use truthful reasons. Examples:

| Reason | Typical source |
|---|---|
| `Adjacent` | URDF graph adjacency |
| `Never` | Setup Assistant sampled matrix |
| `Always` | Setup Assistant sampled matrix |
| `Default` | Setup Assistant sampled matrix |
| `Manual: tool fixture is outside workspace envelope` | Explicit human review |

The current parser classifies reasons into broad provenance buckets such as adjacent, sampled, setup assistant, manual, or assumed. Avoid `assumed` unless the user explicitly requested a provisional SRDF and the risk is reported.

## Review checklist

Before committing a disabled collision pair:

- Is the pair adjacent or sampled-safe?
- Does disabling the pair hide a possible real collision during the planned task?
- Was the pair generated with sufficient sampling density?
- Is the pair still valid after geometry, limits, or group membership changed?
- Was manual rationale written down?

If many manual pairs are present, prefer regenerating the self-collision matrix with MoveIt Setup Assistant.
