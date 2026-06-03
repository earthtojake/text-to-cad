# cadpy-metadata

Small, dependency-free metadata helpers shared by Python-generated URDF, SRDF,
and SDF skill runtimes.

The source of truth lives under `packages/cadpy_metadata`. Consuming skills
must use generated, installable copies under their own
`scripts/packages/cadpy_metadata` runtime directory.

Those skill-local copies can be installed from the consuming skill directory:

```bash
python -m pip install -r requirements.txt
```

Refresh a generated copy with the skill bundle router:

```bash
scripts/bundle/bundle-skill.sh <skill-id>
```
