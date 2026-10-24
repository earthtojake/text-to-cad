# Model catalog

Run each script with the repository cadgen Python environment. Each builds its model in
the engine and prints its id and page; `cadgen export <id> STEP/<name>.step` (or `.stl`)
writes a file of it when one is wanted.

- `baseline.py`: thin-wall starting mounting tray.
- `fdm.py`: thicker walls/floor and four gussets.
- `sheet.py`: uniform sheet with two circular bends.
- `injection.py`: Z-drafted walls and holes, plus four thin tapered ribs.
- `cnc.py`: thicker walls and optional floor root fillets.

Shared geometry lives in `lib/tray_geometry.py`. The original's write-up (its
[`README.md`](../README.md): the comparison, its checks and limitations) and its checks and
figure ([`scripts/verify.py`](../scripts/verify.py), [`scripts/figure.py`](../scripts/figure.py),
reading STEP and STL exports, which `cadgen export` writes) are beside this folder.
