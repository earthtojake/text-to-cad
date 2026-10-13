# usd-brep-demo models

EXPERIMENTAL. build123d scripts run on NVIDIA's
[usd-brep](https://github.com/NVIDIA-Omniverse/usd-brep) kernel (SMLib) through
[`packages/usd-brep-build123d`](../../../packages/usd-brep-build123d/README.md), and
written as exact B-rep in OpenUSD (`BrepArray` prims). No OpenCascade is loaded, and cadgen
is not involved: these are plain scripts, not `@step` models.

usd-brep's wheel is CPython 3.12 on Linux or Windows only. From the repository root:

```bash
uv run --python 3.12 --with usd-brep==1.0.0 --with numpy \
  --with-editable packages/usd-brep-build123d python models/usd-brep-demo/src/hub_flange_g2.py
```

| Script | Artifact | Description |
|--------|----------|-------------|
| `circular_flange.py` | `USD/circular_flange.usda` | `examples/src/circular_flange.py`'s build123d code with only the import changed; the same solid (41,259.763 mm³) |
| `hub_flange_g2.py` | `USD/hub_flange_g2.usda` | Hub flange whose hub-to-plate blend is curvature-continuous (G2), which build123d's circular fillets cannot make (`bd.blend`, the package's one language extension) |
