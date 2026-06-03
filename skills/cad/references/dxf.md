# DXF secondary workflow

Read this file only when the user requests DXF or 2D drawing output from CAD geometry.

DXF is secondary. Generate and validate the STEP envelope first when the geometry originates from a CAD source. Do not treat DXF layers as STEP part/assembly structure.

## Tool

```bash
python scripts/dxf targets... [flags]
```

`scripts/dxf` is a generator for Python sources with `gen_dxf()`. It does not inspect or validate existing `.dxf` files. For existing DXF inspection, use `$cad-viewer` for visual review and a focused DXF library/tool such as `ezdxf` for entity/layer checks.

Plain generated Python targets write sibling `.dxf` outputs. Use `-o`/`--output` only with one plain generated Python target, or use `SOURCE.py=OUTPUT.dxf` positional pairs for per-target custom outputs. Paired output paths resolve from the command cwd.

Do not put output-path fields such as `dxf_output` in the `gen_dxf()` return envelope. The supported path controls are the sibling default, `-o`/`--output`, and `SOURCE.py=OUTPUT.dxf`.

## Source requirements

A DXF target must be a Python source defining:

```python
def gen_dxf():
    ...
    return document
```

The same file must also define a valid `gen_step()` envelope because discovery uses the CAD source catalog.

```python
def gen_step():
    ...
    return shape_or_compound
```

## Workflow

1. Convert the user's prose into a natural-language CAD brief.
2. Build or validate the `gen_step()` envelope.
3. Generate STEP with lightweight facts/planes/positioning inspection.
4. Hand the generated STEP path to `$cad-viewer` when available and return its link.
5. Add or update `gen_dxf()` for the requested projection, layout, or drawing output.
6. Run `scripts/dxf` on explicit Python source targets.
7. Hand the generated DXF path to `$cad-viewer` when available, then report the DXF output plus the primary STEP and `$cad-viewer` viewer links.

## Command

```bash
python scripts/dxf path/to/source.py
python scripts/dxf path/to/source.py -o path/to/output.dxf
python scripts/dxf path/to/a.py=out/a.dxf path/to/b.py=out/b.dxf
```

## Reporting

```text
Files:
- STEP: /absolute/project/models/path/to/source.step
- DXF: /absolute/project/models/path/to/output.dxf

CAD Viewer:
- STEP: http://127.0.0.1:4178/?dir=/absolute/project/models&file=path/to/source.step
- DXF: http://127.0.0.1:4178/?dir=/absolute/project/models&file=path/to/output.dxf

Validation:
- STEP geometry: checked with facts/planes/positioning
- DXF: generated from gen_dxf(); drawing-layer content reported if available
```
